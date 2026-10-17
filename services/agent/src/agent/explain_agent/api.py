"""Mount into an authenticated host; this module opens no port or database connection."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.domain.errors import AgentServiceError

from .models import ExplainActor, ExplainError, ExplainEvent, ExplainResponse, ExplainTurn
from .service import ExplainAgent

ActorDependency = Callable[..., ExplainActor | Awaitable[ExplainActor]]


def _public_error(error: Exception) -> tuple[int, dict[str, str]]:
    if isinstance(error, ExplainError):
        return error.status, {"code": error.code, "message": error.message}
    if isinstance(error, AgentServiceError):
        return 502, {"code": "EXPLAIN_UPSTREAM_FAILED", "message": "数据或模型服务暂不可用，请稍后重试。"}
    return 500, {"code": "EXPLAIN_FAILED", "message": "解释暂未完成，请重试。"}


def create_explain_router(
    agent: ExplainAgent | Callable[[], ExplainAgent], actor_dependency: ActorDependency
) -> APIRouter:
    """The host must verify JWT/internal identity before supplying ExplainActor."""
    router = APIRouter(prefix="/v1/explain", tags=["explain-agent"])
    identity = Depends(actor_dependency)

    def resolve() -> ExplainAgent:
        return agent() if callable(agent) else agent

    @router.post("/turns", response_model=ExplainResponse)
    async def turn(body: ExplainTurn, actor: ExplainActor = identity) -> ExplainResponse:
        try:
            return await resolve().ask(body, actor)
        except Exception as exc:
            status, detail = _public_error(exc)
            raise HTTPException(status, detail) from exc

    @router.post("/turns/stream")
    async def stream(
        body: ExplainTurn, request: Request, actor: ExplainActor = identity
    ) -> StreamingResponse:
        async def generate() -> AsyncIterator[str]:
            queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=16)

            async def emit(event: ExplainEvent) -> None:
                await queue.put(
                    {"event": event.type, "data": event.model_dump(mode="json", exclude_none=True)}
                )

            async def execute() -> None:
                try:
                    await resolve().ask(body, actor, on_event=emit)
                except Exception as exc:
                    status, detail = _public_error(exc)
                    await queue.put({"event": "error", "data": {"status": status, **detail}})

            task = asyncio.create_task(execute())
            try:
                while True:
                    if await request.is_disconnected():
                        return
                    try:
                        item = await asyncio.wait_for(queue.get(), timeout=1)
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"
                        continue
                    yield f"event: {item['event']}\ndata: {json.dumps(item['data'], ensure_ascii=False)}\n\n"
                    if item["event"] in {"completed", "error"}:
                        return
            finally:
                if not task.done():
                    task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
