from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectInput(Model):
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("项目名称不能为空")
        return value.strip()


class LoginInput(Model):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1000)


class SessionUser(Model):
    id: str
    email: str
    name: str
    role: str


class SessionResponse(Model):
    accessToken: str
    expiresIn: int = Field(gt=0)
    user: SessionUser


class ImportResponse(Model):
    project_id: str
    source_document_id: str
    attachment_id: str
    filename: str
    checksum: str
    size: int = Field(gt=0)
    page_count: int = Field(gt=0)
    persistence_backend: str = "supabase"


class EditReceipt(BaseModel):
    model_config = ConfigDict(extra="ignore")
    changed: bool = True
    result_version_id: str | None = None
    result_version: int | None = None
    result_revision: int
    update_mode: Literal["in_place", "snapshot"] = "in_place"
    updated_connection_ids: list[str] = Field(default_factory=list)


class ConnectionFields(Model):
    voltage_level: str | None = Field(default=None, max_length=100)
    terminal_strip: str | None = Field(default=None, max_length=100)
    principle_number: str | None = Field(default=None, max_length=500)
    start_code: str | None = Field(default=None, max_length=500)
    start_description: str | None = Field(default=None, max_length=4000)
    start_terminal: str | None = Field(default=None, max_length=500)
    end_code: str | None = Field(default=None, max_length=500)
    end_description: str | None = Field(default=None, max_length=4000)
    end_terminal: str | None = Field(default=None, max_length=500)
    current_value: str | None = Field(default=None, max_length=100)
    remark: str | None = Field(default=None, max_length=4000)
    color_mark: str | None = Field(default=None, max_length=100)
    is_cross_page: Literal["same_page", "cross_page", "unknown"] | None = None


class ConnectionEdit(Model):
    result_version_id: UUID
    result_revision: int = Field(ge=1)
    record_version: int = Field(ge=1)
    changes: ConnectionFields


class ConnectionCreate(Model):
    result_version_id: UUID
    result_revision: int = Field(ge=1)
    wiring_unit_id: UUID
    source_drawing_id: UUID
    target_drawing_id: UUID | None = None
    fields: ConnectionFields

    @field_validator("fields")
    @classmethod
    def validate_new_terminal(cls, value: ConnectionFields) -> ConnectionFields:
        if not value.start_terminal or not value.start_terminal.strip():
            raise ValueError("新增端子必须提供起点端子")
        return value


class ConnectionDelete(Model):
    result_version_id: UUID
    result_revision: int = Field(ge=1)
    record_version: int = Field(ge=1)
    confirmed: Literal[True]


class ConnectionMutationReceipt(Model):
    result_version_id: str
    result_version: int
    result_revision: int
    connection_id: str
    action: Literal["add", "remove"]
    wire_number: int
    proposal_id: str
    idempotent: bool = False


class ReadModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class DrawingRead(ReadModel):
    id: str
    project_id: str
    workspace_id: str
    pdf_page_number: int
    workspace_page: str | None = None
    status: str
    image_url: str | None = None
    reference_note: str | None = None


class SourceRead(ReadModel):
    id: str
    original_filename: str


class WorkspaceRead(ReadModel):
    id: str
    code: str | None = None
    name: str
    drawings: list[DrawingRead] = Field(default_factory=list)


class WiringUnitRead(ReadModel):
    id: str
    workspace_id: str
    drawing_id: str | None = None
    wire_number: int
    voltage_level: str | None = None
    terminal_strip: str | None = None


class ResultRead(ReadModel):
    id: str
    version: int
    revision: int
    status: str = "draft"
    profile: dict[str, Any] | None = None


class RunRead(ReadModel):
    id: str
    status: str
    current_stage: str | None = None
    run_type: str


class ProjectRead(ReadModel):
    id: str
    name: str
    owner_id: str
    status: str
    standard_profile: str | None = None
    updated_at: str
    workspaces: list[WorkspaceRead] = Field(default_factory=list)
    sources: list[SourceRead] = Field(default_factory=list)
    result: ResultRead | None = None
    latest_run: RunRead | None = None


