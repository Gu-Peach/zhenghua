from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, cast

from ..domain.enums import ErrorCode, RunStatus
from ..domain.errors import AgentServiceError
from ..domain.models.proposals import ResultProposal
from ..domain.models.runs import AgentEvent, AgentRun, CreateRunRequest


def checkpoint_key(run_id: str, graph: str, node: str, item_id: str) -> str:
    values = (run_id, graph, node, item_id)
    if any(not value.strip() for value in values):
        raise ValueError("Checkpoint key parts cannot be empty.")
    return ":".join(value.strip() for value in values)


class CancellationToken:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise AgentServiceError(ErrorCode.RUN_CANCELLED, "Run was cancelled.", retryable=False)


class InMemoryRunRepository:
    def __init__(self) -> None:
        self._runs: dict[str, AgentRun] = {}
        self._idempotency: dict[str, tuple[str, str]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _fingerprint(request: CreateRunRequest) -> str:
        payload = request.model_dump_json(exclude_none=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def create(self, request: CreateRunRequest, idempotency_key: str) -> AgentRun:
        if not idempotency_key.strip():
            raise ValueError("idempotency_key is required.")
        fingerprint = self._fingerprint(request)
        async with self._lock:
            existing = self._idempotency.get(idempotency_key)
            if existing is not None:
                existing_fingerprint, run_id = existing
                if existing_fingerprint != fingerprint:
                    raise AgentServiceError(
                        ErrorCode.INVALID_REQUEST,
                        "Idempotency key was reused with a different request.",
                        retryable=False,
                    )
                return self._runs[run_id].model_copy(deep=True)
            run = AgentRun.from_request(request, idempotency_key)
            self._runs[run.agent_run_id] = run
            self._idempotency[idempotency_key] = (fingerprint, run.agent_run_id)
            return run.model_copy(deep=True)

    async def get(self, agent_run_id: str) -> AgentRun | None:
        async with self._lock:
            run = self._runs.get(agent_run_id)
            return run.model_copy(deep=True) if run else None

    async def save(self, run: AgentRun) -> None:
        async with self._lock:
            current = self._runs.get(run.agent_run_id)
            if (
                current is not None
                and current.status == RunStatus.CANCELLED
                and run.status != RunStatus.CANCELLED
            ):
                raise AgentServiceError(
                    ErrorCode.RUN_CANCELLED,
                    "A cancelled run cannot transition to another status.",
                    retryable=False,
                )
            self._runs[run.agent_run_id] = run.model_copy(deep=True)


class InMemoryEventRepository:
    def __init__(self) -> None:
        self._events: dict[str, list[AgentEvent]] = {}
        self._event_ids: set[str] = set()
        self._lock = asyncio.Lock()

    async def append(self, event: AgentEvent) -> AgentEvent:
        async with self._lock:
            if event.event_id in self._event_ids:
                existing = next(
                    item
                    for item in self._events.get(event.agent_run_id, [])
                    if item.event_id == event.event_id
                )
                return existing.model_copy(deep=True)
            events = self._events.setdefault(event.agent_run_id, [])
            if any(existing.seq == event.seq for existing in events):
                raise AgentServiceError(
                    ErrorCode.CHECKPOINT_CONFLICT,
                    f"Event sequence {event.seq} already exists for this run.",
                    retryable=False,
                )
            events.append(event.model_copy(deep=True))
            events.sort(key=lambda item: item.seq)
            self._event_ids.add(event.event_id)
            return event.model_copy(deep=True)

    async def list_after(self, agent_run_id: str, after_seq: int = -1) -> list[AgentEvent]:
        async with self._lock:
            return [
                event.model_copy(deep=True)
                for event in self._events.get(agent_run_id, [])
                if event.seq > after_seq
            ]


class InMemoryCheckpointStore:
    def __init__(self) -> None:
        self._values: dict[str, tuple[int, dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    async def load(self, key: str) -> Mapping[str, Any] | None:
        async with self._lock:
            current = self._values.get(key)
            if current is None:
                return None
            revision, value = current
            return {"revision": revision, "value": deepcopy(value)}

    async def save(
        self,
        key: str,
        value: Mapping[str, Any],
        expected_revision: int | None = None,
    ) -> int:
        async with self._lock:
            current_revision = self._values.get(key, (0, {}))[0]
            if expected_revision is not None and expected_revision != current_revision:
                raise AgentServiceError(
                    ErrorCode.CHECKPOINT_CONFLICT,
                    f"Checkpoint revision mismatch: expected {expected_revision}, got {current_revision}.",
                    retryable=False,
                )
            next_revision = current_revision + 1
            self._values[key] = (next_revision, deepcopy(dict(value)))
            return next_revision


class InMemoryTraceStore:
    def __init__(self) -> None:
        self._traces: dict[str, list[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    async def append(self, run_id: str, trace: Mapping[str, Any]) -> None:
        async with self._lock:
            self._traces.setdefault(run_id, []).append(deepcopy(dict(trace)))

    async def list(self, run_id: str) -> list[Mapping[str, Any]]:
        async with self._lock:
            return cast(
                list[Mapping[str, Any]],
                deepcopy(self._traces.get(run_id, [])),
            )


class InMemoryArtifactRepository:
    def __init__(self) -> None:
        self._artifacts: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def put(self, artifact_id: str, payload: Mapping[str, Any]) -> None:
        if not artifact_id.strip():
            raise ValueError("artifact_id is required.")
        value = deepcopy(dict(payload))
        run_id = value.get("agent_run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("Artifacts require agent_run_id.")
        async with self._lock:
            current = self._artifacts.get(artifact_id)
            if current is not None and current != value:
                raise AgentServiceError(
                    ErrorCode.CHECKPOINT_CONFLICT,
                    f"Artifact {artifact_id!r} already exists with different content.",
                    retryable=False,
                )
            self._artifacts[artifact_id] = value

    async def get(self, artifact_id: str) -> Mapping[str, Any] | None:
        async with self._lock:
            value = self._artifacts.get(artifact_id)
            return deepcopy(value) if value is not None else None

    async def list_for_run(self, agent_run_id: str) -> list[Mapping[str, Any]]:
        async with self._lock:
            return [
                deepcopy(value)
                for value in self._artifacts.values()
                if value.get("agent_run_id") == agent_run_id
            ]


class InMemoryProposalRepository:
    def __init__(self) -> None:
        self._proposals: dict[str, ResultProposal] = {}
        self._lock = asyncio.Lock()

    async def submit(self, proposal: ResultProposal) -> str:
        async with self._lock:
            existing = self._proposals.get(proposal.proposal_id)
            if existing is not None and existing != proposal:
                raise AgentServiceError(
                    ErrorCode.CHECKPOINT_CONFLICT,
                    f"Proposal {proposal.proposal_id!r} already exists with different content.",
                    retryable=False,
                )
            self._proposals[proposal.proposal_id] = proposal.model_copy(deep=True)
        return proposal.proposal_id

    async def get(self, proposal_id: str) -> ResultProposal | None:
        async with self._lock:
            proposal = self._proposals.get(proposal_id)
            return proposal.model_copy(deep=True) if proposal is not None else None
