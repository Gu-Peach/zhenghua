from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field, model_validator

from ..enums import (
    AgentStage,
    EvalCaseKind,
    EvaluationRecommendation,
    ProfileCandidateStatus,
    ProfileCandidateType,
    RootCauseCategory,
    ScopeType,
)
from .common import StrictModel, utc_now
from .runs import ProfileRef


class AffectedScope(StrictModel):
    type: ScopeType
    ids: list[str] = Field(min_length=1)


class Diagnosis(StrictModel):
    category: RootCauseCategory
    confidence: float = Field(ge=0.0, le=1.0)
    affected_stage: list[AgentStage] = Field(min_length=1)
    affected_scope: AffectedScope
    evidence_ids: list[str] = Field(default_factory=list)
    explanation: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
    profile_candidate_required: bool = False
    needs_human_input: bool = False


class AcceptedFeedback(StrictModel):
    feedback_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    accepted: bool
    result_version_id: str = Field(min_length=1)
    profile: ProfileRef
    model_name: str = Field(min_length=1)
    target: AffectedScope
    before: dict[str, Any]
    after: dict[str, Any]
    evidence_ids: list[str] = Field(min_length=1)
    stage_artifact_ids: list[str] = Field(min_length=1)
    trace_ids: list[str] = Field(min_length=1)
    prompt_checksum: str = Field(min_length=1)
    severity: Literal["low", "medium", "high", "critical"] = "medium"


class FailureSignature(StrictModel):
    profile_key: str
    profile_version: str
    affected_stage: AgentStage
    category: RootCauseCategory
    pattern: str
    model_name: str
    prompt_checksum: str

    @property
    def key(self) -> str:
        return "|".join(
            (
                self.profile_key,
                self.profile_version,
                self.affected_stage.value,
                self.category.value,
                self.pattern,
                self.model_name,
                self.prompt_checksum,
            )
        )


class ImprovementCase(StrictModel):
    case_id: str = Field(default_factory=lambda: str(uuid4()))
    kind: EvalCaseKind
    profile: ProfileRef
    input_refs: list[str] = Field(min_length=1)
    expected: dict[str, Any]
    source_feedback_ids: list[str] = Field(default_factory=list)


class CandidatePatchOperation(StrictModel):
    op: Literal["add", "replace", "remove", "suggest_code_change"]
    relative_path: str = Field(min_length=1)
    content: str | None = None
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_content(self) -> CandidatePatchOperation:
        if self.op in {"add", "replace"} and self.content is None:
            raise ValueError("add/replace candidate patches require content.")
        return self


class ProfilePatchModelOutput(StrictModel):
    candidate_type: ProfileCandidateType
    summary: str = Field(min_length=1)
    operations: list[CandidatePatchOperation] = Field(min_length=1)
    expected_benefit: str = Field(min_length=1)
    risks: list[str] = Field(default_factory=list)


class ProfileCandidate(StrictModel):
    candidate_id: str = Field(default_factory=lambda: str(uuid4()))
    profile: ProfileRef
    candidate_type: ProfileCandidateType
    status: ProfileCandidateStatus = ProfileCandidateStatus.DRAFT
    summary: str
    operations: list[CandidatePatchOperation]
    source_feedback_ids: list[str] = Field(min_length=1)
    diagnoses: list[Diagnosis] = Field(min_length=1)
    sandbox_path: str
    checksum: str
    created_at: datetime = Field(default_factory=utc_now)


class EvalCaseResult(StrictModel):
    case_id: str
    kind: EvalCaseKind
    expected: dict[str, Any]
    actual: dict[str, Any]
    schema_valid: bool = True
    duration_seconds: float = Field(default=0.0, ge=0.0)
    cost: float = Field(default=0.0, ge=0.0)
    error: str | None = None


class EvalMetrics(StrictModel):
    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    target_pass_rate: float = Field(ge=0.0, le=1.0)
    protected_regressions: int = Field(ge=0)
    negative_hallucinations: int = Field(ge=0)
    schema_valid_rate: float = Field(ge=0.0, le=1.0)
    field_precision: float = Field(ge=0.0, le=1.0)
    field_recall: float = Field(ge=0.0, le=1.0)
    total_cost: float = Field(ge=0.0)
    p95_duration_seconds: float = Field(ge=0.0)


class EvalReport(StrictModel):
    eval_run_id: str = Field(default_factory=lambda: str(uuid4()))
    candidate_id: str
    baseline: EvalMetrics
    candidate: EvalMetrics
    baseline_results: list[EvalCaseResult]
    candidate_results: list[EvalCaseResult]
    generated_at: datetime = Field(default_factory=utc_now)


class EvaluationJudgement(StrictModel):
    recommendation: EvaluationRecommendation
    summary: str = Field(min_length=1)
    improvements: list[str] = Field(default_factory=list)
    regressions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    requires_human_review: bool = True


class ReleaseDecision(StrictModel):
    passed: bool
    reasons: list[str]
    reviewer_required: bool = True
