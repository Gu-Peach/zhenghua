from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from ...application.supervisor_conversation import SupervisorConversationService
from ...domain.errors import AgentServiceError
from ...domain.models.supervisor import ConversationTurn, SupervisorUserEvent
from ...graphs.supervisor import run_supervisor_graph
from ...tools.event_presenter import SupervisorEventPresenter
from ..dependencies import require_internal_service
from ..schemas import SupervisorTurnResponse, SupervisorUserEventsResponse
from ..schemas.supervisor import ConversationAttachmentResponse, ConversationMemoryResponse

logger = logging.getLogger(__name__)


def _conversation_service(request: Request) -> SupervisorConversationService:
    service = getattr(request.app.state, "supervisor_conversations", None)
    if not isinstance(service, SupervisorConversationService):
        raise HTTPException(status_code=503, detail="Supervisor model is not configured.")
    return service


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail="Conversation or attachment access denied.")
    if isinstance(exc, AgentServiceError):
        return HTTPException(status_code=502, detail={"code": exc.code.value, "message": exc.message})
    return HTTPException(status_code=400, detail=str(exc))


router = APIRouter(
    prefix="/v1/supervisor",
    tags=["supervisor"],
    dependencies=[Depends(require_internal_service)],
)


@router.get("/runs/{agent_run_id}/events", response_model=SupervisorUserEventsResponse)
async def present_run_events(
    agent_run_id: str,
    conversation_id: str,
    request: Request,
    after_seq: int = 0,
) -> SupervisorUserEventsResponse:
    try:
        await request.app.state.run_control.get_required(agent_run_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Agent run not found.") from exc
    events = await request.app.state.run_control.events.list_after(agent_run_id, after_seq - 1)
    presenter = SupervisorEventPresenter()
    presented = []
    for event in events:
        artifact_payloads = []
        for artifact_ref in event.artifact_refs:
            artifact = await request.app.state.run_control.artifacts.get(artifact_ref)
            if artifact is not None:
                artifact_payloads.append(artifact)
        presented.append(
            presenter.present(
                event,
                conversation_id=conversation_id,
                artifact_payloads=artifact_payloads,
            )
        )
    return SupervisorUserEventsResponse(items=presented)


@router.post("/turns", response_model=SupervisorTurnResponse)
async def supervisor_turn(payload: ConversationTurn, request: Request) -> SupervisorTurnResponse:
    service = getattr(request.app.state, "supervisor_conversations", None)
    if isinstance(service, SupervisorConversationService):
        try:
            result = await service.turn(payload)
        except (ValueError, PermissionError, AgentServiceError) as exc:
            raise _http_error(exc) from exc
        return SupervisorTurnResponse(
            decision=result.decision, receipt=result.receipt, user_event=result.user_event
        )
    runtime = getattr(request.app.state, "supervisor_runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="Supervisor model is not configured.")
    result = await run_supervisor_graph(
        agent=runtime["agent"],
        workflows=runtime["workflows"],
        turn=payload,
    )
    return SupervisorTurnResponse(
        decision=result.decision,
        receipt=result.receipt,
        user_event=result.user_event,
    )


@router.post("/conversations/{conversation_id}/attachments", response_model=ConversationAttachmentResponse)
async def upload_conversation_pdf(
    conversation_id: str,
    user_id: str,
    filename: str,
    request: Request,
) -> ConversationAttachmentResponse:
    service = _conversation_service(request)
    limit = request.app.state.settings.profile_max_pdf_bytes
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > limit:
            raise HTTPException(status_code=413, detail="PDF exceeds the configured size limit.")
    try:
        payload = await service.upload_attachment(
            conversation_id=conversation_id,
            user_id=user_id,
            filename=filename,
            content=bytes(content),
        )
        return ConversationAttachmentResponse.model_validate(payload)
    except (ValueError, PermissionError) as exc:
        raise _http_error(exc) from exc


@router.get("/conversations/{conversation_id}", response_model=ConversationMemoryResponse)
async def get_conversation_memory(
    conversation_id: str,
    user_id: str,
    request: Request,
) -> ConversationMemoryResponse:
    try:
        return ConversationMemoryResponse.model_validate(
            _conversation_service(request).snapshot(conversation_id, user_id)
        )
    except (ValueError, PermissionError) as exc:
        raise _http_error(exc) from exc


@router.post("/turns/stream")
async def stream_supervisor_turn(payload: ConversationTurn, request: Request) -> StreamingResponse:
    service = _conversation_service(request)

    async def generate() -> AsyncIterator[str]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        async def present(event: SupervisorUserEvent) -> None:
            await queue.put({"event": "message", "data": event.model_dump(mode="json")})

        async def execute() -> None:
            try:
                result = await service.turn(payload, on_event=present)
                response = SupervisorTurnResponse(
                    decision=result.decision,
                    receipt=result.receipt,
                    user_event=result.user_event,
                )
                await queue.put({"event": "response", "data": response.model_dump(mode="json")})
            except (ValueError, PermissionError, AgentServiceError) as exc:
                error = _http_error(exc)
                await queue.put(
                    {"event": "error", "data": {"status": error.status_code, "detail": error.detail}}
                )
            except Exception:
                logger.exception("Supervisor conversation failed")
                await queue.put(
                    {"event": "error", "data": {"status": 500, "detail": "Supervisor processing failed."}}
                )

        task = asyncio.create_task(execute())
        try:
            while True:
                if await request.is_disconnected():
                    return
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"event: {item['event']}\ndata: {json.dumps(item['data'], ensure_ascii=False)}\n\n"
                if item["event"] in {"response", "error"}:
                    return
        finally:
            if not task.done():
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    return StreamingResponse(
        generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )
