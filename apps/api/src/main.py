import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, Header, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "services/server/src"))
from wiring_server.agent_bridge import AgentBridge
from wiring_server.config import Settings
from wiring_server.connection_mutations import ConnectionMutations
from wiring_server.models import (
    ConnectionCreate,
    ConnectionDelete,
    ConnectionEdit,
    ConnectionMutationReceipt,
    ConnectionPage,
    DrawingRead,
    EditReceipt,
    ImportResponse,
    LoginInput,
    ProjectInput,
    ProjectRead,
    ResourcePackage,
    RuleCreate,
    RuleCreateReceipt,
    RuleDeleteReceipt,
    RuleRead,
    SessionResponse,
    SupervisorTurn,
    WiringUnitRead,
)
from wiring_server.repository import Repository, ServiceError
from wiring_server.rule_library import RuleLibraryService
from wiring_server.workbench import WorkbenchService


def create_app(
    settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> FastAPI:
    config = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(600, connect=15), transport=transport
        ) as http:
            app.state.db = Repository(config, http)
            app.state.workbench = WorkbenchService(app.state.db)
            app.state.connection_mutations = ConnectionMutations(config.database_url)
            app.state.agent = AgentBridge(app.state.db)
            app.state.rule_library = RuleLibraryService(app.state.db, app.state.agent)
            yield

    app = FastAPI(title="Wiring Workbench Server", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(
            {config.web_origin, "http://localhost:5174", "http://127.0.0.1:5174"}
        ),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "Last-Event-ID",
        ],
    )

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError) -> JSONResponse:
        response = JSONResponse(
            status_code=exc.status,
            content={"detail": {"code": exc.code, "message": exc.message}},
        )
        if exc.status == 401 and request.url.path == "/api/v1/auth/refresh":
            response.delete_cookie("wiring_refresh", path="/api/v1/auth")
        return response

    async def identity(
        request: Request, authorization: Annotated[str | None, Header()] = None
    ) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise ServiceError(401, "AUTH_REQUIRED", "请先登录")
        token = authorization[7:]
        try:
            response = await request.app.state.db.http.get(
                config.supabase_url + "/auth/v1/user",
                headers={
                    "apikey": config.service_key,
                    "Authorization": "Bearer " + token,
                },
            )
        except httpx.HTTPError as exc:
            raise ServiceError(503, "AUTH_UNAVAILABLE", "登录服务暂不可用") from exc
        if response.is_error:
            raise ServiceError(401, "SESSION_EXPIRED", "登录已过期，请重新登录")
        request.state.token = token
        return str(UUID(response.json()["id"]))

    User = Annotated[str, Depends(identity)]

    async def auth_session(
        request: Request, response: Response, grant: str, payload: dict[str, str]
    ) -> dict[str, Any]:
        try:
            result = await request.app.state.db.http.post(
                config.supabase_url + "/auth/v1/token",
                params={"grant_type": grant},
                json=payload,
                headers={"apikey": config.service_key},
            )
        except httpx.HTTPError as exc:
            raise ServiceError(503, "AUTH_UNAVAILABLE", "登录服务暂不可用") from exc
        if result.is_error:
            if result.status_code >= 500 or result.status_code == 429:
                raise ServiceError(
                    503, "AUTH_UNAVAILABLE", "登录服务暂不可用，请稍后重试"
                )
            raise ServiceError(401, "LOGIN_FAILED", "邮箱或密码错误，或登录已过期")
        data = result.json()
        response.set_cookie(
            "wiring_refresh",
            data["refresh_token"],
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
            max_age=30 * 86400,
            path="/api/v1/auth",
        )
        who = data["user"]
        return {
            "accessToken": data["access_token"],
            "expiresIn": data["expires_in"],
            "user": {
                "id": who["id"],
                "email": who.get("email", ""),
                "name": who.get("user_metadata", {}).get("display_name")
                or who.get("email", ""),
                "role": "工程师",
            },
        }

    @app.post("/api/v1/auth/login", response_model=SessionResponse)
    async def login(
        payload: LoginInput, request: Request, response: Response
    ) -> dict[str, Any]:
        return await auth_session(request, response, "password", payload.model_dump())

    def cookie_origin(request: Request) -> None:
        if request.headers.get("origin") not in {
            config.web_origin,
            "http://localhost:5174",
            "http://127.0.0.1:5174",
        }:
            raise ServiceError(403, "ORIGIN_DENIED", "请求来源不受信任")

    @app.post("/api/v1/auth/refresh", response_model=SessionResponse)
    async def refresh(request: Request, response: Response) -> dict[str, Any]:
        cookie_origin(request)
        token = request.cookies.get("wiring_refresh")
        if not token:
            raise ServiceError(401, "AUTH_REQUIRED", "请先登录")
        return await auth_session(
            request, response, "refresh_token", {"refresh_token": token}
        )

    @app.post("/api/v1/auth/logout", status_code=204)
    async def logout(
        request: Request,
        response: Response,
        authorization: Annotated[str | None, Header()] = None,
    ) -> Response:
        cookie_origin(request)
        # Expired access JWT must not prevent clearing the local refresh cookie.
        if authorization and authorization.startswith("Bearer "):
            try:
                revoked = await request.app.state.db.http.post(
                    config.supabase_url + "/auth/v1/logout",
                    headers={
                        "apikey": config.service_key,
                        "Authorization": authorization,
                    },
                )
                if revoked.status_code >= 500:
                    logging.getLogger(__name__).warning(
                        "Remote logout unavailable; local session cleared"
                    )
            except httpx.HTTPError:
                logging.getLogger(__name__).warning(
                    "Remote logout unreachable; local session cleared"
                )
        response.delete_cookie("wiring_refresh", path="/api/v1/auth")
        response.status_code = 204
        return response

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/projects", response_model=list[ProjectRead])
    async def list_projects(request: Request, user: User) -> list[dict[str, Any]]:
        return await request.app.state.workbench.projects(request.state.token)

    @app.post("/api/v1/projects", status_code=201, response_model=ProjectRead)
    async def create_project(
        payload: ProjectInput, request: Request, user: User
    ) -> dict[str, Any]:
        return await request.app.state.db.insert(
            "projects", {"name": payload.name, "owner_id": user}
        )

    @app.get("/api/v1/projects/{project_id}", response_model=ProjectRead)
    async def project_detail(
        project_id: UUID, request: Request, user: User
    ) -> dict[str, Any]:
        return await request.app.state.workbench.detail(str(project_id), user)

    @app.patch("/api/v1/projects/{project_id}", response_model=ProjectRead)
    async def rename_project(
        project_id: UUID, payload: ProjectInput, request: Request, user: User
    ) -> dict[str, Any]:
        await request.app.state.db.require_project(str(project_id), user, write=True)
        return (
            await request.app.state.db.update(
                "projects", {"id": f"eq.{project_id}"}, {"name": payload.name}
            )
        )[0]

    @app.delete("/api/v1/projects/{project_id}", status_code=204)
    async def delete_project(
        project_id: UUID,
        request: Request,
        user: User,
        expected_updated_at: str,
        confirmed: bool = False,
    ) -> None:
        if not confirmed:
            raise ServiceError(
                422, "CONFIRMATION_REQUIRED", "必须明确确认删除项目和原始文件"
            )
        await request.app.state.workbench.delete_project(
            str(project_id), user, expected_updated_at
        )

    @app.get("/api/v1/projects/{project_id}/connections", response_model=ConnectionPage)
    async def connections(
        project_id: UUID,
        request: Request,
        user: User,
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
        workspace_id: UUID | None = None,
        drawing_id: UUID | None = None,
        result_version_id: UUID | None = None,
        search: str = Query("", max_length=100),
    ) -> ConnectionPage:
        return await request.app.state.workbench.results(
            str(project_id),
            user,
            offset=offset,
            limit=limit,
            workspace=str(workspace_id) if workspace_id else None,
            drawing=str(drawing_id) if drawing_id else None,
            version=str(result_version_id) if result_version_id else None,
            search=search,
        )

    @app.get(
        "/api/v1/projects/{project_id}/wiring-units",
        response_model=list[WiringUnitRead],
    )
    async def wiring_units(
        project_id: UUID, request: Request, user: User
    ) -> list[dict[str, Any]]:
        return await request.app.state.workbench.units(str(project_id), user)

    @app.post(
        "/api/v1/projects/{project_id}/connections",
        response_model=ConnectionMutationReceipt,
        status_code=201,
    )
    async def add_connection(
        project_id: UUID,
        payload: ConnectionCreate,
        request: Request,
        user: User,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=1, max_length=200)
        ],
    ) -> dict[str, Any]:
        return await request.app.state.connection_mutations.add(
            str(project_id), user, payload, idempotency_key
        )

    @app.delete(
        "/api/v1/projects/{project_id}/connections/{connection_id}",
        response_model=ConnectionMutationReceipt,
    )
    async def delete_connection(
        project_id: UUID,
        connection_id: UUID,
        payload: ConnectionDelete,
        request: Request,
        user: User,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=1, max_length=200)
        ],
    ) -> dict[str, Any]:
        return await request.app.state.connection_mutations.remove(
            str(project_id), user, str(connection_id), payload, idempotency_key
        )

    @app.patch("/api/v1/connections/{connection_id}", response_model=EditReceipt)
    async def edit_connection(
        connection_id: UUID,
        payload: ConnectionEdit,
        request: Request,
        user: User,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=1, max_length=200)
        ],
    ) -> dict[str, Any]:
        return await request.app.state.workbench.edit(
            str(connection_id), user, payload, idempotency_key
        )

    @app.get("/api/v1/connections/{connection_id}/target", response_model=DrawingRead)
    async def connection_target(
        connection_id: UUID, request: Request, user: User
    ) -> dict[str, Any]:
        return await request.app.state.workbench.target(str(connection_id), user)

    @app.get("/api/v1/drawings/{drawing_id}", response_model=DrawingRead)
    async def drawing(drawing_id: UUID, request: Request, user: User) -> dict[str, Any]:
        return await request.app.state.workbench.drawing(str(drawing_id), user)

    @app.get("/api/v1/rule-library", response_model=list[RuleRead])
    async def rules(request: Request, user: User) -> list[dict[str, Any]]:
        return await request.app.state.workbench.rules(request.state.token, user)

    @app.post("/api/v1/rule-library", response_model=RuleCreateReceipt, status_code=201)
    async def create_rule(
        payload: RuleCreate, request: Request, user: User
    ) -> dict[str, Any]:
        return await request.app.state.rule_library.create(
            payload, user, request.state.token
        )

    @app.delete("/api/v1/rule-library/{package_id}", response_model=RuleDeleteReceipt)
    async def delete_rule(
        package_id: UUID,
        request: Request,
        user: User,
        confirmed: bool = Query(default=False),
    ) -> dict[str, Any]:
        return await request.app.state.rule_library.remove(
            str(package_id), user, request.state.token, confirmed
        )

    @app.get("/api/v1/rule-library/{package_id}", response_model=ResourcePackage)
    async def package(package_id: UUID, request: Request, user: User) -> dict[str, Any]:
        return await request.app.state.workbench.package(
            str(package_id), request.state.token
        )

    @app.post("/api/v1/imports", status_code=201, response_model=ImportResponse)
    async def import_pdf(
        request: Request,
        user: User,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=1, max_length=200)
        ],
        conversation_id: str = Query(min_length=1, max_length=200),
        project_name: str = Query(min_length=1, max_length=200),
        filename: str = Query(min_length=1, max_length=200),
    ) -> dict[str, Any]:
        content = bytearray()
        async for chunk in request.stream():
            if len(content) + len(chunk) > config.max_pdf_bytes:
                raise ServiceError(413, "PDF_TOO_LARGE", "PDF 超过大小限制")
            content.extend(chunk)
        if not content.startswith(b"%PDF-"):
            raise ServiceError(422, "INVALID_PDF", "文件不是有效 PDF")
        return await request.app.state.agent.call(
            "POST",
            "/v1/imports",
            params={
                "user_id": user,
                "conversation_id": conversation_id,
                "project_name": project_name,
                "filename": filename,
            },
            content=bytes(content),
            headers={
                "Content-Type": "application/pdf",
                "Idempotency-Key": idempotency_key,
            },
        )

    @app.post("/api/v1/supervisor/turns/stream")
    async def supervisor_turn(
        payload: SupervisorTurn, request: Request, user: User
    ) -> StreamingResponse:
        return await request.app.state.agent.turn(payload, user)

    @app.get("/api/v1/supervisor/conversations/{conversation_id}")
    async def conversation(
        conversation_id: str, request: Request, user: User
    ) -> dict[str, Any]:
        data = await request.app.state.agent.call(
            "GET",
            f"/v1/supervisor/conversations/{conversation_id}",
            params={"user_id": user},
        )
        if data.get("project_id"):
            await request.app.state.db.require_project(data["project_id"], user)
        return {
            k: data.get(k)
            for k in ("history", "agent_run_id", "project_id", "survives_restart")
        }

    @app.get("/api/v1/runs/{run_id}")
    async def run(run_id: UUID, request: Request, user: User) -> dict[str, Any]:
        await request.app.state.agent.require_run(str(run_id), user)
        return await request.app.state.agent.call("GET", f"/v1/runs/{run_id}")

    @app.get("/api/v1/runs/{run_id}/events/stream")
    async def run_events(
        run_id: UUID, request: Request, user: User, after_seq: int = Query(-1, ge=-1)
    ) -> StreamingResponse:
        await request.app.state.agent.require_run(str(run_id), user)
        return await request.app.state.agent.stream(
            "GET", f"/v1/runs/{run_id}/events/stream", params={"after_seq": after_seq}
        )

    @app.get("/api/v1/runs/{run_id}/artifacts")
    async def artifacts(run_id: UUID, request: Request, user: User) -> dict[str, Any]:
        await request.app.state.agent.require_run(str(run_id), user)
        # Only public summaries: bundles can contain local paths and model inputs.
        data = await request.app.state.agent.call("GET", f"/v1/runs/{run_id}/artifacts")
        allowed = {
            "artifact_id",
            "kind",
            "proposal_id",
            "diagnoses",
            "candidate_recommended",
            "authorization_required",
            "reason",
            "candidate",
        }
        return {
            "items": [
                {k: v for k, v in a.items() if k in allowed} for a in data["items"]
            ]
        }

    @app.get("/api/v1/proposals/{proposal_id}")
    async def proposal(
        proposal_id: str, request: Request, user: User
    ) -> dict[str, Any]:
        rows = await request.app.state.db.rows(
            "result_proposals", {"id": f"eq.{proposal_id}"}
        )
        if not rows:
            raise ServiceError(404, "PROPOSAL_NOT_FOUND", "修订建议不存在")
        await request.app.state.db.require_project(rows[0]["project_id"], user)
        return {
            **rows[0]["payload"],
            "committed_result_version_id": rows[0].get("committed_result_version_id"),
            "commit_receipt": rows[0].get("commit_receipt"),
        }

    return app


app = create_app()
