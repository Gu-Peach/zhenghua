"""Contracts for an independently callable, draft-only Profile Agent."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator

from src.domain.models.common import StrictModel


class ProfileError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class ProfileActor(StrictModel):
    user_id: UUID


class TemplateFields(StrictModel):
    """Unknown drawing conventions stay empty; they are never guessed from the ZH brand."""

    key: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    display_name: str = Field(min_length=1, max_length=120)
    adapter: Literal["zh_native", "abb_native", "zh_gantry_reel_native"] = "zh_native"
    company_signals: list[str] = Field(default_factory=list, max_length=20)
    wire_marker: str | None = Field(default=None, max_length=4000)
    grouping_rule: str | None = Field(default=None, max_length=4000)
    page_number_rule: str | None = Field(default=None, max_length=4000)
    page_naming_rule: str | None = Field(
        default=None,
        max_length=2000,
        description="填写业务页标到function/正整数页号的映射；实际文件名沿用提取器，任意文件名重写需额外代码适配",
    )
    cross_page_rule: str | None = Field(default=None, max_length=6000)
    cross_page_input_mode: Literal["source_and_target", "target_only"] = "source_and_target"
    reference_mode: Literal["function_page", "reversible_sheet", "adapter_change_required"] = "function_page"
    page_number_mode: Literal[
        "positive_integer", "reversible_positive_integer", "adapter_change_required"
    ] = "positive_integer"
    additional_rules: list[str] = Field(default_factory=list, max_length=30)
    open_questions: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("company_signals", "additional_rules", "open_questions")
    @classmethod
    def remove_blank_entries(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]


class ImageUse(StrictModel):
    attachment_id: UUID
    role: Literal["source_page", "target_page", "sample"]


class ExampleCase(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")
    stage: Literal["classification", "scan", "completion"]
    kind: Literal["positive", "negative"] = "positive"
    title: str = Field(min_length=1, max_length=240)
    images: list[ImageUse] = Field(min_length=1, max_length=4)
    expected: dict[str, Any]
    input: dict[str, Any] | None = None


class DraftCreate(StrictModel):
    draft_id: UUID = Field(default_factory=uuid4)
    key: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    display_name: str = Field(min_length=1, max_length=120)
    source_profile: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]*$")
    source_version: str | None = None


class Attachment(StrictModel):
    id: UUID
    filename: str
    path: str
    checksum: str
    mime_type: str
    origin: Literal["upload", "pdf_sample"] = "upload"


class DraftView(StrictModel):
    draft_id: UUID
    revision: int
    checksum: str
    key: str
    version: str
    source: dict[str, str] | None = None
    files: list[str]
    attachments: list[Attachment] = Field(default_factory=list)
    template: TemplateFields | None = None
    warnings: list[str] = Field(default_factory=list)


class PdfSampleRequest(StrictModel):
    revision: int = Field(ge=1)
    request_id: UUID = Field(default_factory=uuid4)
    filename: str = Field(min_length=1, max_length=200)
    content_base64: str = Field(min_length=1, max_length=70 * 1024 * 1024)
    stage: Literal["classification"] = "classification"


class SampledPdfPage(StrictModel):
    attachment_id: UUID
    pdf_page_number: int = Field(ge=1)


class PdfSampleInfo(StrictModel):
    request_id: UUID
    filename: str
    checksum: str
    page_count: int = Field(ge=1)
    pages: list[SampledPdfPage] = Field(min_length=1, max_length=2)
    notice: str | None = None


class PdfSampleResult(StrictModel):
    draft: DraftView
    sample: PdfSampleInfo


class FileEdit(StrictModel):
    path: str = Field(min_length=1, max_length=300)
    before_checksum: str | None = None
    content: str | None = Field(default=None, max_length=300000)
    operation: Literal["write", "delete"] = "write"


class EvidenceAnchor(StrictModel):
    path: str
    quote: str = Field(min_length=1, max_length=2000)


class Finding(StrictModel):
    category: Literal["rule_issue", "example_issue", "model_deviation", "mixed", "insufficient_evidence"]
    explanation: str = Field(min_length=1, max_length=4000)
    evidence: list[EvidenceAnchor] = Field(default_factory=list, max_length=12)
    missing_evidence: list[str] = Field(default_factory=list, max_length=12)


class ProposalRequest(StrictModel):
    summary: str = Field(min_length=1, max_length=4000)
    edits: list[FileEdit] = Field(min_length=1, max_length=20)
    findings: list[Finding] = Field(default_factory=list, max_length=12)


class FileDiff(StrictModel):
    path: str
    before: str | None
    after: str | None


class Proposal(ProposalRequest):
    id: UUID
    draft_id: UUID
    base_revision: int
    base_checksum: str
    status: Literal["pending", "accepted", "rejected"] = "pending"
    applied_revision: int | None = None
    diffs: list[FileDiff] = Field(default_factory=list)


class ProfileTurn(StrictModel):
    turn_id: UUID = Field(default_factory=uuid4)
    message: str = Field(min_length=1, max_length=12000, pattern=r"\S")
    intent: Literal["discuss", "edit"] = "discuss"
    expected_revision: int = Field(ge=1)
    observations: list[dict[str, Any]] = Field(default_factory=list, max_length=20)


class ValidationIssue(StrictModel):
    code: str
    path: str | None = None
    message: str


class ValidationReport(StrictModel):
    ready: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    case_count: int = 0
    schema_version: str = "extraction_stages_v1/review_1.0.0"


class ProfileReply(StrictModel):
    draft_id: UUID
    turn_id: UUID
    revision: int
    answer: str
    findings: list[Finding] = Field(default_factory=list)
    proposals: list[Proposal] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    validation: ValidationReport | None = None
    tool_limited: bool = False
    cached: bool = False
    model_calls: list[dict[str, Any]] = Field(default_factory=list)
    viewed_images: list[str] = Field(default_factory=list)


class ProfileEvent(StrictModel):
    type: Literal["tool_started", "tool_completed", "answer_delta", "completed"]
    tool: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    delta: str | None = None
    reply: ProfileReply | None = None


class ExportReceipt(StrictModel):
    draft_id: UUID
    revision: int
    key: str
    version: str
    checksum: str
    archive_path: str
    published: Literal[False] = False
