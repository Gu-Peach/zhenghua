from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import Field, model_validator

from ..enums import SupervisorIntent, SupervisorTurnStatus, WorkflowKind
from .common import FrozenModel, StrictModel, utc_now


class SupervisorTargetHint(StrictModel):
    agent_run_id: str | None = None
    result_version_id: str | None = None
    connection_id: str | None = None
    drawing_id: str | None = None
    workspace_id: str | None = None
    wire_number: str | None = None
    project_name: str | None = None
    workspace_name: str | None = None
    workspace_page: str | None = None
    terminal: str | None = None
    proposal_id: str | None = None
    candidate_id: str | None = None
    field: str | None = None


class ConversationTurn(StrictModel):
    turn_id: str = Field(default_factory=lambda: str(uuid4()))
    conversation_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    project_id: str | None = None
    message: str = Field(min_length=1, max_length=8000)
    target_hint: SupervisorTargetHint = Field(default_factory=SupervisorTargetHint)
    attachment_ids: list[str] = Field(default_factory=list)
    occurred_at: datetime = Field(default_factory=utc_now)


class SupervisorModelOutput(StrictModel):
    intent: SupervisorIntent
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)
    requires_input: bool = False
    question: str | None = None
    extracted_hints: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_question(self) -> SupervisorModelOutput:
        if self.requires_input and not self.question:
            raise ValueError("requires_input decisions must include a question.")
        return self


class WorkflowCommand(FrozenModel):
    command_id: str = Field(default_factory=lambda: str(uuid4()))
    conversation_id: str
    turn_id: str
    user_id: str
    project_id: str | None
    workflow: WorkflowKind
    action: str = Field(min_length=1)
    target: SupervisorTargetHint
    payload: dict[str, Any] = Field(default_factory=dict)


class SupervisorDecision(StrictModel):
    turn_id: str
    conversation_id: str
    intent: SupervisorIntent
    confidence: float = Field(ge=0.0, le=1.0)
    status: SupervisorTurnStatus
    reason: str
    user_message: str
    requires_input: bool
    missing_fields: list[str] = Field(default_factory=list)
    command: WorkflowCommand | None = None
    agent_run_id: str | None = None

    @model_validator(mode="after")
    def validate_dispatch(self) -> SupervisorDecision:
        if self.status == SupervisorTurnStatus.DISPATCHED and self.command is None:
            raise ValueError("DISPATCHED decisions require a workflow command.")
        if self.status == SupervisorTurnStatus.WAITING_INPUT and not self.requires_input:
            raise ValueError("WAITING_INPUT decisions require input.")
        return self


class SupervisorUserEvent(FrozenModel):
    conversation_id: str
    turn_id: str | None = None
    agent_run_id: str | None = None
    event_type: str = Field(min_length=1)
    stage: str | None = None
    user_message: str = Field(min_length=1)
    requires_input: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=utc_now)
