from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from ..domain.enums import CrossPageState, ErrorCode, ScopeType
from ..domain.errors import AgentServiceError
from ..domain.models.correction import CorrectionEvidenceBundle
from ..domain.models.improvement import AcceptedFeedback, AffectedScope
from ..domain.models.proposals import ResultProposal
from ..domain.models.result_data import (
    ConnectionSearchQuery,
    ConnectionSearchResult,
    ResultCommitResult,
)


@dataclass(slots=True)
class _ConnectionEntry:
    match: ConnectionSearchResult
    bundle: CorrectionEvidenceBundle


class InMemoryResultDataRepository:
    """Development adapter for the Server-owned result-data tool contract."""

    def __init__(self) -> None:
        self._entries: dict[str, _ConnectionEntry] = {}
        self._accepted_feedback: dict[str, AcceptedFeedback] = {}
        self._commits: dict[str, ResultCommitResult] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        match: ConnectionSearchResult,
        bundle: CorrectionEvidenceBundle,
    ) -> None:
        if bundle.facts.target.id != match.connection_id:
            raise ValueError("Connection metadata and correction bundle target do not match.")
        async with self._lock:
            self._entries[match.connection_id] = _ConnectionEntry(
                match=match.model_copy(deep=True),
                bundle=bundle.model_copy(deep=True),
            )

    async def search_connections(
        self,
        query: ConnectionSearchQuery,
    ) -> list[ConnectionSearchResult]:
        async with self._lock:
            entries = list(self._entries.values())
        matches = [entry.match for entry in entries if _matches(entry.match, query)]
        return [item.model_copy(deep=True) for item in sorted(matches, key=_sort_key)]

    async def get_correction_bundle(self, connection_id: str) -> CorrectionEvidenceBundle:
        async with self._lock:
            entry = self._entries.get(connection_id)
        if entry is None:
            raise AgentServiceError(
                ErrorCode.PROJECT_CONTEXT_NOT_FOUND,
                "The requested connection was not found.",
                retryable=False,
            )
        return entry.bundle.model_copy(deep=True)

    async def commit_result_patch(
        self,
        proposal: ResultProposal,
        confirmed_by: str,
    ) -> ResultCommitResult:
        async with self._lock:
            existing = self._commits.get(proposal.proposal_id)
            if existing is not None:
                if existing.confirmed_by != confirmed_by:
                    raise AgentServiceError(
                        ErrorCode.CHECKPOINT_CONFLICT,
                        "The proposal was already confirmed by another user.",
                        retryable=False,
                    )
                return existing.model_copy(deep=True)

            affected_entries: list[_ConnectionEntry] = []
            for operation in proposal.operations:
                entry = self._entries.get(operation.target_id)
                if entry is None or entry.match.project_id != proposal.project_id:
                    raise AgentServiceError(
                        ErrorCode.PROJECT_CONTEXT_NOT_FOUND,
                        "A proposal target does not belong to the requested project.",
                        retryable=False,
                    )
                if entry.match.result_version != proposal.base_result_version:
                    raise AgentServiceError(
                        ErrorCode.BASE_VERSION_CONFLICT,
                        "The result version changed before confirmation.",
                        retryable=False,
                    )
                if (
                    operation.expected_version is not None
                    and operation.expected_version != entry.match.record_version
                ):
                    raise AgentServiceError(
                        ErrorCode.BASE_VERSION_CONFLICT,
                        "A connection changed before confirmation.",
                        retryable=False,
                    )
                affected_entries.append(entry)

            new_version = proposal.base_result_version + 1
            result_version_id = f"{proposal.project_id}:v{new_version}"
            accepted: list[AcceptedFeedback] = []
            for operation, entry in zip(proposal.operations, affected_entries, strict=True):
                if operation.op != "replace" or operation.before is None or operation.after is None:
                    raise AgentServiceError(
                        ErrorCode.INVALID_REQUEST,
                        "Online confirmation currently accepts replace operations only.",
                        retryable=False,
                    )
                current = next(
                    (
                        item
                        for item in entry.bundle.current_records
                        if _record_id(item) == operation.target_id
                    ),
                    None,
                )
                if current is None or current != operation.before:
                    raise AgentServiceError(
                        ErrorCode.BASE_VERSION_CONFLICT,
                        "The connection no longer matches the proposal before-value.",
                        retryable=False,
                    )
                current.clear()
                current.update(deepcopy(operation.after))
                entry.match.start_terminal = _terminal(operation.after, "start")
                entry.match.end_terminal = _terminal(operation.after, "end")
                cross_page = operation.after.get("is_cross_page")
                if cross_page is not None:
                    entry.match.is_cross_page = CrossPageState(str(cross_page))
                entry.bundle.base_result_version = new_version
                entry.bundle.facts.target.result_version_id = result_version_id
                entry.match.result_version = new_version
                entry.match.result_version_id = result_version_id
                entry.match.record_version += 1
                feedback = AcceptedFeedback(
                    feedback_id=entry.bundle.facts.feedback_id,
                    project_id=proposal.project_id,
                    accepted=True,
                    result_version_id=result_version_id,
                    profile=proposal.profile,
                    model_name=proposal.model.name,
                    target=AffectedScope(type=ScopeType.CONNECTION, ids=[operation.target_id]),
                    before=deepcopy(operation.before),
                    after=deepcopy(operation.after),
                    evidence_ids=list(operation.evidence_ids),
                    stage_artifact_ids=[f"{proposal.agent_run_id}:correction"],
                    trace_ids=[f"{proposal.agent_run_id}:trace"],
                    prompt_checksum=proposal.profile.checksum or "unversioned-profile",
                )
                self._accepted_feedback[feedback.feedback_id] = feedback
                accepted.append(feedback)

            result = ResultCommitResult(
                proposal_id=proposal.proposal_id,
                project_id=proposal.project_id,
                previous_result_version=proposal.base_result_version,
                result_version=new_version,
                result_version_id=result_version_id,
                confirmed_by=confirmed_by,
                accepted_feedback=accepted,
            )
            self._commits[proposal.proposal_id] = result
            return result.model_copy(deep=True)

    async def get_accepted_feedback(self, feedback_id: str) -> AcceptedFeedback:
        async with self._lock:
            feedback = self._accepted_feedback.get(feedback_id)
        if feedback is None:
            raise KeyError(feedback_id)
        return feedback.model_copy(deep=True)

    async def persist_extraction_proposal(
        self,
        proposal: ResultProposal,
        created_by: str,
    ) -> ResultCommitResult:
        async with self._lock:
            existing = self._commits.get(proposal.proposal_id)
            if existing is not None:
                return existing.model_copy(deep=True)
            result = ResultCommitResult(
                proposal_id=proposal.proposal_id,
                project_id=proposal.project_id,
                previous_result_version=proposal.base_result_version,
                result_version=proposal.base_result_version + 1,
                result_version_id=f"{proposal.project_id}:v{proposal.base_result_version + 1}",
                confirmed_by=created_by,
            )
            self._commits[proposal.proposal_id] = result
            return result.model_copy(deep=True)


