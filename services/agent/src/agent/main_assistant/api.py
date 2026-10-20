from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.api.dependencies import require_internal_service
from src.config import AgentSettings

from .models import AssistantEvent, AssistantInternalTurn
from .service import MainAssistant, RemoteExecutor, create_main_assistant


def create_assistant_router(settings: AgentSettings, agent: MainAssistant | None = None) -> APIRouter:
    router = APIRouter(prefix="/v1/assistant", dependencies=[Depends(require_internal_service)])

    @router.get("/capabilities")
    async def capabilities() -> dict[str, bool]:
        return {"available": agent is not None or settings.model_configured}

    @router.post("/turns/stream")
    async def stream(
        body: AssistantInternalTurn,
        request: Request,
        token: Annotated[str, Header(alias="X-Assistant-Turn-Token", min_length=32)],
    ) -> StreamingResponse:
        try:
            runtime = agent or create_main_assistant(settings)
        except ValueError as exc:
            raise HTTPException(503, {"code": "ASSISTANT_NOT_CONFIGURED", "message": str(exc)}) from exc

        async def events() -> AsyncIterator[str]:
            queue: asyncio.Queue[AssistantEvent | None] = asyncio.Queue(maxsize=32)

            async def emit(event: AssistantEvent) -> None:
                await queue.put(event)

            async def execute() -> None:
                try:
                    await runtime.ask(body, RemoteExecutor(settings, body.turn_id, token), emit)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    await emit(
                        AssistantEvent(
                            turn_id=body.turn_id,
                            type="error",
                            message="主助手处理未完成，请检查模型/服务状态；已创建任务可在会话中查询。",
                        )
                    )
                await queue.put(None)

            task = asyncio.create_task(execute())
            try:
                while True:
                    item = await queue.get()
                    if item is None or await request.is_disconnected():
                        break
                    payload = json.dumps(item.model_dump(mode="json"), ensure_ascii=False)
                    yield f"event: {item.type}\ndata: {payload}\n\n"
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

        return StreamingResponse(
            events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    return router
