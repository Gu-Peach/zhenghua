from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from ..enums import CorrectionIssueKind, CrossPageState
from .common import StrictModel
from .improvement import AcceptedFeedback


class ConnectionSearchQuery(StrictModel):
    project_id: str | None = None
    project_name: str | None = None
    workspace_id: str | None = None
    workspace_name: str | None = None
    workspace_page: str | None = None
    result_version_id: str | None = None
    connection_id: str | None = None
    wire_number: str | None = None
    terminal: str | None = None

    @model_validator(mode="after")
    def require_search_term(self) -> ConnectionSearchQuery:
        if not any(
            (
                self.project_id,
                self.project_name,
                self.workspace_id,
                self.workspace_name,
                self.workspace_page,
                self.result_version_id,
                self.connection_id,
                self.wire_number,
                self.terminal,
            )
        ):
            raise ValueError("Connection search requires at least one constrained field.")
        return self


class ConnectionSearchResult(StrictModel):
    connection_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    project_name: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    workspace_name: str = Field(min_length=1)
    workspace_page: str | None = None
    result_version_id: str = Field(min_length=1)
    result_version: int = Field(ge=0)
    record_version: int = Field(ge=0)
    source_document_id: str = Field(min_length=1)
    wire_number: str | None = None
    terminal_strip: str | None = None
    start_terminal: str | None = None
    end_terminal: str | None = None
    is_cross_page: CrossPageState = CrossPageState.UNKNOWN


class PrepareCorrectionRequest(StrictModel):
    query: ConnectionSearchQuery
    requested_by: str = Field(min_length=1)
    field: str | None = None
    observed_problem: str = Field(min_length=1)
    suggested_value_present: bool = False
    suggested_value: Any = None
    issue_kind: CorrectionIssueKind = CorrectionIssueKind.RECOGNITION_ERROR

    @model_validator(mode="after")
    def validate_direct_value(self) -> PrepareCorrectionRequest:
        if self.issue_kind == CorrectionIssueKind.DIRECT_VALUE_CHANGE:
            if not self.field or not self.suggested_value_present:
                raise ValueError("Direct value correction requires field and suggested value.")
        return self


class PreparedCorrection(StrictModel):
    feedback_id: str = Field(min_length=1)
    match: ConnectionSearchResult
    expected_result_version: int = Field(ge=0)


class ResultCommitResult(StrictModel):
    proposal_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    previous_result_version: int = Field(ge=0)
    result_version: int = Field(ge=0)
    result_version_id: str = Field(min_length=1)
    confirmed_by: str = Field(min_length=1)
    accepted_feedback: list[AcceptedFeedback] = Field(default_factory=list)
