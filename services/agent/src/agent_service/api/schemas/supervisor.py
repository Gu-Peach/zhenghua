from __future__ import annotations

from typing import Literal

from pydantic import Field

from ...application.workflow_registry import WorkflowDispatchReceipt
from ...domain.models.common import StrictModel
from ...domain.models.profile_detection import ProfileAssignment, ProfileDetectionResult
from ...domain.models.supervisor import (
    SupervisorDecision,
    SupervisorUserEvent,
)


class SupervisorTurnResponse(StrictModel):
    decision: SupervisorDecision
    receipt: WorkflowDispatchReceipt | None = None
    user_event: SupervisorUserEvent


class SupervisorUserEventsResponse(StrictModel):
    items: list[SupervisorUserEvent]


class ConversationAttachmentResponse(StrictModel):
    attachment_id: str
    filename: str
    size: int = Field(gt=0)


class ConversationHistoryMessage(StrictModel):
    role: Literal["user", "assistant"]
    content: str


class ConversationMemoryResponse(StrictModel):
    conversation_id: str
    user_id: str
    memory_backend: Literal["process_short_term"]
    model_name: str
    survives_restart: Literal[False]
    history: list[ConversationHistoryMessage]
    attachment_ids: list[str]
    pending_detection: ProfileDetectionResult | None = None
    profile_assignment: ProfileAssignment | None = None
    agent_run_id: str | None = None
