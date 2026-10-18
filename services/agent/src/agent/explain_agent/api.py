"""Mount into an authenticated host; this module opens no port or database connection."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.domain.enums import ErrorCode
from src.domain.errors import AgentServiceError
from src.harness.model_gateway import ModelGatewayError

from .models import ExplainActor, ExplainError, ExplainEvent, ExplainResponse, ExplainTurn
from .service import ExplainAgent

ActorDependency = Callable[..., ExplainActor | Awaitable[ExplainActor]]


def _public_error(error: Exception, turn: ExplainTurn | None = None) -> tuple[int, dict[str, str]]:
    """Expose bounded error categories and log identifiers, never upstream bodies or credentials."""
    upstream_status = error.details.get("status_code") if isinstance(error, AgentServiceError) else None
    logging.getLogger(__name__).error(
        "Explain request failed turn=%s project=%s type=%s code=%s upstream_status=%s stream_error=%s",
        turn.turn_id if turn else None,
        turn.project_id if turn else None,
        type(error).__name__,
        error.code if isinstance(error, (AgentServiceError, ExplainError)) else "EXPLAIN_FAILED",
        upstream_status if type(upstream_status) is int else None,
        isinstance(error, ModelGatewayError) and error.details.get("failure_kind") == "provider_stream_error",
    )
    if isinstance(error, ExplainError):
        return error.status, {"code": error.code, "message": error.message}
    if isinstance(error, ModelGatewayError):
        if error.details.get("failure_kind") == "provider_stream_error":
            message = "模型服务在流式响应中返回错误，请联系模型服务方检查，或切换可用模型后重试。"
        elif error.code == ErrorCode.MODEL_SCHEMA_INVALID:
            message = "模型返回的回答或工具调用格式无效，请重试；重复失败时检查模型的工具调用兼容性。"
        elif type(upstream_status) is int:
            reason = {
                401: "模型鉴权失败",
                403: "当前令牌无权访问模型",
                413: "模型请求或图片超出服务限制",
                429: "模型服务限流",
            }.get(upstream_status, "模型服务拒绝请求" if upstream_status < 500 else "模型服务暂时不可用")
            message = f"{reason}（HTTP {upstream_status}），请检查配置或稍后重试。"
        else:
            message = "模型请求超时、连接中断或服务暂不可用，请稍后重试。"
        return 502, {"code": "EXPLAIN_UPSTREAM_FAILED", "message": message}
    if isinstance(error, AgentServiceError):
        return 502, {
            "code": "EXPLAIN_UPSTREAM_FAILED",
            "message": "数据服务读取失败，请检查数据库与图纸存储服务后重试。",
        }
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
            status, detail = _public_error(exc, body)
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
                    status, detail = _public_error(exc, body)
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
