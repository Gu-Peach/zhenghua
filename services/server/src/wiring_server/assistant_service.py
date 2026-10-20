from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid5

from fastapi.responses import StreamingResponse

from .agent_bridge import AgentBridge
from .assistant_attachments import AssistantAttachments
from .assistant_completion import AssistantCompletion
from .assistant_contract import (
    AssistantEvent,
    AssistantInternalTurn,
    AssistantScope,
    AssistantTurnInput,
)
from .assistant_evidence import AssistantEvidence
from .assistant_history import build_history
from .assistant_store import AssistantStore
from .repository import Repository, ServiceError


def frame(event: AssistantEvent) -> str:
    return f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"


class AssistantService:
    def __init__(self, db: Repository) -> None:
        self.db, self.store = db, AssistantStore(db)

    async def stream(
        self, conversation: str, body: AssistantTurnInput, user: str
    ) -> StreamingResponse:
        saved = await self.store.get(conversation, user)
        scope = body.scope if body.scope.project_id else saved.context
        if scope.project_id:
            scope, _ = await AssistantEvidence(self.db).resolve(scope, user)
        assets = await AssistantAttachments(self.db).rows(
            conversation, list(map(str, body.attachment_ids)), user
        )
        turn, token = await self.store.begin(conversation, user, body)
        if turn["status"] == "completed":

            async def replay() -> AsyncIterator[str]:
                completed = next(
                    (
                        event
                        for event in reversed(turn["events"])
                        if event["type"] == "completed"
                    ),
                    None,
                )
                if (
                    not completed
                    or (completed.get("data") or {}).get("completion_verified")
                    is not True
                ):
                    yield frame(
                        AssistantEvent(
                            turn_id=body.turn_id,
                            type="error",
                            message="历史回复没有执行核验记录，请重新发送需求；旧回复不会创建真实重扫任务。",
                        )
                    )
                    yield frame(
                        AssistantEvent(
                            turn_id=body.turn_id,
                            type="completed",
                            data={"status": "failed"},
                        )
                    )
                    return
                for event in turn["events"]:
                    yield frame(AssistantEvent.model_validate(event))

            return StreamingResponse(replay(), media_type="text/event-stream")
        history = await build_history(self.db, saved, scope, body.turn_id, user)
        internal = AssistantInternalTurn(
            conversation_id=UUID(conversation),
            turn_id=body.turn_id,
            message=body.message,
            scope=scope,
            history=history[-24:],
            attachments=[
                {
                    k: v
                    for k, v in asset.items()
                    if k
                    in {
                        "id",
                        "filename",
                        "mime_type",
                        "role",
                        "pdf_page_number",
                        "project_id",
                    }
                }
                for asset in assets
            ],
        )
        # Freeze the resolved visible scope before tools run; it cannot come from model text.
        await self.db.update(
            "assistant_conversations",
            {"id": f"eq.{conversation}", "owner_id": f"eq.{user}"},
            {"context": scope.model_dump(mode="json")},
        )

        async def events() -> AsyncIterator[str]:
            collected: list[dict[str, Any]] = []
            pending_answer: list[AssistantEvent] = []
            verifier = AssistantCompletion(self.db, turn)
            answer, error, outcome = "", None, "failed"
            response = None
            try:
                response = await AgentBridge(self.db).open(
                    "POST",
                    "/v1/assistant/turns/stream",
                    headers={"X-Assistant-Turn-Token": token},
                    json=internal.model_dump(mode="json"),
                )
                lines: list[str] = []
                async for line in response.aiter_lines():
                    if line:
                        lines.append(line)
                        continue
                    data = "\n".join(
                        value[5:].lstrip()
                        for value in lines
                        if value.startswith("data:")
                    )
                    lines = []
                    if not data:
                        continue
                    event = AssistantEvent.model_validate_json(data)
                    if event.turn_id != body.turn_id:
                        raise ValueError("turn mismatch")
                    if len(collected) + len(pending_answer) >= 1000:
                        raise ValueError("event limit")
                    if event.type == "answer_delta":
                        pending_answer.append(event)
                        continue
                    elif event.type == "task_started":
                        event.data = await verifier.rescan(event.data)
                    elif event.type == "error":
                        error = event.message or "主助手未完成"
                    elif event.type == "completed":
                        outcome = "failed" if error else "completed"
                        if not error:
                            verified_rescan = await verifier.completed(event.data)
                            if verified_rescan:
                                pending_answer = [
                                    AssistantEvent(
                                        id=uuid5(
                                            body.turn_id, "verified-rescan-answer"
                                        ),
                                        turn_id=body.turn_id,
                                        type="answer_delta",
                                        message=verified_rescan.get("verified_answer")
                                        or verifier.rescan_answer(verified_rescan),
                                    )
                                ]
                            for delta in pending_answer:
                                answer += delta.message or ""
                                collected.append(delta.model_dump(mode="json"))
                                yield frame(delta)
                        pending_answer.clear()
                    collected.append(event.model_dump(mode="json"))
                    # Completion is emitted after the durable finish below.
                    if event.type != "completed":
                        yield frame(event)
                if outcome != "completed" and not error:
                    raise ValueError("stream incomplete")
            except asyncio.CancelledError:
                outcome, error = "cancelled", "本轮对话已停止；已创建任务仍可查询"
                raise
            except Exception as exc:  # noqa: BLE001 -- persist a safe terminal SSE error, including transport failures
                outcome = "failed"
                error = (
                    exc.message
                    if isinstance(exc, ServiceError)
                    else "主助手响应中断，可重试本轮；已创建任务仍可查询"
                )
                logging.getLogger(__name__).warning(
                    "Assistant turn failed turn=%s type=%s",
                    body.turn_id,
                    type(exc).__name__,
                )
                event = AssistantEvent(
                    id=uuid5(body.turn_id, "server-error"),
                    turn_id=body.turn_id,
                    type="error",
                    message=error,
                )
                collected.append(event.model_dump(mode="json"))
                yield frame(event)
            finally:
                if response is not None:
                    await response.aclose()
                context = await self.store.owned(
                    "assistant_conversations", conversation, user
                )
                await self.store.finish(
                    turn,
                    token,
                    outcome,
                    collected,
                    answer,
                    error,
                    AssistantScope.model_validate(context.get("context") or {}),
                )
            yield frame(
                AssistantEvent(
                    id=uuid5(body.turn_id, "server-completed"),
                    turn_id=body.turn_id,
                    type="completed",
                    data={"status": outcome},
                )
            )

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
