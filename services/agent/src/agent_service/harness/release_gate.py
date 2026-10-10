from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..domain.enums import ProfileCandidateStatus
from ..domain.models.improvement import EvalReport, ProfileCandidate, ReleaseDecision


@dataclass(frozen=True, slots=True)
class ReleaseThresholds:
    max_cost_ratio: float = 1.20
    max_p95_latency_ratio: float = 1.20


class ReleaseGate:
    def __init__(self, thresholds: ReleaseThresholds | None = None) -> None:
        self.thresholds = thresholds or ReleaseThresholds()

    def evaluate(self, report: EvalReport) -> ReleaseDecision:
        metrics = report.candidate
        baseline = report.baseline
        reasons: list[str] = []
        if metrics.target_pass_rate < 1.0:
            reasons.append("target cases did not all pass")
        if metrics.protected_regressions:
            reasons.append("protected cases regressed")
        if metrics.negative_hallucinations:
            reasons.append("negative cases introduced hallucinations")
        if metrics.schema_valid_rate < 1.0:
            reasons.append("schema valid rate is below 100%")
        if metrics.field_precision < baseline.field_precision:
            reasons.append("field precision decreased")
        if metrics.field_recall < baseline.field_recall:
            reasons.append("field recall decreased")
        if _exceeds_ratio(metrics.total_cost, baseline.total_cost, self.thresholds.max_cost_ratio):
            reasons.append("cost exceeds configured threshold")
        if _exceeds_ratio(
            metrics.p95_duration_seconds,
            baseline.p95_duration_seconds,
            self.thresholds.max_p95_latency_ratio,
        ):
            reasons.append("P95 latency exceeds configured threshold")
        return ReleaseDecision(passed=not reasons, reasons=reasons, reviewer_required=True)


class InMemoryCandidateRepository:
    def __init__(self) -> None:
        self._items: dict[str, ProfileCandidate] = {}
        self._reviews: dict[str, list[str]] = {}
        self._active: dict[str, str] = {}
        self._previous_active: dict[str, str] = {}
        self._audit: list[dict[str, Any]] = []
        self._gate_decisions: dict[str, ReleaseDecision] = {}
        self._lock = asyncio.Lock()

    async def put(self, candidate: ProfileCandidate) -> None:
        async with self._lock:
            self._items[candidate.candidate_id] = candidate.model_copy(deep=True)
            self._audit.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "action": "created",
                    "status": candidate.status.value,
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    async def get(self, candidate_id: str) -> ProfileCandidate:
        async with self._lock:
            candidate = self._items.get(candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)
        return candidate.model_copy(deep=True)

    async def transition(
        self,
        candidate_id: str,
        status: ProfileCandidateStatus,
        *,
        reviewer_id: str | None = None,
    ) -> ProfileCandidate:
        async with self._lock:
            candidate = self._items[candidate_id]
            _validate_transition(candidate.status, status)
            if status in {ProfileCandidateStatus.APPROVED, ProfileCandidateStatus.CANARY} and not reviewer_id:
                raise ValueError("Human reviewer_id is required for approval and canary.")
            if reviewer_id:
                self._reviews.setdefault(candidate_id, []).append(reviewer_id)
            if status == ProfileCandidateStatus.ACTIVE:
                if not self._reviews.get(candidate_id):
                    raise ValueError("A candidate cannot become active without human approval.")
                key = candidate.profile.key
                previous = self._active.get(key)
                if previous:
                    self._previous_active[key] = previous
                    old_candidate = self._items[previous]
                    self._items[previous] = old_candidate.model_copy(
                        update={"status": ProfileCandidateStatus.RETIRED}
                    )
                self._active[key] = candidate_id
            updated = candidate.model_copy(update={"status": status})
            self._items[candidate_id] = updated
            self._audit.append(
                {
                    "candidate_id": candidate_id,
                    "action": "transition",
                    "from": candidate.status.value,
                    "to": status.value,
                    "reviewer_id": reviewer_id,
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            return updated.model_copy(deep=True)

    async def rollback(self, candidate_id: str, reviewer_id: str) -> ProfileCandidate:
        async with self._lock:
            candidate = self._items[candidate_id]
            if candidate.status not in {ProfileCandidateStatus.CANARY, ProfileCandidateStatus.ACTIVE}:
                raise ValueError("Only canary or active candidates can be rolled back.")
            self._reviews.setdefault(candidate_id, []).append(reviewer_id)
            if self._active.get(candidate.profile.key) == candidate_id:
                previous = self._previous_active.get(candidate.profile.key)
                if previous:
                    self._active[candidate.profile.key] = previous
                    previous_candidate = self._items[previous]
                    self._items[previous] = previous_candidate.model_copy(
                        update={"status": ProfileCandidateStatus.ACTIVE}
                    )
                else:
                    self._active.pop(candidate.profile.key, None)
            updated = candidate.model_copy(update={"status": ProfileCandidateStatus.ROLLED_BACK})
            self._items[candidate_id] = updated
            self._audit.append(
                {
                    "candidate_id": candidate_id,
                    "action": "rollback",
                    "reviewer_id": reviewer_id,
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            return updated.model_copy(deep=True)

    async def audit_log(self, candidate_id: str | None = None) -> list[dict[str, Any]]:
        async with self._lock:
            return [
                dict(item)
                for item in self._audit
                if candidate_id is None or item["candidate_id"] == candidate_id
            ]

    async def record_gate(self, candidate_id: str, decision: ReleaseDecision) -> None:
        async with self._lock:
            if candidate_id not in self._items:
                raise KeyError(candidate_id)
            self._gate_decisions[candidate_id] = decision.model_copy(deep=True)
            self._audit.append(
                {
                    "candidate_id": candidate_id,
                    "action": "release_gate",
                    "passed": decision.passed,
                    "reasons": list(decision.reasons),
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    async def gate_passed(self, candidate_id: str) -> bool:
        async with self._lock:
            decision = self._gate_decisions.get(candidate_id)
            return bool(decision and decision.passed)


def _exceeds_ratio(value: float, baseline: float, ratio: float) -> bool:
    if baseline <= 0:
        return value > 0
    return value > baseline * ratio


def _validate_transition(current: ProfileCandidateStatus, target: ProfileCandidateStatus) -> None:
    allowed = {
        ProfileCandidateStatus.DRAFT: {
            ProfileCandidateStatus.EVALUATING,
            ProfileCandidateStatus.REJECTED,
        },
        ProfileCandidateStatus.EVALUATING: {
            ProfileCandidateStatus.REJECTED,
            ProfileCandidateStatus.APPROVED,
        },
        ProfileCandidateStatus.APPROVED: {ProfileCandidateStatus.CANARY},
        ProfileCandidateStatus.CANARY: {
            ProfileCandidateStatus.ACTIVE,
            ProfileCandidateStatus.ROLLED_BACK,
        },
        ProfileCandidateStatus.ACTIVE: {
            ProfileCandidateStatus.RETIRED,
            ProfileCandidateStatus.ROLLED_BACK,
        },
    }
    if target not in allowed.get(current, set()):
        raise ValueError(f"Invalid candidate transition: {current.value} -> {target.value}.")
