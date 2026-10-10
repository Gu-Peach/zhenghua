from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from pydantic import Field, HttpUrl, model_validator

from ..enums import AgentStage, EventType, RunStatus, RunType, ScopeType
from .common import StrictModel, utc_now


class ProfileRef(StrictModel):
    key: str = Field(min_length=1)
    version: str = Field(min_length=1)
    checksum: str | None = None


class ModelRef(StrictModel):
    provider: str = "openai-compatible"
    name: str = Field(min_length=1)
    snapshot: str | None = None


class RunScope(StrictModel):
    type: ScopeType
    id: str = Field(min_length=1)
    field: str | None = None
    source_drawing_ids: list[str] = Field(default_factory=list)
    target_drawing_ids: list[str] = Field(default_factory=list)


class CallbackConfig(StrictModel):
    url: HttpUrl
    audience: str = Field(min_length=1)


class RunOptions(StrictModel):
    dry_run: bool = False
    keep_stage_artifacts: bool = True
    model_override: str | None = None


class CreateRunRequest(StrictModel):
    run_type: RunType
    project_id: str = Field(min_length=1)
    source_document_id: str = Field(min_length=1)
    feedback_id: str | None = None
    requested_by: str = Field(min_length=1)
    profile_hint: str | None = None
    expected_result_version: int | None = Field(default=None, ge=0)
    scope: RunScope
    callback: CallbackConfig | None = None
    options: RunOptions = Field(default_factory=RunOptions)

    @model_validator(mode="after")
    def validate_scoped_correction_feedback(self) -> CreateRunRequest:
        if self.run_type in {RunType.SCOPED_CORRECTION, RunType.SCOPED_REMEDIATION} and not self.feedback_id:
            raise ValueError("Scoped correction runs require feedback_id.")
        if self.scope.type == ScopeType.PROFILE and self.run_type not in {
            RunType.IMPROVEMENT_CANDIDATE,
            RunType.PROFILE_EVALUATION,
            RunType.PROFILE_CANARY,
        }:
            raise ValueError("PROFILE scope is reserved for improvement and evaluation runs.")
        return self


class AgentRun(StrictModel):
    agent_run_id: str = Field(default_factory=lambda: str(uuid4()))
    idempotency_key: str = Field(min_length=1)
    run_type: RunType
    status: RunStatus = RunStatus.QUEUED
    project_id: str
    source_document_id: str
    requested_by: str
    scope: RunScope
    feedback_id: str | None = None
    profile_hint: str | None = None
    expected_result_version: int | None = Field(default=None, ge=0)
    options: RunOptions = Field(default_factory=RunOptions)
    profile: ProfileRef | None = None
    parent_run_id: str | None = None
    current_stage: AgentStage | None = None
    error: EventError | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @classmethod
    def from_request(cls, request: CreateRunRequest, idempotency_key: str) -> AgentRun:
        return cls(
            idempotency_key=idempotency_key,
            run_type=request.run_type,
            project_id=request.project_id,
            source_document_id=request.source_document_id,
            requested_by=request.requested_by,
            scope=request.scope,
            feedback_id=request.feedback_id,
            profile_hint=request.profile_hint,
            expected_result_version=request.expected_result_version,
            options=request.options,
        )


class ArtifactRef(StrictModel):
    artifact_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    checksum: str | None = None


class EventError(StrictModel):
    code: str
    message: str
    retryable: bool = False


class AgentEvent(StrictModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_run_id: str = Field(min_length=1)
    seq: int = Field(ge=0)
    occurred_at: datetime = Field(default_factory=utc_now)
    event_type: EventType
    stage: AgentStage | None = None
    level: str = "INFO"
    scope: RunScope | None = None
    message: str = ""
    metrics: dict[str, int | float | str | bool | None] = Field(default_factory=dict)
    artifact_refs: list[str] = Field(default_factory=list)
    error: EventError | None = None
