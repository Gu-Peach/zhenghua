import asyncio
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, FastAPI, Header, Query, Request

from .models import DrawingRead, ResourcePackage
from .repository import ServiceError
from .simple_models import (
    LocalProfileOption,
    ProfileReferenceCreate,
    ProfileReferenceRead,
    SimpleConnectionCreate,
    SimpleConnectionDelete,
    SimpleConnectionEdit,
    SimpleConnectionPage,
    SimpleImportRead,
    SimpleMutationReceipt,
    SimpleProjectInput,
    SimpleProjectRead,
)


def install_management_routes(app: FastAPI, identity: Any) -> None:
    User = Annotated[str, Depends(identity)]
    Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)]

    @app.get("/api/v1/capabilities")
    async def capabilities(user: User) -> dict[str, bool]:
        return {"data_management": True, "extraction": False, "supervisor": False}

    @app.get("/api/v1/projects", response_model=list[SimpleProjectRead])
    async def projects(request: Request, user: User) -> Any:
        return await request.app.state.management.projects(user, request.state.token)

    @app.post("/api/v1/projects", response_model=SimpleProjectRead, status_code=201)
    async def create_project(
        body: SimpleProjectInput, request: Request, user: User
    ) -> Any:
        return await request.app.state.management.create(
            body.name, str(body.profile_id) if body.profile_id else None, user
        )

    @app.get("/api/v1/projects/{project_id}", response_model=SimpleProjectRead)
    async def project(project_id: UUID, request: Request, user: User) -> Any:
        return await request.app.state.management.detail(str(project_id), user)

    @app.patch("/api/v1/projects/{project_id}", response_model=SimpleProjectRead)
    async def rename(
        project_id: UUID, body: SimpleProjectInput, request: Request, user: User
    ) -> Any:
        if body.profile_id is not None:
            raise ServiceError(422, "PROFILE_FROZEN", "重命名不能修改项目的规则引用")
        return await request.app.state.management.rename(
            str(project_id), body.name, user
        )

    @app.delete("/api/v1/projects/{project_id}", status_code=204)
    async def remove_project(
        project_id: UUID,
        request: Request,
        user: User,
        expected_updated_at: str,
        confirmed: bool = False,
    ) -> None:
        if not confirmed:
            raise ServiceError(422, "CONFIRMATION_REQUIRED", "请确认删除项目及其文件")
        await request.app.state.management.delete_project(
            str(project_id), user, expected_updated_at
        )

    @app.get("/api/v1/projects/{project_id}/source")
    async def source(project_id: UUID, request: Request, user: User) -> Any:
        return await request.app.state.management.source(str(project_id), user)

    @app.get(
        "/api/v1/projects/{project_id}/connections", response_model=SimpleConnectionPage
    )
    async def results(
        project_id: UUID,
        request: Request,
        user: User,
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
        batch_id: str | None = Query(None, min_length=1, max_length=200),
        workspace_id: UUID | None = None,
        drawing_id: UUID | None = None,
        search: str = Query("", max_length=100),
    ) -> Any:
        return await request.app.state.management.results(
            str(project_id),
            user,
            offset=offset,
            limit=limit,
            batch=batch_id,
            workspace=str(workspace_id) if workspace_id else None,
            drawing=str(drawing_id) if drawing_id else None,
            search=search,
        )

    @app.post(
        "/api/v1/projects/{project_id}/connections",
        response_model=SimpleMutationReceipt,
        status_code=201,
    )
    async def add(
        project_id: UUID,
        body: SimpleConnectionCreate,
        request: Request,
        user: User,
        idempotency_key: Key,
    ) -> Any:
        return await request.app.state.management.mutate(
            str(project_id), user, "add", idempotency_key, body=body
        )

    @app.delete(
        "/api/v1/projects/{project_id}/connections/{connection_id}",
        response_model=SimpleMutationReceipt,
    )
    async def remove(
        project_id: UUID,
        connection_id: UUID,
        body: SimpleConnectionDelete,
        request: Request,
        user: User,
        idempotency_key: Key,
    ) -> Any:
        return await request.app.state.management.mutate(
            str(project_id),
            user,
            "remove",
            idempotency_key,
            identifier=str(connection_id),
            body=body,
        )

    @app.patch(
        "/api/v1/connections/{connection_id}", response_model=SimpleMutationReceipt
    )
    async def edit(
        connection_id: UUID,
        body: SimpleConnectionEdit,
        request: Request,
        user: User,
        idempotency_key: Key,
    ) -> Any:
        return await request.app.state.management.edit(
            str(connection_id), user, body, idempotency_key
        )

    @app.get("/api/v1/connections/{connection_id}/target", response_model=DrawingRead)
    async def target(connection_id: UUID, request: Request, user: User) -> Any:
        return await request.app.state.management.target(str(connection_id), user)

    @app.get("/api/v1/drawings/{drawing_id}", response_model=DrawingRead)
    async def drawing(drawing_id: UUID, request: Request, user: User) -> Any:
        return await request.app.state.management.drawing(str(drawing_id), user)

    # Static route must precede /{profile_id}.
    @app.get("/api/v1/rule-library/local", response_model=list[LocalProfileOption])
    async def available_profiles(request: Request, user: User) -> Any:
        options = await asyncio.to_thread(request.app.state.management.profiles.catalog)
        return [
            {name: option[name] for name in LocalProfileOption.model_fields}
            for option in options.values()
        ]

    @app.get("/api/v1/rule-library", response_model=list[ProfileReferenceRead])
    async def profiles(request: Request, user: User) -> Any:
        return await request.app.state.management.profiles.list(user)

    @app.post(
        "/api/v1/rule-library", response_model=ProfileReferenceRead, status_code=201
    )
    async def register(
        body: ProfileReferenceCreate, request: Request, user: User
    ) -> Any:
        row = await request.app.state.management.profiles.register(
            body.profile_key, user
        )
        return {**row, "can_delete": row["created_by"] == user}

    @app.delete("/api/v1/rule-library/{profile_id}", status_code=204)
    async def remove_profile(
        profile_id: UUID, request: Request, user: User, confirmed: bool = False
    ) -> None:
        if not confirmed:
            raise ServiceError(422, "CONFIRMATION_REQUIRED", "请确认删除规则引用")
        await request.app.state.management.profiles.remove(str(profile_id), user)

    @app.get("/api/v1/rule-library/{profile_id}", response_model=ResourcePackage)
    async def profile_package(profile_id: UUID, request: Request, user: User) -> Any:
        profiles = request.app.state.management.profiles
        row = await profiles.get(str(profile_id))
        return await asyncio.to_thread(profiles.resource_package, row)

    @app.post("/api/v1/imports", response_model=SimpleImportRead, status_code=201)
    async def upload(
        request: Request,
        user: User,
        idempotency_key: Key,
        profile_key: str = Query(pattern=r"^[a-z][a-z0-9_-]*$"),
        project_name: str = Query(min_length=1, max_length=200, pattern=r"\S"),
        filename: str = Query(min_length=1, max_length=200),
    ) -> Any:
        content = bytearray()
        async for chunk in request.stream():
            if len(content) + len(chunk) > request.app.state.db.settings.max_pdf_bytes:
                raise ServiceError(413, "PDF_TOO_LARGE", "PDF超过大小限制")
            content.extend(chunk)
        if not content.startswith(b"%PDF-"):
            raise ServiceError(422, "INVALID_PDF", "文件不是有效PDF")
        return await request.app.state.management.import_pdf(
            content=bytes(content),
            filename=filename,
            name=project_name,
            key=idempotency_key,
            user=user,
            profile_key=profile_key,
        )

    @app.api_route(
        "/api/v1/supervisor/{path:path}",
        methods=["GET", "POST"],
        include_in_schema=False,
    )
    async def supervisor_unavailable(user: User) -> None:
        raise ServiceError(
            503,
            "EXTRACTION_NOT_CONNECTED",
            "提取与AI对话暂未接入，当前支持文件及线表数据管理",
        )
