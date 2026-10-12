from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ...application.model_output_view import model_output_view
from ...application.run_read_models import stage_summary
from ...domain.enums import RunStatus, RunType
from ...domain.errors import AgentServiceError
from ...domain.models.imports import RunStageSummaryResponse
from ...domain.models.runs import CreateRunRequest
from ..dependencies import refresh_current_profiles
from ..schemas import HumanInputRequest, RunArtifactsResponse, RunEventsResponse, RunResponse

router = APIRouter(
    prefix="/v1/runs",
    tags=["runs"],
    dependencies=[Depends(refresh_current_profiles)],
)


def _raise_http(exc: AgentServiceError) -> None:
    status = 404 if exc.code.value == "PROJECT_CONTEXT_NOT_FOUND" else 409
    raise HTTPException(
        status_code=status,
        detail={
            "code": exc.code.value,
            "message": exc.message,
            "retryable": exc.retryable,
            "details": exc.details,
        },
    ) from exc


@router.post("", response_model=RunResponse, status_code=202)
async def create_run(
    payload: CreateRunRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1),
) -> RunResponse:
    try:
        run = await request.app.state.run_control.create(payload, idempotency_key)
    except AgentServiceError as exc:
        _raise_http(exc)
    return RunResponse(run=run)


@router.get("/{agent_run_id}", response_model=RunResponse)
async def get_run(agent_run_id: str, request: Request) -> RunResponse:
    try:
        run = await request.app.state.run_control.get_required(agent_run_id)
    except AgentServiceError as exc:
        _raise_http(exc)
    return RunResponse(run=run)


@router.get("/{agent_run_id}/events", response_model=RunEventsResponse)
async def get_run_events(
    agent_run_id: str,
    request: Request,
    after_seq: int = Query(default=-1, ge=-1),
) -> RunEventsResponse:
    try:
        await request.app.state.run_control.get_required(agent_run_id)
    except AgentServiceError as exc:
        _raise_http(exc)
    items = await request.app.state.run_control.events.list_after(agent_run_id, after_seq)
    return RunEventsResponse(items=items)


@router.get("/{agent_run_id}/events/stream")
async def stream_run_events(
    agent_run_id: str,
    request: Request,
    after_seq: int = Query(default=-1, ge=-1),
    last_event_id: int | None = Header(default=None, alias="Last-Event-ID", ge=-1),
) -> StreamingResponse:
    try:
        await request.app.state.run_control.get_required(agent_run_id)
    except AgentServiceError as exc:
        _raise_http(exc)

    async def generate() -> AsyncIterator[str]:
        cursor = max(after_seq, last_event_id if last_event_id is not None else -1)
        while not await request.is_disconnected():
            events = await request.app.state.run_control.events.list_after(agent_run_id, cursor)
            for event in events:
                cursor = event.seq
                yield (
                    f"id: {event.seq}\nevent: {event.event_type.value}\ndata: {event.model_dump_json()}\n\n"
                )
            run = await request.app.state.run_control.get_required(agent_run_id)
            if run.status in {
                RunStatus.SUCCEEDED,
                RunStatus.NEEDS_REVIEW,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.WAITING_INPUT,
            }:
                # Run may become terminal after the first fetch. Drain events committed
                # with its terminal transition, including batches above the REST row limit.
                remaining = await request.app.state.run_control.events.list_after(agent_run_id, cursor)
                if not remaining:
                    return
                for event in remaining:
                    cursor = event.seq
                    yield (
                        f"id: {event.seq}\nevent: {event.event_type.value}\n"
                        f"data: {event.model_dump_json()}\n\n"
                    )
                continue
            if not events:
                yield ": keep-alive\n\n"
                await asyncio.sleep(0.5)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{agent_run_id}/summary", response_model=RunStageSummaryResponse)
async def get_stage_summary(agent_run_id: str, user_id: str, request: Request) -> RunStageSummaryResponse:
    try:
        return await stage_summary(
            request.app.state.run_control,
            getattr(request.app.state, "durable_stages", None),
            agent_run_id,
            user_id,
        )
    except AgentServiceError as exc:
        _raise_http(exc)
    except PermissionError as exc:
        raise HTTPException(403, detail="Run access denied.") from exc
    raise AssertionError("unreachable")


@router.get("/{agent_run_id}/model-outputs")
async def get_model_outputs(agent_run_id: str, user_id: str, request: Request) -> dict[str, Any]:
    run = await request.app.state.run_control.get_required(agent_run_id)
    if run.requested_by != user_id:
        raise HTTPException(403, detail="Run model output access denied.")
    keys = [run.agent_run_id]
    if run.run_type == RunType.PROFILE_EVALUATION:
        dataset = await request.app.state.run_control.artifacts.get(f"{agent_run_id}:evaluation-dataset")
        if dataset:
            for checksum in (dataset["baseline_profile"]["checksum"], dataset["candidate_checksum"]):
                keys.extend(
                    f"{agent_run_id}:evaluation:{checksum}:{case['case_id']}" for case in dataset["cases"]
                )
    if run.run_type == RunType.IMPROVEMENT_CANDIDATE:
        keys += [
            f"improvement:{key}"
            for key in dict.fromkeys(
                [run.feedback_id or run.source_document_id] + run.options.correction_feedback_ids
            )
        ]
    items: list[dict[str, Any]] = []
    for key in keys:
        traces = await request.app.state.trace_store.list(key)
        items.extend(model_output_view(key, index, trace) for index, trace in enumerate(traces))
    return {"items": items, "reasoning_exposed": False}


@router.get("/{agent_run_id}/artifacts", response_model=RunArtifactsResponse)
async def get_run_artifacts(agent_run_id: str, request: Request) -> RunArtifactsResponse:
    try:
        await request.app.state.run_control.get_required(agent_run_id)
    except AgentServiceError as exc:
        _raise_http(exc)
    items = await request.app.state.run_control.artifacts.list_for_run(agent_run_id)
    return RunArtifactsResponse(items=[dict(item) for item in items])


@router.post("/{agent_run_id}/cancel", response_model=RunResponse)
async def cancel_run(agent_run_id: str, request: Request) -> RunResponse:
    try:
        run = await request.app.state.run_control.cancel(agent_run_id)
    except AgentServiceError as exc:
        _raise_http(exc)
    request.app.state.agent_worker.cancel(agent_run_id)
    return RunResponse(run=run)


@router.post("/{agent_run_id}/resume", response_model=RunResponse, status_code=202)
async def resume_run(agent_run_id: str, request: Request) -> RunResponse:
    try:
        run = await request.app.state.run_control.resume(agent_run_id)
    except AgentServiceError as exc:
        _raise_http(exc)
    return RunResponse(run=run)


@router.post("/{agent_run_id}/input", response_model=RunResponse, status_code=202)
async def provide_run_input(
    agent_run_id: str,
    payload: HumanInputRequest,
    request: Request,
) -> RunResponse:
    try:
        run = await request.app.state.run_control.provide_input(agent_run_id, payload.payload)
    except AgentServiceError as exc:
        _raise_http(exc)
    return RunResponse(run=run)
