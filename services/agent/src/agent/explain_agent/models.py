from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from src.domain.models.common import StrictModel


class ExplainActor(StrictModel):
    """Trusted identity supplied by the host, never by the language model."""

    user_id: UUID


ExactText = Annotated[str, Field(min_length=1, max_length=200, pattern=r"\S")]


class ConnectionQuery(StrictModel):
    """AND-combined exact filters; drawing_page always means the source business page."""

    connection_id: UUID | None = None
    drawing_page: ExactText | None = None
    pdf_page_number: int | None = Field(default=None, ge=1)
    target_drawing_page: ExactText | None = None
    target_pdf_page_number: int | None = Field(default=None, ge=1)
    workspace_code: ExactText | None = None
    principle_number: ExactText | None = None
    wire_number: ExactText | None = None
    start_terminal: ExactText | None = None
    end_terminal: ExactText | None = None
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=50, ge=1, le=100)

    @model_validator(mode="after")
    def require_filter(self) -> ConnectionQuery:
        if not self.exact_filters():
            raise ValueError("至少提供页码、原理号或端子等一个精确查询条件")
        return self

    def exact_filters(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True, exclude={"offset", "limit"})


class ExplainTurn(StrictModel):
    project_id: UUID
    connection_id: UUID | None = None
    query: ConnectionQuery | None = None
    conversation_id: UUID = Field(default_factory=uuid4)
    turn_id: UUID = Field(default_factory=uuid4)
    message: str = Field(
        default="请解释这一行的端子连接和信息来源。", min_length=1, max_length=8000, pattern=r"\S"
    )
    batch_id: str | None = Field(default=None, min_length=1, max_length=200)
    record_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def check_selection(self) -> ExplainTurn:
        if (self.connection_id is None) == (self.query is None):
            raise ValueError("connection_id与query必须且只能提供一个")
        if self.record_version is not None and self.connection_id is None:
            raise ValueError("record_version只用于单行入口")
        return self


class TerminalPosition(StrictModel):
    x: float = Field(ge=0, le=1, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, allow_inf_nan=False)
    pdf_page_number: int = Field(ge=1)


class ConnectionFacts(StrictModel):
    id: UUID
    project_id: UUID
    batch_id: str
    record_version: int = Field(ge=1)
    page_item_id: str | None = None
    workspace_code: str | None = None
    source_drawing_page: str | None = None
    source_pdf_page_number: int = Field(ge=1)
    target_drawing_page: str | None = None
    target_pdf_page_number: int | None = Field(default=None, ge=1)
    wire_number: str | None = None
    principle_number: str | None = None
    terminal_strip: str | None = None
    voltage_level: str | None = None
    start_code: str | None = None
    start_description: str | None = None
    start_terminal: str | None = None
    end_code: str | None = None
    end_description: str | None = None
    end_terminal: str | None = None
    current_value: str | None = None
    color_mark: str | None = None
    remark: str | None = None
    is_cross_page: bool = False
    needs_review: bool = False
    start_terminal_coordinates: TerminalPosition | None = None
    end_terminal_coordinates: TerminalPosition | None = None


class ProfileEvidence(StrictModel):
    key: str
    version: str | None = None
    checksum: str | None = None
    source: Literal["record_evidence", "project_reference"]


class DrawingEvidence(StrictModel):
    role: Literal["source", "target", "reference"]
    pdf_page_number: int
    drawing_page: str | None = None
    workspace_code: str | None = None
    image_url: str | None = None
    url_expires_in: int | None = None
    terminal_coordinates: TerminalPosition | None = None
    connection_ids: list[UUID] = Field(default_factory=list)


class EvidenceStep(StrictModel):
    id: str
    kind: Literal["record", "source", "target", "profile", "reference", "extraction", "review"]
    description: str
    facts: dict[str, Any] = Field(default_factory=dict)


class ExplainContext(StrictModel):
    project_name: str
    row: ConnectionFacts
    profile: ProfileEvidence | None = None
    drawings: list[DrawingEvidence] = Field(default_factory=list)
    recorded: dict[str, Any] = Field(default_factory=dict)
    evidence_path: list[EvidenceStep] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)

    def model_facts(self) -> dict[str, Any]:
        """Short-lived signed URLs and private storage paths never enter model prompts."""
        value = self.model_dump(mode="json")
        value["drawings"] = [
            drawing.model_dump(mode="json", exclude={"image_url", "url_expires_in"})
            for drawing in self.drawings
        ]
        return value


class ExplainResponse(StrictModel):
    conversation_id: UUID
    turn_id: UUID
    answer: str = Field(min_length=1)
    context: ExplainContext | SearchResult
    retrievals: list[SearchResult] = Field(default_factory=list)
    drawings: list[DrawingEvidence] = Field(default_factory=list)
    retrieval_limited: bool = False
    coverage: list[SearchCoverage] = Field(default_factory=list)
    visual_pages: list[int] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    history_reset: bool = False
    cached: bool = False


class SearchResult(StrictModel):
    project_name: str
    batch_id: str | None = None
    query: ConnectionQuery
    rows: list[ExplainContext] = Field(default_factory=list)
    drawings: list[DrawingEvidence] = Field(default_factory=list)
    has_more: bool = False
    next_offset: int | None = None
    gaps: list[str] = Field(default_factory=list)

    def model_facts(self) -> dict[str, Any]:
        value = self.model_dump(mode="json", exclude={"rows", "drawings"})
        value["rows"] = [row.model_facts() for row in self.rows]
        value["drawings"] = [
            item.model_dump(mode="json", exclude={"image_url", "url_expires_in"}) for item in self.drawings
        ]
        return value


class SearchCoverage(StrictModel):
    filters: dict[str, Any]
    returned_count: int
    complete: bool


class DrawingQuery(StrictModel):
    pdf_page_numbers: list[Annotated[int, Field(ge=1)]] = Field(min_length=1, max_length=4)


class ModelImage(StrictModel):
    pdf_page_number: int
    data_url: str = Field(repr=False)


class DrawingReadResult(StrictModel):
    images: list[ModelImage] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class ToolActivity(StrictModel):
    id: str
    name: Literal["load_connection", "search_connections", "view_drawings", "unsupported"]
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None


class ExplainEvent(StrictModel):
    type: Literal[
        "context", "retrieval", "answer_delta", "completed", "tool_started", "tool_completed", "tool_failed"
    ]
    conversation_id: UUID
    turn_id: UUID
    context: ExplainContext | SearchResult | None = None
    retrieval: SearchResult | None = None
    tool: ToolActivity | None = None
    delta: str | None = None
    result: ExplainResponse | None = None


class ExplainError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status
