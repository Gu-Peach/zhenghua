from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from ..domain.enums import AgentStage, ErrorCode, EventType, RunStatus
from ..domain.errors import AgentServiceError
from ..domain.models.runs import AgentEvent, AgentRun, CreateRunRequest, EventError
from ..domain.ports import ArtifactRepository, EventRepository, RunQueue, RunRepository


class RunEventPublisher:
    def __init__(self, events: EventRepository, runs: RunRepository | None = None) -> None:
        self._events = events
        self._runs = runs
        self._locks: dict[str, asyncio.Lock] = {}

    async def publish(
        self,
        run: AgentRun,
        event_type: EventType,
        *,
        stage: AgentStage | None = None,
        message: str = "",
        metrics: dict[str, int | float | str | bool | None] | None = None,
        artifact_refs: list[str] | None = None,
        error: EventError | None = None,
    ) -> AgentEvent:
        lock = self._locks.setdefault(run.agent_run_id, asyncio.Lock())
        async with lock:
            if event_type == EventType.STAGE_STARTED and stage is not None:
                run.current_stage = stage
                if self._runs is not None:
                    await self._runs.save(run)
            existing = await self._events.list_after(run.agent_run_id)
            event = AgentEvent(
                agent_run_id=run.agent_run_id,
                seq=max((item.seq for item in existing), default=-1) + 1,
                event_type=event_type,
                stage=stage,
                scope=run.scope,
                message=message,
                metrics=metrics or {},
                artifact_refs=artifact_refs or [],
                error=error,
            )
            return await self._events.append(event)

    async def has_event(self, agent_run_id: str, event_type: EventType) -> bool:
        events = await self._events.list_after(agent_run_id)
        return any(event.event_type == event_type for event in events)


class RunControlService:
    def __init__(
        self,
        *,
        runs: RunRepository,
        events: EventRepository,
        artifacts: ArtifactRepository,
        queue: RunQueue,
    ) -> None:
        self.runs = runs
        self.events = events
        self.artifacts = artifacts
        self.queue = queue
        self.publisher = RunEventPublisher(events, runs)

    async def create(self, request: CreateRunRequest, idempotency_key: str) -> AgentRun:
        run = await self.runs.create(request, idempotency_key)
        existing = await self.events.list_after(run.agent_run_id)
        if not existing:
            await self.publisher.publish(run, EventType.RUN_CREATED, message="run created")
            await self.queue.enqueue(run.agent_run_id)
        return run

    async def get_required(self, agent_run_id: str) -> AgentRun:
        run = await self.runs.get(agent_run_id)
        if run is None:
            raise AgentServiceError(
                ErrorCode.PROJECT_CONTEXT_NOT_FOUND,
                f"Agent run {agent_run_id!r} was not found.",
                retryable=False,
            )
        return run

    async def cancel(self, agent_run_id: str) -> AgentRun:
        run = await self.get_required(agent_run_id)
        if run.status in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}:
            return run
        run.status = RunStatus.CANCELLED
        await self.runs.save(run)
        await self.publisher.publish(run, EventType.RUN_CANCELLED, message="run cancelled")
        return run

    async def resume(self, agent_run_id: str) -> AgentRun:
        run = await self.get_required(agent_run_id)
        if run.status not in {RunStatus.FAILED, RunStatus.WAITING_INPUT, RunStatus.NEEDS_REVIEW}:
            raise AgentServiceError(
                ErrorCode.INVALID_REQUEST,
                f"Run in status {run.status.value} cannot be resumed.",
                retryable=False,
            )
        run.status = RunStatus.QUEUED
        run.error = None
        await self.runs.save(run)
        await self.queue.enqueue(run.agent_run_id)
        return run

    async def provide_input(self, agent_run_id: str, payload: dict[str, Any]) -> AgentRun:
        run = await self.get_required(agent_run_id)
        if run.status != RunStatus.WAITING_INPUT:
            raise AgentServiceError(
                ErrorCode.INVALID_REQUEST,
                "Human input is only accepted for WAITING_INPUT runs.",
                retryable=False,
            )
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16]
        artifact_id = f"{run.agent_run_id}:human-input:{digest}"
        await self.artifacts.put(
            artifact_id,
            {
                "artifact_id": artifact_id,
                "agent_run_id": run.agent_run_id,
                "kind": "human_input",
                "payload": payload,
            },
        )
        profile_key = payload.get("profile_key")
        if isinstance(profile_key, str) and profile_key.strip():
            run.profile_hint = profile_key.strip()
        expected_version = payload.get("expected_result_version")
        if isinstance(expected_version, int) and expected_version >= 0:
            run.expected_result_version = expected_version
        run.status = RunStatus.QUEUED
        await self.runs.save(run)
        await self.queue.enqueue(run.agent_run_id)
        return run
