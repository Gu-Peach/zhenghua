from __future__ import annotations

from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from src.agent.explain_agent.models import RescanTargetBinding
from src.domain.models.common import StrictModel


class AssistantScope(StrictModel):
    project_id: UUID | None = None
    project_name: str | None = None
    workspace_code: str | None = Field(default=None, max_length=200)
    workspace_id: UUID | None = None
    drawing_id: UUID | None = None
    drawing_page: str | None = Field(default=None, max_length=200)
    pdf_page_number: int | None = Field(default=None, ge=1)
    connection_ids: list[UUID] = Field(default_factory=list, max_length=200)
    batch_id: str | None = None


class AssistantConversationCreate(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    title: str = Field(default="新对话", min_length=1, max_length=120)


class AssistantTurnInput(StrictModel):
    turn_id: UUID = Field(default_factory=uuid4)
    message: str = Field(min_length=1, max_length=8000, pattern=r"\S")
    scope: AssistantScope = Field(default_factory=AssistantScope)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=6)


class AssistantEvent(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    turn_id: UUID
    type: Literal[
        "answer_delta",
        "tool_started",
        "tool_completed",
        "navigate",
        "selection_required",
        "task_started",
        "proposal_ready",
        "completed",
        "error",
    ]
    message: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class AssistantTurnRead(StrictModel):
    id: UUID
    conversation_id: UUID
    status: str
    request: AssistantTurnInput
    events: list[AssistantEvent] = Field(default_factory=list)
    answer: str = ""
    error: str | None = None
    created_at: str


class AssistantConversationRead(StrictModel):
    id: UUID
    title: str
    context: AssistantScope = Field(default_factory=AssistantScope)
    created_at: str
    updated_at: str
    turns: list[AssistantTurnRead] = Field(default_factory=list)
    has_more: bool = False
    next_offset: int | None = None


class AssistantInternalTurn(StrictModel):
    conversation_id: UUID
    turn_id: UUID
    message: str
    scope: AssistantScope
    history: list[dict[str, str]] = Field(default_factory=list, max_length=24)
    attachments: list[dict[str, Any]] = Field(default_factory=list, max_length=6)


class AssistantToolCall(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)


class AssistantActionRead(StrictModel):
    id: UUID
    conversation_id: UUID
    turn_id: UUID
    tool_name: str
    status: str
    result: dict[str, Any] = Field(default_factory=dict)
    checksum: str | None = None


class AssistantActionDecision(StrictModel):
    checksum: str
    accepted: bool


class AssistantAttachmentInput(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    filename: str = Field(min_length=1, max_length=200)
    content_base64: str = Field(min_length=1, max_length=72_000_000, repr=False)
    project_id: UUID | None = None
    pdf_page_number: int | None = Field(default=None, ge=1)
    role: Literal["source", "target", "detail", "pdf"] = "detail"


class AssistantAttachmentRead(StrictModel):
    id: UUID
    conversation_id: UUID
    filename: str
    mime_type: str
    project_id: UUID | None = None
    pdf_page_number: int | None = None
    role: str
    checksum: str


class FindTargets(StrictModel):
    project_name: str | None = Field(default=None, max_length=200)
    workspace_code: str | None = Field(default=None, max_length=200)
    drawing_page: str | None = Field(default=None, max_length=200)


class ScopeTool(StrictModel):
    scope: AssistantScope = Field(default_factory=AssistantScope)


class NavigateTool(ScopeTool):
    view: Literal["table", "preview"] = "table"


class ExplainScope(ScopeTool):
    question: str = Field(min_length=1, max_length=4000)


class SearchConnections(ScopeTool):
    principle_number: str | None = Field(default=None, max_length=512)
    principle_numbers: list[str] = Field(default_factory=list, max_length=200)
    start_terminal: str | None = Field(default=None, max_length=512)
    end_terminal: str | None = Field(default=None, max_length=512)
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=50, ge=1, le=100)

    @model_validator(mode="after")
    def check_numbers(self) -> SearchConnections:
        if self.principle_number and self.principle_numbers:
            raise ValueError("单个原理号和多原理号不能同时指定")
        if any(not value.strip() or len(value) > 512 for value in self.principle_numbers):
            raise ValueError("原理号不能为空或超过512字符")
        return self


class AttachmentBinding(StrictModel):
    attachment_id: UUID
    pdf_page_number: int = Field(ge=1)
    role: Literal["source", "target"] = "source"


class RescanScopeTool(ScopeTool):
    fields: Literal["all", "start", "end"] = "all"
    instructions: str = Field(default="", max_length=4000)
    bindings: list[AttachmentBinding] = Field(default_factory=list, max_length=6)
    target_bindings: list[RescanTargetBinding] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def validate_targets(self) -> RescanScopeTool:
        if self.target_bindings and self.fields != "end":
            raise ValueError("目标页绑定仅用于终点重扫")
        identifiers = [item for binding in self.target_bindings for item in binding.connection_ids]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("同一连接不能绑定多个目标页")
        if self.scope.connection_ids and set(identifiers) - set(self.scope.connection_ids):
            raise ValueError("目标页绑定超出选中连接范围")
        return self


class ProfileDiagnosis(ScopeTool):
    question: str = Field(min_length=1, max_length=4000)
    propose_changes: bool = False


class TaskTool(StrictModel):
    action_id: UUID


class OpenPageTool(StrictModel):
    page: Literal["extraction", "profile"]
    profile_id: UUID | None = None


class DocumentTool(StrictModel):
    attachment_id: UUID
    profile_key: str = Field(min_length=1, max_length=80)


class EmptyTool(StrictModel):
    pass
