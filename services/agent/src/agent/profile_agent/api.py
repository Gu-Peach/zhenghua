"""Optional router for a future authenticated shared host. Importing it opens no service."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import Field

from src.domain.errors import AgentServiceError
from src.domain.models.common import StrictModel

from .models import (
    DraftCreate,
    DraftView,
    ExportReceipt,
    ProfileActor,
    ProfileError,
    ProfileEvent,
    ProfileReply,
    ProfileTurn,
    Proposal,
    ValidationReport,
)
from .service import ProfileAgent
from .validation import validate_draft


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
    if isinstance(error, ProfileError):
        return error.status, {"code": error.code, "message": error.message}
    if isinstance(error, AgentServiceError):
        if str(error.code).startswith("PROFILE_"):
            return 422, {"code": str(error.code), "message": "本地规则资源或指定版本不可用，请核对配置。"}
        return 502, {"code": str(error.code), "message": "规则助手模型请求失败，请检查配置或重试。"}
    return 500, {"code": "PROFILE_AGENT_FAILED", "message": "规则助手未完成，已提交修订仍保留，请刷新核对。"}


def create_profile_router(
    agent: ProfileAgent, actor_dependency: Callable[..., ProfileActor | Awaitable[ProfileActor]]
) -> APIRouter:
    """A trusted host must authenticate the caller and construct ProfileActor outside the body."""
    router = APIRouter(prefix="/v1/profile", tags=["profile-agent"])
    identity = Depends(actor_dependency)

    async def execute(call: Callable[[], Awaitable[Any]]) -> Any:
        try:
            return await call()
        except Exception as exc:
            status, detail = public_error(exc)
            raise HTTPException(status, detail) from exc

    @router.post("/drafts", response_model=DraftView)
    async def create(body: DraftCreate, actor: ProfileActor = identity) -> Any:
        return await execute(lambda: agent.create(body, actor))

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
