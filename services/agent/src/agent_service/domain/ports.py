from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from .enums import ProfileCandidateStatus
from .models.correction import CorrectionEvidenceBundle
from .models.extraction import ExtractionExecutionResult, LegacyExtractionRequest
from .models.extraction_stages import (
    CrossPageCompletionData,
    CrossPageCompletionRequest,
    PageClassificationData,
    PageClassificationRequest,
    PageScanData,
    PageScanRequest,
)
from .models.improvement import (
    AcceptedFeedback,
    EvalReport,
    ProfileCandidate,
    ReleaseDecision,
)
from .models.proposals import ResultProposal
from .models.result_data import ConnectionSearchQuery, ConnectionSearchResult, ResultCommitResult
from .models.runs import AgentEvent, AgentRun, CreateRunRequest


@runtime_checkable
class RunRepository(Protocol):
    async def create(self, request: CreateRunRequest, idempotency_key: str) -> AgentRun: ...

    async def get(self, agent_run_id: str) -> AgentRun | None: ...

    async def save(self, run: AgentRun) -> None: ...


@runtime_checkable
class EventRepository(Protocol):
    async def append(self, event: AgentEvent) -> AgentEvent: ...

    async def list_after(self, agent_run_id: str, after_seq: int = -1) -> list[AgentEvent]: ...


@runtime_checkable
class ArtifactRepository(Protocol):
    async def put(self, artifact_id: str, payload: Mapping[str, Any]) -> None: ...

    async def get(self, artifact_id: str) -> Mapping[str, Any] | None: ...

    async def list_for_run(self, agent_run_id: str) -> list[Mapping[str, Any]]: ...


@runtime_checkable
class CheckpointStore(Protocol):
    async def load(self, key: str) -> Mapping[str, Any] | None: ...

    async def save(self, key: str, value: Mapping[str, Any], expected_revision: int | None = None) -> int: ...


@runtime_checkable
class TraceStore(Protocol):
    async def append(self, run_id: str, trace: Mapping[str, Any]) -> None: ...

    async def list(self, run_id: str) -> list[Mapping[str, Any]]: ...


@runtime_checkable
class ProposalSink(Protocol):
    async def submit(self, proposal: ResultProposal) -> str: ...

    async def get(self, proposal_id: str) -> ResultProposal | None: ...


@runtime_checkable
class RunQueue(Protocol):
    async def enqueue(self, agent_run_id: str) -> None: ...

    async def dequeue(self) -> str | None: ...

    async def acknowledge(self, agent_run_id: str) -> None: ...


@runtime_checkable
class ResultDataRepository(Protocol):
    async def search_connections(
        self,
        query: ConnectionSearchQuery,
    ) -> list[ConnectionSearchResult]: ...

    async def get_correction_bundle(self, connection_id: str) -> CorrectionEvidenceBundle: ...

    async def commit_result_patch(
        self,
        proposal: ResultProposal,
        confirmed_by: str,
    ) -> ResultCommitResult: ...

    async def get_accepted_feedback(self, feedback_id: str) -> AcceptedFeedback: ...

    async def persist_extraction_proposal(
        self,
        proposal: ResultProposal,
        created_by: str,
    ) -> ResultCommitResult: ...


@runtime_checkable
class CandidateRepository(Protocol):
    async def put(self, candidate: ProfileCandidate) -> None: ...

    async def get(self, candidate_id: str) -> ProfileCandidate: ...

    async def transition(
        self,
        candidate_id: str,
        status: ProfileCandidateStatus,
        *,
        reviewer_id: str | None = None,
    ) -> ProfileCandidate: ...

    async def rollback(self, candidate_id: str, reviewer_id: str) -> ProfileCandidate: ...

    async def audit_log(self, candidate_id: str | None = None) -> list[dict[str, Any]]: ...

    async def record_gate(self, candidate_id: str, decision: ReleaseDecision) -> None: ...

    async def gate_passed(self, candidate_id: str) -> bool: ...


@runtime_checkable
class EvalRepository(Protocol):
    async def put(self, report: EvalReport) -> None: ...

    async def get(self, eval_run_id: str) -> EvalReport: ...


@runtime_checkable
class ExtractionAdapter(Protocol):
    async def run_full(self, request: LegacyExtractionRequest) -> ExtractionExecutionResult: ...


@runtime_checkable
class ExtractionStageAdapter(Protocol):
    """Profile-specific VLM execution for the three stable extraction stages."""

    async def classify_page(self, request: PageClassificationRequest) -> PageClassificationData: ...

    async def scan_page(self, request: PageScanRequest) -> PageScanData: ...

    async def resolve_cross_page(
        self,
        request: CrossPageCompletionRequest,
    ) -> CrossPageCompletionData: ...
