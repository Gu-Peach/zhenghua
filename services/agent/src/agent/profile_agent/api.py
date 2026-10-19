"""Optional router for a future authenticated shared host. Importing it opens no service."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import Field, ValidationError

from src.domain.errors import AgentServiceError
from src.domain.models.common import StrictModel

from .conversation import ConversationEvent, ConversationState, ConversationTurn, ProfileConversation
from .diagnostics import public_model_error
from .editing import ProfileEditor
from .models import (
    DraftCreate,
    DraftDeleteInput,
    DraftView,
    EditFilesInput,
    ExportReceipt,
    PdfSampleRequest,
    PdfSampleResult,
    ProfileActor,
    ProfileEditState,
    ProfileError,
    ProfileEvent,
    ProfileImport,
    ProfileReply,
    ProfileTurn,
    Proposal,
    ValidationReport,
)
from .pdf_sampling import PdfSamplingTool
from .service import ProfileAgent
from .validation import validate_draft
from .wizard import ProfileWizard, Stage, StageConfirm, StageGenerate, WizardState


class RevisionInput(StrictModel):
    revision: int = Field(ge=1)


class ConfirmInput(RevisionInput):
    accepted: bool


class ExpectedInput(RevisionInput):
    files: dict[str, str] = Field(min_length=1, max_length=40)


class ImageInput(RevisionInput):
    image_id: UUID = Field(default_factory=uuid4)
    filename: str = Field(min_length=1, max_length=200)
    content_base64: str = Field(min_length=1, max_length=14 * 1024 * 1024)


def public_error(error: Exception) -> tuple[int, dict[str, str]]:
    logging.getLogger(__name__).error(
        "Profile request failed type=%s code=%s diagnostic_id=%s",
        type(error).__name__,
        getattr(error, "code", "PROFILE_AGENT_FAILED"),
        getattr(error, "details", {}).get("diagnostic_id", "unavailable"),
    )
    if isinstance(error, ProfileError):
        return error.status, {"code": error.code, "message": error.message}
    if isinstance(error, ValidationError):
        fields = [".".join(map(str, item["loc"])) for item in error.errors(include_input=False)[:8]]
        return 422, {
            "code": "EXPECTED_SCHEMA_INVALID",
            "message": "答案字段格式不正确，请核对：" + "、".join(fields),
        }
    if isinstance(error, AgentServiceError):
        if str(error.code).startswith("PROFILE_"):
            return 422, {"code": str(error.code), "message": "本地规则资源或指定版本不可用，请核对配置。"}
        return 502, public_model_error(error)
    return 500, {"code": "PROFILE_AGENT_FAILED", "message": "规则助手未完成，已提交修订仍保留，请刷新核对。"}


def create_profile_router(
    agent: ProfileAgent, actor_dependency: Callable[..., ProfileActor | Awaitable[ProfileActor]]
) -> APIRouter:
    """A trusted host must authenticate the caller and construct ProfileActor outside the body."""
    router = APIRouter(prefix="/v1/profile", tags=["profile-agent"])
    identity = Depends(actor_dependency)
    wizard = ProfileWizard(agent)
    conversation = ProfileConversation(wizard)
    pdf_sampling = PdfSamplingTool(agent.store)
    editor = ProfileEditor(agent.store)

    @router.post("/imports", response_model=ProfileEditState)
    async def import_profile(body: ProfileImport, actor: ProfileActor = identity) -> Any:
        return await execute(lambda: asyncio.to_thread(editor.import_profile, body, actor))

    @router.get("/drafts/{draft}/editor", response_model=ProfileEditState)
    async def editor_state(draft: UUID, actor: ProfileActor = identity) -> Any:
        return await execute(lambda: asyncio.to_thread(editor.state, draft, actor))

    @router.post("/drafts/{draft}/editor/files", response_model=ProfileEditState)
    async def editor_save(draft: UUID, body: EditFilesInput, actor: ProfileActor = identity) -> Any:
        async def save() -> ProfileEditState:
            await asyncio.to_thread(editor.state, draft, actor)
            await asyncio.to_thread(
                agent.store.edit,
                draft,
                actor,
                body.revision,
                f"manual:{body.operation_id}",
                body.edits,
                "explicit_instruction",
            )
            return await asyncio.to_thread(editor.state, draft, actor)

        return await execute(save)

    @router.post("/drafts/{draft}/editor/accept", response_model=ProfileEditState)
    async def editor_accept(draft: UUID, body: RevisionInput, actor: ProfileActor = identity) -> Any:
        return await execute(lambda: asyncio.to_thread(editor.accept, draft, actor, body.revision))

    async def execute(call: Callable[[], Awaitable[Any]]) -> Any:
        try:
            return await call()
        except Exception as exc:
            status, detail = public_error(exc)
            raise HTTPException(status, detail) from exc

    @router.post("/drafts", response_model=DraftView)
    async def create(body: DraftCreate, actor: ProfileActor = identity) -> Any:
        return await execute(lambda: agent.create(body, actor))

    @router.get("/drafts", response_model=list[DraftView])
    async def drafts(actor: ProfileActor = identity) -> Any:
        return await execute(lambda: asyncio.to_thread(agent.store.list_drafts, actor))

    @router.delete("/drafts/{draft}", status_code=204)
    async def delete_draft(
        draft: UUID, body: DraftDeleteInput, actor: ProfileActor = identity
    ) -> Response:
        await execute(lambda: asyncio.to_thread(agent.store.delete, draft, actor, body.revision))
        return Response(status_code=204)

    @router.get("/drafts/{draft}/wizard", response_model=WizardState)
    async def state(draft: UUID, actor: ProfileActor = identity) -> Any:
        return await execute(lambda: asyncio.to_thread(wizard.state, draft, actor))

    @router.post("/drafts/{draft}/pdf-samples", response_model=PdfSampleResult)
    async def sample_pdf(draft: UUID, body: PdfSampleRequest, actor: ProfileActor = identity) -> Any:
        return await execute(lambda: asyncio.to_thread(pdf_sampling.sample, draft, body, actor))

    @router.get("/drafts/{draft}/conversation", response_model=ConversationState)
    async def conversation_state(draft: UUID, actor: ProfileActor = identity) -> Any:
        return await execute(lambda: asyncio.to_thread(conversation.state, draft, actor))

    @router.post("/drafts/{draft}/conversation/turns", response_model=ConversationState)
    async def conversation_turn(draft: UUID, body: ConversationTurn, actor: ProfileActor = identity) -> Any:
        return await execute(lambda: conversation.turn(draft, body, actor))

    @router.post("/drafts/{draft}/conversation/turns/stream", response_class=StreamingResponse)
    async def conversation_stream(
        draft: UUID, body: ConversationTurn, request: Request, actor: ProfileActor = identity
    ) -> StreamingResponse:
        await execute(lambda: asyncio.to_thread(agent.store.get, draft, actor))

        async def events() -> AsyncIterator[str]:
            queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=16)

            async def emit(event: ConversationEvent) -> None:
                await queue.put(
                    {"event": event.type, "data": event.model_dump(mode="json", exclude_none=True)}
                )

            async def run() -> None:
                try:
                    await conversation.turn(draft, body, actor, emit)
                except Exception as exc:
                    status, detail = public_error(exc)
                    await queue.put({"event": "error", "data": {"status": status, **detail}})

            task = asyncio.create_task(run())
            try:
                while True:
                    if await request.is_disconnected():
                        return
                    try:
                        event = await asyncio.wait_for(queue.get(), 1)
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"
                        continue
                    data = json.dumps(event["data"], ensure_ascii=False)
                    yield f"event: {event['event']}\ndata: {data}\n\n"
                    if event["event"] in {"completed", "error"}:
                        return
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/drafts/{draft}/stages/{stage}/generate", response_model=WizardState)
    async def generate(draft: UUID, stage: Stage, body: StageGenerate, actor: ProfileActor = identity) -> Any:
        return await execute(lambda: wizard.generate(draft, stage, body, actor))

    @router.post("/drafts/{draft}/stages/{stage}/confirm", response_model=WizardState)
    async def stage_confirm(
        draft: UUID, stage: Stage, body: StageConfirm, actor: ProfileActor = identity
    ) -> Any:
        return await execute(lambda: asyncio.to_thread(wizard.confirm, draft, stage, body, actor))

    @router.get("/drafts/{draft}/images/{image_id}", response_model=dict[str, str])
    async def pixels(draft: UUID, image_id: UUID, actor: ProfileActor = identity) -> Any:
        async def read_image() -> Any:
            view = await asyncio.to_thread(agent.store.get, draft, actor)
            asset = next((a for a in view.attachments if a.id == image_id), None)
            if asset is None:
                raise ProfileError("IMAGE_NOT_FOUND", "草稿中没有此图片", 404)
            return (await asyncio.to_thread(agent.store.images, draft, actor, [asset.path]))[0]

        return await execute(read_image)

    @router.post("/drafts/{draft}/publication")
    async def publication(draft: UUID, body: RevisionInput, actor: ProfileActor = identity) -> Any:
        async def package() -> Any:
            receipt = await agent.export(draft, body.revision, actor)
            from pathlib import Path

            content = await asyncio.to_thread(Path(receipt.archive_path).read_bytes)
            if len(content) > 30 * 1024 * 1024:
                raise ProfileError("PACKAGE_TOO_LARGE", "发布包不能超过30MiB", 413)
            view = await asyncio.to_thread(agent.store.get, draft, actor)
            if view.revision != body.revision:
                raise ProfileError("VERSION_CONFLICT", "导出期间草稿已更新", 409)
            return {
                "key": receipt.key,
                "version": receipt.version,
                "display_name": view.template.display_name if view.template else receipt.key,
                "checksum": receipt.checksum,
                "content_base64": base64.b64encode(content).decode(),
                "source": view.source,
            }

        return await execute(package)

    @router.get("/drafts/{draft}", response_model=DraftView)
    async def get(draft: UUID, actor: ProfileActor = identity) -> Any:
        return await execute(lambda: asyncio.to_thread(agent.store.get, draft, actor))

    @router.get("/drafts/{draft}/files")
    async def read(
        draft: UUID,
        path: str,
        actor: ProfileActor = identity,
        offset: int = Query(0, ge=0),
        limit: int = Query(16000, ge=1, le=40000),
    ) -> Any:
        return await execute(lambda: asyncio.to_thread(agent.store.read, draft, actor, path, offset, limit))

    @router.post("/drafts/{draft}/images", response_model=DraftView)
    async def image(draft: UUID, body: ImageInput, actor: ProfileActor = identity) -> Any:
        try:
            content = base64.b64decode(body.content_base64, validate=True)
        except binascii.Error as exc:
            raise HTTPException(422, {"code": "INVALID_IMAGE", "message": "图片Base64无效"}) from exc
        return await execute(
            lambda: asyncio.to_thread(
                agent.store.attach, draft, actor, body.revision, body.image_id, body.filename, content
            )
        )

    @router.post("/drafts/{draft}/turns", response_model=ProfileReply)
    async def ask(draft: UUID, body: ProfileTurn, actor: ProfileActor = identity) -> Any:
        return await execute(lambda: agent.ask(draft, body, actor))

    @router.post(
        "/drafts/{draft}/turns/stream",
        response_class=StreamingResponse,
        responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
    )
    async def stream(
        draft: UUID, body: ProfileTurn, request: Request, actor: ProfileActor = identity
    ) -> StreamingResponse:
        await execute(lambda: asyncio.to_thread(agent.store.get, draft, actor))

        async def generate() -> AsyncIterator[str]:
            queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=16)

            async def emit(event: ProfileEvent) -> None:
                await queue.put(
                    {"event": event.type, "data": event.model_dump(mode="json", exclude_none=True)}
                )

            async def run() -> None:
                try:
                    await agent.ask(draft, body, actor, on_event=emit)
                except Exception as exc:
                    status, detail = public_error(exc)
                    await queue.put({"event": "error", "data": {"status": status, **detail}})

            task = asyncio.create_task(run())
            try:
                while True:
                    if await request.is_disconnected():
                        return
                    try:
                        event = await asyncio.wait_for(queue.get(), 1)
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"
                        continue
                    data = json.dumps(event["data"], ensure_ascii=False)
                    yield f"event: {event['event']}\ndata: {data}\n\n"
                    if event["event"] in {"completed", "error"}:
                        return
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get("/drafts/{draft}/proposals/{proposal}", response_model=Proposal)
    async def proposal(draft: UUID, proposal: UUID, actor: ProfileActor = identity) -> Any:
        return await execute(lambda: asyncio.to_thread(agent.store.proposal, draft, actor, proposal))

    @router.post("/drafts/{draft}/proposals/{proposal}/confirm", response_model=DraftView)
    async def confirm(draft: UUID, proposal: UUID, body: ConfirmInput, actor: ProfileActor = identity) -> Any:
        return await execute(lambda: agent.confirm(draft, proposal, body.revision, body.accepted, actor))

    @router.post("/drafts/{draft}/expected/confirm", response_model=DraftView)
    async def expected(draft: UUID, body: ExpectedInput, actor: ProfileActor = identity) -> Any:
        return await execute(
            lambda: asyncio.to_thread(agent.store.confirm_expected, draft, actor, body.revision, body.files)
        )

    @router.get("/drafts/{draft}/validation", response_model=ValidationReport)
    async def validation(draft: UUID, actor: ProfileActor = identity) -> Any:
        async def validate() -> ValidationReport:
            root, meta = await asyncio.to_thread(agent.store.root_for, draft, actor)
            return await asyncio.to_thread(validate_draft, root, meta)

        return await execute(validate)

    @router.get("/drafts/{draft}/audit")
    async def audit(draft: UUID, actor: ProfileActor = identity) -> Any:
        return await execute(lambda: asyncio.to_thread(agent.store.audit, draft, actor))

    @router.post("/drafts/{draft}/export", response_model=ExportReceipt)
    async def export(draft: UUID, body: RevisionInput, actor: ProfileActor = identity) -> Any:
        return await execute(lambda: agent.export(draft, body.revision, actor))

    return router