def _matches(match: ConnectionSearchResult, query: ConnectionSearchQuery) -> bool:
    exact_fields = (
        "project_id",
        "workspace_id",
        "workspace_page",
        "result_version_id",
        "connection_id",
        "wire_number",
    )
    for field in exact_fields:
        expected = getattr(query, field)
        if expected is not None and str(getattr(match, field)) != str(expected):
            return False
    for field in ("project_name", "workspace_name"):
        expected = getattr(query, field)
        if expected is not None and getattr(match, field).casefold() != expected.casefold():
            return False
    if query.terminal is not None:
        terminals = {match.start_terminal, match.end_terminal}
        if query.terminal not in terminals:
            return False
    return True


def _sort_key(item: ConnectionSearchResult) -> tuple[str, str, str, str]:
    return (
        item.project_name,
        item.workspace_name,
        item.workspace_page or "",
        item.connection_id,
    )


def _record_id(record: dict[str, Any]) -> str:
    return str(record.get("connection_id") or record.get("id") or "")


def _terminal(record: dict[str, Any], side: str) -> str | None:
    flat = record.get(f"{side}_terminal")
    if flat not in (None, ""):
        return str(flat)
    endpoint = record.get(side)
    if isinstance(endpoint, dict) and endpoint.get("terminal") not in (None, ""):
        return str(endpoint["terminal"])
    return None
