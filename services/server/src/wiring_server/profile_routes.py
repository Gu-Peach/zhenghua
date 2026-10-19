from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, FastAPI, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .profile_authoring import ProfileAuthoring
from .profile_contract import (
    ConversationEvent,
    ConversationState,
    ConversationTurn,
    DraftCreate,
    DraftDeleteInput,
    DraftView,
    EditFilesInput,
    PdfSampleRequest,
    PdfSampleResult,
    ProfileEditState,
    ProfileEvent,
    ProfileTurn,
    Stage,
    StageConfirm,
    StageGenerate,
    WizardState,
)
from .repository import ServiceError
from .simple_models import ProfileReferenceRead


class ProfileRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)


class ProfileImage(ProfileRevision):
    image_id: UUID
    filename: str = Field(min_length=1, max_length=200)
    content_base64: str = Field(min_length=1, max_length=14 * 1024 * 1024)


class ProfileFork(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft_id: UUID
    base_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ProfileProposalConfirm(ProfileRevision):
    accepted: bool


def install_profile_routes(app: FastAPI, identity: Any) -> None:
    User = Annotated[str, Depends(identity)]

    def service(request: Request) -> ProfileAuthoring:
        return ProfileAuthoring(request.app.state.db)

    @app.post(
        "/api/v1/profile/references/{profile}/draft", response_model=ProfileEditState
    )
    async def fork(
        profile: UUID, body: ProfileFork, request: Request, user: User
    ) -> Any:
        return await service(request).fork(
            str(profile), str(body.draft_id), body.base_checksum, user
        )

    @app.get("/api/v1/profile/drafts/{draft}/editor", response_model=ProfileEditState)
    async def editor_state(draft: UUID, request: Request, user: User) -> Any:
        return await service(request).call("GET", f"/drafts/{draft}/editor", user)

    @app.post(
        "/api/v1/profile/drafts/{draft}/editor/files", response_model=ProfileEditState
    )
    async def editor_save(
        draft: UUID, body: EditFilesInput, request: Request, user: User
    ) -> Any:
        return await service(request).call(
            "POST", f"/drafts/{draft}/editor/files", user, body.model_dump(mode="json")
        )

    @app.post(
        "/api/v1/profile/drafts/{draft}/editor/accept", response_model=ProfileEditState
    )
    async def editor_accept(
        draft: UUID, body: ProfileRevision, request: Request, user: User
    ) -> Any:
        return await service(request).call(
            "POST", f"/drafts/{draft}/editor/accept", user, body.model_dump(mode="json")
        )

    @app.post(
        "/api/v1/profile/drafts/{draft}/editor/proposals/{proposal}/confirm",
        response_model=ProfileEditState,
    )
    async def editor_confirm(
        draft: UUID,
        proposal: UUID,
        body: ProfileProposalConfirm,
        request: Request,
        user: User,
    ) -> Any:
        await service(request).call(
            "POST",
            f"/drafts/{draft}/proposals/{proposal}/confirm",
            user,
            body.model_dump(mode="json"),
        )
        return await service(request).call("GET", f"/drafts/{draft}/editor", user)

    @app.post(
        "/api/v1/profile/drafts/{draft}/editor/turns/stream",
        response_class=StreamingResponse,
        responses={
            200: {
                "model": ProfileEvent,
                "content": {"text/event-stream": {"schema": {"type": "string"}}},
            }
        },
    )
    async def editor_stream(
        draft: UUID, body: ProfileTurn, request: Request, user: User
    ) -> StreamingResponse:
        if body.intent != "discuss":
            raise ServiceError(422, "PROPOSAL_REQUIRED", "请先提出建议，再确认具体修改")
        return await service(request).bridge.stream(
            "POST",
            f"/v1/profile/drafts/{draft}/turns/stream",
            headers={"X-Profile-User-Id": user},
            json=body.model_dump(mode="json"),
        )

    @app.post("/api/v1/profile/cleanup", response_model=dict[str, bool])
    async def cleanup(request: Request, user: User) -> dict[str, bool]:
        return {"cleanup_pending": await service(request).cleanup(user)}

    @app.get("/api/v1/profile/drafts", response_model=list[DraftView])
    async def drafts(request: Request, user: User) -> Any:
        return await service(request).call("GET", "/drafts", user)

    @app.delete("/api/v1/profile/drafts/{draft}", status_code=204)
    async def delete_draft(
        draft: UUID, body: DraftDeleteInput, request: Request, user: User
    ) -> Response:
        await service(request).call(
            "DELETE", f"/drafts/{draft}", user, body.model_dump(mode="json")
        )
        return Response(status_code=204)

    @app.post("/api/v1/profile/drafts", response_model=DraftView)
    async def create(body: DraftCreate, request: Request, user: User) -> Any:
        profiles = request.app.state.management.profiles
        if not body.source_profile and body.key in await profiles.available(user):
            raise ServiceError(
                409, "PROFILE_KEY_EXISTS", "规则标识已存在，请为新规则使用不同标识"
            )
        return await service(request).call(
            "POST", "/drafts", user, body.model_dump(mode="json")
        )

    @app.get("/api/v1/profile/drafts/{draft}/wizard", response_model=WizardState)
    async def state(draft: UUID, request: Request, user: User) -> Any:
        return await service(request).call("GET", f"/drafts/{draft}/wizard", user)

    @app.get(
        "/api/v1/profile/drafts/{draft}/conversation", response_model=ConversationState
    )
    async def conversation_state(draft: UUID, request: Request, user: User) -> Any:
        return await service(request).call("GET", f"/drafts/{draft}/conversation", user)

    @app.post(
        "/api/v1/profile/drafts/{draft}/pdf-samples", response_model=PdfSampleResult
    )
    async def sample_pdf(
        draft: UUID, body: PdfSampleRequest, request: Request, user: User
    ) -> Any:
        return await service(request).call(
            "POST", f"/drafts/{draft}/pdf-samples", user, body.model_dump(mode="json")
        )

    @app.post(
        "/api/v1/profile/drafts/{draft}/conversation/turns/stream",
        response_class=StreamingResponse,
        responses={
            200: {
                "model": ConversationEvent,
                "description": "公开对话SSE事件",
                "content": {"text/event-stream": {"schema": {"type": "string"}}},
            }
        },
    )
    async def conversation_stream(
        draft: UUID, body: ConversationTurn, request: Request, user: User
    ) -> StreamingResponse:
        return await service(request).bridge.stream(
            "POST",
            f"/v1/profile/drafts/{draft}/conversation/turns/stream",
            headers={"X-Profile-User-Id": user},
            json=body.model_dump(mode="json"),
        )

    @app.post("/api/v1/profile/drafts/{draft}/images", response_model=DraftView)
    async def image(
        draft: UUID, body: ProfileImage, request: Request, user: User
    ) -> Any:
        return await service(request).call(
            "POST", f"/drafts/{draft}/images", user, body.model_dump(mode="json")
        )

    @app.get(
        "/api/v1/profile/drafts/{draft}/images/{image}", response_model=dict[str, str]
    )
    async def pixels(draft: UUID, image: UUID, request: Request, user: User) -> Any:
        return await service(request).call(
            "GET", f"/drafts/{draft}/images/{image}", user
        )

    @app.post(
        "/api/v1/profile/drafts/{draft}/stages/{stage}/generate",
        response_model=WizardState,
    )
    async def generate(
        draft: UUID, stage: Stage, body: StageGenerate, request: Request, user: User
    ) -> Any:
        return await service(request).call(
            "POST",
            f"/drafts/{draft}/stages/{stage}/generate",
            user,
            body.model_dump(mode="json"),
        )

    @app.post(
        "/api/v1/profile/drafts/{draft}/stages/{stage}/confirm",
        response_model=WizardState,
    )
    async def confirm(
        draft: UUID, stage: Stage, body: StageConfirm, request: Request, user: User
    ) -> Any:
        return await service(request).call(
            "POST",
            f"/drafts/{draft}/stages/{stage}/confirm",
            user,
            body.model_dump(mode="json"),
        )

    @app.post(
        "/api/v1/profile/drafts/{draft}/publish", response_model=ProfileReferenceRead
    )
    async def publish(
        draft: UUID, body: ProfileRevision, request: Request, user: User
    ) -> Any:
        return await service(request).publish(str(draft), body.revision, user)
