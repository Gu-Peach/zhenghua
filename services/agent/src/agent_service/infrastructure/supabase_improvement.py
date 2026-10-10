from __future__ import annotations

from typing import Any

from ..domain.enums import ErrorCode, ProfileCandidateStatus
from ..domain.errors import AgentServiceError
from ..domain.models.improvement import EvalReport, ProfileCandidate, ReleaseDecision
from .supabase_client import SupabaseClient


class SupabaseCandidateRepository:
    """Persist candidate state, release-gate decisions and human audit events."""

    def __init__(self, client: SupabaseClient) -> None:
        self._client = client

    async def put(self, candidate: ProfileCandidate) -> None:
        rows = await self._client.select(
            "profile_candidates",
            params={"id": f"eq.{candidate.candidate_id}", "limit": "1"},
        )
        payload = candidate.model_dump(mode="json")
        if rows:
            if rows[0].get("payload") != payload:
                raise AgentServiceError(
                    ErrorCode.CHECKPOINT_CONFLICT,
                    "Profile candidate already exists with different content.",
                    retryable=False,
                )
            return
        await self._client.insert(
            "profile_candidates",
            {
                "id": candidate.candidate_id,
                "profile_key": candidate.profile.key,
                "profile_version": candidate.profile.version,
                "status": candidate.status.value,
                "payload": payload,
            },
        )
        await self._client.insert(
            "profile_candidate_audit",
            {
                "candidate_id": candidate.candidate_id,
                "action": "created",
                "to_status": candidate.status.value,
            },
        )

    async def get(self, candidate_id: str) -> ProfileCandidate:
        rows = await self._client.select(
            "profile_candidates",
            params={"id": f"eq.{candidate_id}", "limit": "1"},
        )
        if not rows:
            raise KeyError(candidate_id)
        return ProfileCandidate.model_validate(rows[0]["payload"])

    async def transition(
        self,
        candidate_id: str,
        status: ProfileCandidateStatus,
        *,
        reviewer_id: str | None = None,
    ) -> ProfileCandidate:
        try:
            payload = await self._client.rpc(
                "transition_profile_candidate",
                {
                    "candidate_key": candidate_id,
                    "target_status": status.value,
                    "reviewer": reviewer_id,
                    "action_value": "transition",
                },
            )
        except AgentServiceError as exc:
            if exc.code == ErrorCode.INVALID_REQUEST:
                raise ValueError("Invalid Profile candidate transition.") from exc
            raise
        return ProfileCandidate.model_validate(payload)

    async def rollback(self, candidate_id: str, reviewer_id: str) -> ProfileCandidate:
        try:
            payload = await self._client.rpc(
                "transition_profile_candidate",
                {
                    "candidate_key": candidate_id,
                    "target_status": ProfileCandidateStatus.ROLLED_BACK.value,
                    "reviewer": reviewer_id,
                    "action_value": "rollback",
                },
            )
        except AgentServiceError as exc:
            if exc.code == ErrorCode.INVALID_REQUEST:
                raise ValueError("Profile candidate cannot be rolled back.") from exc
            raise
        return ProfileCandidate.model_validate(payload)

    async def audit_log(self, candidate_id: str | None = None) -> list[dict[str, Any]]:
        params = {"order": "occurred_at.asc"}
        if candidate_id is not None:
            params["candidate_id"] = f"eq.{candidate_id}"
        return await self._client.select("profile_candidate_audit", params=params)

    async def record_gate(self, candidate_id: str, decision: ReleaseDecision) -> None:
        rows = await self._client.update(
            "profile_candidates",
            {
                "gate_passed": decision.passed,
                "gate_decision": decision.model_dump(mode="json"),
            },
            filters={"id": f"eq.{candidate_id}"},
        )
        if not rows:
            raise KeyError(candidate_id)
        await self._client.insert(
            "profile_candidate_audit",
            {
                "candidate_id": candidate_id,
                "action": "release_gate",
                "payload": decision.model_dump(mode="json"),
            },
        )

    async def gate_passed(self, candidate_id: str) -> bool:
        rows = await self._client.select(
            "profile_candidates",
            params={"id": f"eq.{candidate_id}", "select": "gate_passed", "limit": "1"},
        )
        if not rows:
            raise KeyError(candidate_id)
        return bool(rows[0]["gate_passed"])


class SupabaseEvalRepository:
    def __init__(self, client: SupabaseClient) -> None:
        self._client = client

    async def put(self, report: EvalReport) -> None:
        payload = report.model_dump(mode="json")
        rows = await self._client.select(
            "evaluation_reports",
            params={"id": f"eq.{report.eval_run_id}", "limit": "1"},
        )
        if rows:
            if rows[0].get("payload") != payload:
                raise AgentServiceError(
                    ErrorCode.CHECKPOINT_CONFLICT,
                    "Evaluation report already exists with different content.",
                    retryable=False,
                )
            return
        await self._client.insert(
            "evaluation_reports",
            {
                "id": report.eval_run_id,
                "candidate_id": report.candidate_id,
                "payload": payload,
            },
        )

    async def get(self, eval_run_id: str) -> EvalReport:
        rows = await self._client.select(
            "evaluation_reports",
            params={"id": f"eq.{eval_run_id}", "limit": "1"},
        )
        if not rows:
            raise KeyError(eval_run_id)
        return EvalReport.model_validate(rows[0]["payload"])
