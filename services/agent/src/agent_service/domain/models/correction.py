from __future__ import annotations

from typing import Any

from pydantic import Field

from ..enums import (
    AgentStage,
    CorrectionAction,
    CorrectionIssueKind,
    CrossPageState,
    ScopeType,
)
from .common import StrictModel
from .extraction_stages import (
    CrossPageCompletionRequest,
    PageClassificationRequest,
    PageScanRequest,
)
from .profiles import ProfileBinding


class FeedbackTarget(StrictModel):
    type: ScopeType
    id: str = Field(min_length=1)
    field: str | None = None
    project_id: str = Field(min_length=1)
    result_version_id: str = Field(min_length=1)


class CorrectionConstraints(StrictModel):
    preserve_start: bool = True
    allowed_target_drawings: list[str] = Field(default_factory=list)
    allowed_connection_ids: list[str] = Field(default_factory=list)
    allowed_fields: list[str] = Field(default_factory=list)
    do_not_modify_unrelated_rows: bool = True


class CorrectionContext(StrictModel):
    feedback_id: str = Field(min_length=1)
    field: str | None = None
    observed_problem: str = Field(min_length=1)
    suggested_value: Any = None
    constraints: CorrectionConstraints
    evidence: dict[str, Any] = Field(default_factory=dict)
    instruction: str = (
        "Re-read visible evidence. The suggested value is not ground truth; "
        "return needs_review when the drawing is insufficient."
    )


class CorrectionFacts(StrictModel):
    feedback_id: str = Field(min_length=1)
    target: FeedbackTarget
    issue_kind: CorrectionIssueKind
    is_cross_page: CrossPageState = CrossPageState.UNKNOWN
    suggested_value_present: bool = False
    affected_drawing_ids: list[str] = Field(default_factory=list)
    target_drawing_ids: list[str] = Field(default_factory=list)


class CorrectionPlan(StrictModel):
    feedback_id: str = Field(min_length=1)
    action: CorrectionAction
    stages: list[AgentStage] = Field(default_factory=list)
    target: FeedbackTarget
    source_drawing_ids: list[str] = Field(default_factory=list)
    target_drawing_ids: list[str] = Field(default_factory=list)
    allowed_fields: list[str] = Field(default_factory=list)
    estimated_model_calls: int = Field(ge=0)
    requires_human_approval: bool = False
    reason: str = Field(min_length=1)


class CorrectionEvidenceBundle(StrictModel):
    facts: CorrectionFacts
    context: CorrectionContext
    profile: ProfileBinding
    base_result_version: int = Field(ge=0)
    current_records: list[dict[str, Any]] = Field(min_length=1)
    unaffected_records: list[dict[str, Any]] = Field(default_factory=list)
    record_versions: dict[str, int] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(min_length=1)
    page_classification_requests: list[PageClassificationRequest] = Field(default_factory=list)
    page_scan_requests: list[PageScanRequest] = Field(default_factory=list)
    cross_page_requests: list[CrossPageCompletionRequest] = Field(default_factory=list)
    cross_page_task_targets: dict[str, str] = Field(default_factory=dict)