class ConnectionRow(ReadModel):
    connection_id: str
    project_id: str
    workspace_id: str
    workspace_name: str
    drawing_id: str | None = None
    workspace_page: str | None = None
    pdf_page_number: int | None = None
    wiring_unit_id: str
    wire_number: int
    core_order: int
    result_version_id: str
    result_version: int
    result_revision: int
    record_version: int
    principle_number: str | None = None
    voltage_level: str | None = None
    terminal_strip: str | None = None
    start_code: str | None = None
    start_description: str | None = None
    start_terminal: str | None = None
    end_code: str | None = None
    end_description: str | None = None
    end_terminal: str | None = None
    current_value: str | None = None
    remark: str | None = None
    color_mark: str | None = None
    is_cross_page: Literal["same_page", "cross_page", "unknown"]
    confidence: float | None = None
    needs_review: bool
    status: str


class RuleRead(ReadModel):
    id: str
    profile_key: str
    profile_version: str
    source_profile_checksum: str
    package_checksum: str
    status: str
    created_at: str
    published_at: str | None = None
    can_delete: bool = False


class RuleCreate(Model):
    base_package_id: UUID
    profile_key: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    display_name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    detection_summary: str = Field(min_length=1, max_length=4000)
    strong_signals: list[str] = Field(min_length=1, max_length=30)
    prompts: dict[
        Literal["classification_prompt", "page_scan_prompt", "cross_page_prompt"], str
    ] = Field(default_factory=dict)
    confirmed: Literal[True]

    @field_validator("display_name", "detection_summary")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("名称和识别说明不能为空")
        return value.strip()

    @field_validator("strong_signals")
    @classmethod
    def signals(cls, value: list[str]) -> list[str]:
        if any(not signal.strip() or len(signal) > 2000 for signal in value):
            raise ValueError("识别特征不能为空或超过 2000 字符")
        return [signal.strip() for signal in value]

    @field_validator("prompts")
    @classmethod
    def valid_prompts(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not prompt.strip() or len(prompt) > 100000 for prompt in value.values()):
            raise ValueError("Prompt 不能为空或超过 100000 字符")
        return value


class RuleCreateReceipt(Model):
    id: str
    profile_key: str
    status: Literal["active"]
    registered: Literal[True]


class RuleDeleteReceipt(Model):
    id: str
    status: Literal["retired"]
    historical_resources_retained: Literal[True]


class ResourceText(Model):
    path: str
    content: str


class ResourceImage(Model):
    path: str
    url: str


class ResourcePackage(Model):
    manifest: dict[str, Any]
    files: list[ResourceText]
    images: list[ResourceImage]


class ConnectionPage(Model):
    items: list[ConnectionRow]
    result_version_id: str | None = None
    result_version: int | None = None
    result_revision: int | None = None
    offset: int
    limit: int
    has_more: bool


class SupervisorTurn(Model):
    conversation_id: str = Field(min_length=1, max_length=200)
    turn_id: UUID
    project_id: UUID | None = None
    message: str = Field(min_length=1, max_length=8000)
    target_hint: dict[str, str] = Field(default_factory=dict, max_length=20)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=10)

    @field_validator("target_hint")
    @classmethod
    def validate_target_hints(cls, hints: dict[str, str]) -> dict[str, str]:
        allowed = {
            "agent_run_id",
            "result_version_id",
            "connection_id",
            "drawing_id",
            "workspace_id",
            "wire_number",
            "project_name",
            "workspace_name",
            "workspace_page",
            "terminal",
            "start_terminal",
            "end_terminal",
            "proposal_id",
            "candidate_id",
            "field",
        }
        if set(hints) - allowed or any(
            not value or len(value) > 500 for value in hints.values()
        ):
            raise ValueError("无效的目标提示字段")
        for key in {
            "agent_run_id",
            "result_version_id",
            "connection_id",
            "drawing_id",
            "workspace_id",
            "candidate_id",
        } & hints.keys():
            hints[key] = str(UUID(hints[key]))
        return hints
