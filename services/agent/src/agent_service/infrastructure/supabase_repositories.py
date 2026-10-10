from __future__ import annotations

import hashlib
import socket
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from ..domain.enums import ErrorCode, RunStatus
from ..domain.errors import AgentServiceError
from ..domain.models.common import utc_now
from ..domain.models.proposals import ResultProposal
from ..domain.models.runs import AgentEvent, AgentRun, CreateRunRequest
from .supabase_client import SupabaseClient


class SupabaseRunRepository:
    def __init__(self, client: SupabaseClient) -> None:
        self._client = client

    async def create(self, request: CreateRunRequest, idempotency_key: str) -> AgentRun:
        if not idempotency_key.strip():
            raise ValueError("idempotency_key is required.")
        fingerprint = hashlib.sha256(request.model_dump_json(exclude_none=False).encode("utf-8")).hexdigest()
        existing = await self._find_idempotent(request.project_id, idempotency_key)
        if existing is not None:
            self._validate_fingerprint(existing, fingerprint)
            return _run_from_row(existing)

        run = AgentRun.from_request(request, idempotency_key)
        rows = await self._client.insert("agent_runs", _run_to_row(run, fingerprint=fingerprint))
        if not rows:
            raise _missing_row("agent run")
        return _run_from_row(rows[0])

    async def get(self, agent_run_id: str) -> AgentRun | None:
        rows = await self._client.select(
            "agent_runs",
            params={"id": f"eq.{_uuid(agent_run_id)}", "limit": "1"},
        )
        return _run_from_row(rows[0]) if rows else None

    async def save(self, run: AgentRun) -> None:
        current = await self.get(run.agent_run_id)
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
        rows = await self._client.update(
            "agent_runs",
            _run_to_row(run, include_identity=False),
            filters={"id": f"eq.{_uuid(run.agent_run_id)}"},
        )
        if not rows:
            raise _missing_row("agent run")

    async def _find_idempotent(
        self,
        project_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        rows = await self._client.select(
            "agent_runs",
            params={
                "project_id": f"eq.{_uuid(project_id)}",
                "idempotency_key": f"eq.{idempotency_key}",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    @staticmethod
    def _validate_fingerprint(row: Mapping[str, Any], fingerprint: str) -> None:
        if row.get("request_fingerprint") != fingerprint:
            raise AgentServiceError(
                ErrorCode.INVALID_REQUEST,
                "Idempotency key was reused with a different request.",
                retryable=False,
            )


class SupabaseEventRepository:
    def __init__(self, client: SupabaseClient) -> None:
        self._client = client

    async def append(self, event: AgentEvent) -> AgentEvent:
        seq = await self._client.rpc(
            "append_agent_event",
            {
                "event_id": _uuid(event.event_id),
                "target_run_id": _uuid(event.agent_run_id),
                "event_type_value": event.event_type.value,
                "stage_value": event.stage.value if event.stage else None,
                "level_value": event.level,
                "scope_value": event.scope.model_dump(mode="json") if event.scope else None,
                "message_value": event.message,
                "metrics_value": event.metrics,
                "artifact_refs_value": event.artifact_refs,
                "error_value": event.error.model_dump(mode="json") if event.error else None,
                "occurred_at_value": event.occurred_at.isoformat(),
            },
        )
        return event.model_copy(update={"seq": int(seq)})

    async def list_after(self, agent_run_id: str, after_seq: int = -1) -> list[AgentEvent]:
        rows = await self._client.select(
            "agent_events",
            params={
                "agent_run_id": f"eq.{_uuid(agent_run_id)}",
                "seq": f"gt.{after_seq}",
                "order": "seq.asc",
            },
        )
        return [_event_from_row(row) for row in rows]


class SupabaseArtifactRepository:
    def __init__(self, client: SupabaseClient) -> None:
        self._client = client

    async def put(self, artifact_id: str, payload: Mapping[str, Any]) -> None:
        if not artifact_id.strip():
            raise ValueError("artifact_id is required.")
        run_id = payload.get("agent_run_id")
        kind = payload.get("kind")
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("Artifacts require agent_run_id.")
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError("Artifacts require kind.")
        existing = await self.get(artifact_id)
        value = dict(payload)
        if existing is not None:
            if dict(existing) != value:
                raise AgentServiceError(
                    ErrorCode.CHECKPOINT_CONFLICT,
                    f"Artifact {artifact_id!r} already exists with different content.",
                    retryable=False,
                )
            return
        await self._client.insert(
            "agent_artifacts",
            {
                "artifact_id": artifact_id,
                "agent_run_id": _uuid(run_id),
                "kind": kind,
                "payload": value,
                "storage_bucket": value.get("storage_bucket"),
                "storage_path": value.get("storage_path"),
                "checksum": value.get("checksum"),
            },
        )

    async def get(self, artifact_id: str) -> Mapping[str, Any] | None:
        rows = await self._client.select(
            "agent_artifacts",
            params={"artifact_id": f"eq.{artifact_id}", "limit": "1"},
        )
        return _mapping(rows[0].get("payload")) if rows else None

    async def list_for_run(self, agent_run_id: str) -> list[Mapping[str, Any]]:
        rows = await self._client.select(
            "agent_artifacts",
            params={
                "agent_run_id": f"eq.{_uuid(agent_run_id)}",
                "order": "created_at.asc",
            },
        )
        return [_mapping(row.get("payload")) for row in rows]


class SupabaseProposalRepository:
    def __init__(self, client: SupabaseClient) -> None:
        self._client = client

    async def submit(self, proposal: ResultProposal) -> str:
        existing = await self.get(proposal.proposal_id)
        if existing is not None:
            if existing != proposal:
                raise AgentServiceError(
                    ErrorCode.CHECKPOINT_CONFLICT,
                    f"Proposal {proposal.proposal_id!r} already exists with different content.",
                    retryable=False,
                )
            return proposal.proposal_id
        await self._client.insert(
            "result_proposals",
            {
                "id": proposal.proposal_id,
                "agent_run_id": _uuid(proposal.agent_run_id),
                "project_id": _uuid(proposal.project_id),
                "status": proposal.status,
                "payload": proposal.model_dump(mode="json"),
            },
        )
        return proposal.proposal_id

    async def get(self, proposal_id: str) -> ResultProposal | None:
        rows = await self._client.select(
            "result_proposals",
            params={"id": f"eq.{proposal_id}", "limit": "1"},
        )
        if not rows:
            return None
        return ResultProposal.model_validate(rows[0]["payload"])


class SupabaseTraceStore:
    def __init__(self, client: SupabaseClient) -> None:
        self._client = client

    async def append(self, run_id: str, trace: Mapping[str, Any]) -> None:
        await self._client.rpc(
            "append_agent_trace",
            {"target_run_id": run_id, "payload_value": dict(trace)},
        )

    async def list(self, run_id: str) -> list[Mapping[str, Any]]:
        rows = await self._client.select(
            "agent_traces",
            params={"run_key": f"eq.{run_id}", "order": "seq.asc"},
        )
        return [_mapping(row.get("payload")) for row in rows]


class SupabaseCheckpointStore:
    def __init__(self, client: SupabaseClient) -> None:
        self._client = client

    async def load(self, key: str) -> Mapping[str, Any] | None:
        rows = await self._client.select(
            "agent_checkpoints",
            params={"checkpoint_key": f"eq.{key}", "limit": "1"},
        )
        if not rows:
            return None
        return {"revision": int(rows[0]["revision"]), "value": _mapping(rows[0]["payload"])}

    async def save(
        self,
        key: str,
        value: Mapping[str, Any],
        expected_revision: int | None = None,
    ) -> int:
        run_id = key.split(":", 1)[0]
        try:
            revision = await self._client.rpc(
                "save_agent_checkpoint",
                {
                    "target_key": key,
                    "target_run_id": _uuid(run_id),
                    "payload_value": dict(value),
                    "expected_revision": expected_revision,
                },
            )
        except AgentServiceError as exc:
            if exc.code == ErrorCode.INVALID_REQUEST:
                raise AgentServiceError(
                    ErrorCode.CHECKPOINT_CONFLICT,
                    "Checkpoint revision mismatch.",
                    retryable=False,
                ) from exc
            raise
        return int(revision)


class SupabaseRunQueue:
    def __init__(
        self,
        client: SupabaseClient,
        *,
        worker_id: str | None = None,
        lease_seconds: int = 300,
    ) -> None:
        self._client = client
        self._worker_id = worker_id or socket.gethostname()
        self._lease_seconds = lease_seconds

    async def enqueue(self, agent_run_id: str) -> None:
        await self._client.insert(
            "agent_run_queue",
            {
                "agent_run_id": _uuid(agent_run_id),
                "available_at": utc_now().isoformat(),
                "leased_at": None,
                "leased_by": None,
            },
            on_conflict="agent_run_id",
            upsert=True,
        )

    async def dequeue(self) -> str | None:
        run_id = await self._client.rpc(
            "claim_agent_run",
            {"worker_id": self._worker_id, "lease_seconds": self._lease_seconds},
        )
        return str(run_id) if run_id else None

    async def acknowledge(self, agent_run_id: str) -> None:
        await self._client.delete(
            "agent_run_queue",
            filters={"agent_run_id": f"eq.{_uuid(agent_run_id)}"},
        )

    async def size(self) -> int:
        rows = await self._client.select("agent_run_queue", params={"select": "agent_run_id"})
        return len(rows)


def _run_to_row(
    run: AgentRun,
    *,
    fingerprint: str | None = None,
    include_identity: bool = True,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "run_type": run.run_type.value,
        "status": run.status.value,
        "scope": run.scope.model_dump(mode="json"),
        "feedback_id": run.feedback_id,
        "profile_hint": run.profile_hint,
        "expected_result_version": run.expected_result_version,
        "options": run.options.model_dump(mode="json"),
        "profile": run.profile.model_dump(mode="json") if run.profile else None,
        "parent_run_id": _uuid(run.parent_run_id) if run.parent_run_id else None,
        "current_stage": run.current_stage.value if run.current_stage else None,
        "error": run.error.model_dump(mode="json") if run.error else None,
    }
    if include_identity:
        row.update(
            {
                "id": _uuid(run.agent_run_id),
                "idempotency_key": run.idempotency_key,
                "request_fingerprint": fingerprint or "saved-run",
                "project_id": _uuid(run.project_id),
                "source_document_id": _uuid(run.source_document_id),
                "requested_by": _uuid(run.requested_by),
                "created_at": run.created_at.isoformat(),
            }
        )
    return row


def _run_from_row(row: Mapping[str, Any]) -> AgentRun:
    return AgentRun.model_validate(
        {
            "agent_run_id": str(row["id"]),
            "idempotency_key": row["idempotency_key"],
            "run_type": row["run_type"],
            "status": row["status"],
            "project_id": str(row["project_id"]),
            "source_document_id": str(row["source_document_id"]),
            "requested_by": str(row["requested_by"]),
            "scope": row["scope"],
            "feedback_id": row.get("feedback_id"),
            "profile_hint": row.get("profile_hint"),
            "expected_result_version": row.get("expected_result_version"),
            "options": row.get("options") or {},
            "profile": row.get("profile"),
            "parent_run_id": str(row["parent_run_id"]) if row.get("parent_run_id") else None,
            "current_stage": row.get("current_stage"),
            "error": row.get("error"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    )


def _event_from_row(row: Mapping[str, Any]) -> AgentEvent:
    return AgentEvent.model_validate(
        {
            "event_id": str(row["id"]),
            "agent_run_id": str(row["agent_run_id"]),
            "seq": row["seq"],
            "occurred_at": row["occurred_at"],
            "event_type": row["event_type"],
            "stage": row.get("stage"),
            "level": row.get("level") or "INFO",
            "scope": row.get("scope"),
            "message": row.get("message") or "",
            "metrics": row.get("metrics") or {},
            "artifact_refs": row.get("artifact_refs") or [],
            "error": row.get("error"),
        }
    )


def _uuid(value: str) -> str:
    return str(UUID(value))


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AgentServiceError(
            ErrorCode.INTERNAL_ERROR,
            "Supabase JSON payload is not an object.",
            retryable=False,
        )
    return dict(value)


def _missing_row(resource: str) -> AgentServiceError:
    return AgentServiceError(
        ErrorCode.PROJECT_CONTEXT_NOT_FOUND,
        f"Supabase did not return the requested {resource}.",
        retryable=False,
    )
