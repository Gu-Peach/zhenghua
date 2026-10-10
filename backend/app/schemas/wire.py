from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Endpoint(BaseModel):
    """A structured endpoint read from one or more drawing pages."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    part: str | None = None
    location: str | None = None
    device: str | None = None
    name: str | None = None
    terminal_board: str | None = None
    terminal_code: str | None = None
    terminal_strip: str | None = None
    terminal: str | int | None = None

    @field_validator(
        "part", "location", "device", "name", "terminal_board", "terminal_code", "terminal_strip", mode="before"
    )
    @classmethod
    def blank_string_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class ReferenceEvidence(BaseModel):
    """A cross-page locator; it is not itself an endpoint."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    raw: str | None = None
    target_function: str | None = None
    target_drawing_page: int | None = None
    target_internal_page: int | None = None
    target_pdf_page: int | None = None
    target_column: int | None = None
    target_object: str | None = None
    external: bool = False
    reason: str | None = None


class WireConnection(BaseModel):
    """One physical connection. Multiple connections may share a line number."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    connection_id: str | None = None
    local_connection_id: str | None = None
    unit_id: str | None = None
    origin_pdf_page: int | None = None
    core_number: int | str | None = None
    color: str | None = None
    line_number: str | None = None
    current: str | int | float | None = None
    current_basis: str | None = None
    current_source_text: str | None = None
    start: Endpoint | None = None
    end: Endpoint | None = None
    intermediate_points: list[Endpoint] = Field(default_factory=list)
    references: list[ReferenceEvidence] = Field(default_factory=list)
    status: str = "complete"
    confidence: float | None = None
    remark: str | None = None
    source_note: str | None = None
    source_pdf_pages: list[int] = Field(default_factory=list)
    source_drawing_pages: list[str] = Field(default_factory=list)
    external_source_required: bool = False


class WireUnit(BaseModel):
    """Logical wiring-table unit, normally keyed by wire_number."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    unit_id: str
    wire_number: str | None = None
    project_no: str | None = None
    drawing_prefix: str | None = None
    attribute: str | None = None
    model: str | None = None
    spec: str | None = None
    length: int | float | str | None = None
    current: str | int | float | None = None
    cable_context: str | None = None
    unit_identity_confidence: str = "high"
    connections: list[WireConnection] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    source_drawing_pages: list[str] = Field(default_factory=list)
    status: str = "complete"
    confidence: float | None = None


class PageScanResult(BaseModel):
    """Pydantic envelope returned by the page-scanning VLM call."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    pdf_page_number: int | None = None
    drawing_function: str | None = None
    drawing_page_number: int | None = None
    drawing_object_location: str | None = None
    blank: bool = False
    needs_review: bool = False
    units: list[WireUnit] = Field(default_factory=list)
    page_references: list[ReferenceEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CrossPageCompletion(BaseModel):
    """One VLM answer used to complete a single cross-page table row."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    task_id: str | None = None
    end: Endpoint | None = None
    intermediate_points: list[Endpoint] = Field(default_factory=list)
    current: str | int | float | None = None
    current_basis: str | None = None
    current_source_text: str | None = None
    status: str = "needs_review"
    needs_review: bool = False
    confidence: float | None = None
    source_note: str | None = None
    warnings: list[str] = Field(default_factory=list)


class PageClassification(BaseModel):
    """Stage-one identity read from a drawing title block."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    plant_function: str | None = None
    page_number: int | None = None
    blank: bool = False
    non_wiring: bool = False
    confidence: float | None = None
    needs_review: bool = False
    reason: str | None = None


class WireRecord(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    wire_number: str | None = Field(default=None, description="放线表线号，如 0272、4111")
    attribute: str | None = Field(default=None, description="放线表属性，如 D")
    model: str | None = Field(default=None, description="电缆型号，如 CJV/DA")
    length: int | float | str | None = Field(default=None, description="电缆长度")
    current: str | int | float | None = None
    current_basis: str | None = None
    current_source_text: str | None = None

    line_number: str | None = Field(default=None, description="图纸原理号，如 003G0121、082R5001")
    core_number: int | str | None = None
    color: str | None = None
    spec: str | None = None
    start_part: str | None = None
    start_location: str | None = None
    start_device: str | None = None
    start_name: str | None = None
    start_terminal_board: str | None = None
    start_terminal_code: str | None = None
    start_terminal: int | str | None = None
    end_part: str | None = None
    end_location: str | None = None
    end_device: str | None = None
    end_name: str | None = None
    end_terminal_board: str | None = None
    end_terminal_code: str | None = None
    end_terminal: int | str | None = None
    terminal_strip: str | None = None
    remark: str | None = None
    confidence: float | None = None
    source_note: str | None = None
    source_image: str | None = None
    # Filled by the backend from the rendered PDF page manifest.
    source_pages: list[int] = Field(default_factory=list)
    drawing_page: str | None = None
    source_type: str | None = None
    external_source_required: bool = False
    # Logical-unit and cross-page provenance fields. These are appended so the
    # legacy flat API/XLSX column order remains stable for existing clients.
    unit_id: str | None = None
    connection_id: str | None = None
    start_terminal_strip: str | None = None
    end_terminal_strip: str | None = None
    intermediate_points: list[dict[str, Any]] = Field(default_factory=list)
    references: list[dict[str, Any]] = Field(default_factory=list)
    drawing_function: str | None = None
    drawing_page_number: int | None = None
    pdf_page_number: int | None = None
    drawing_source_pages: list[str] = Field(default_factory=list)
    status: str = "complete"
    unit_identity_confidence: str | None = None

    @field_validator(
        "wire_number",
        "attribute",
        "model",
        "line_number",
        "color",
        "spec",
        "start_part",
        "start_location",
        "start_device",
        "start_name",
        "start_terminal_board",
        "start_terminal_code",
        "end_part",
        "end_location",
        "end_device",
        "end_name",
        "end_terminal_board",
        "end_terminal_code",
        "terminal_strip",
        "remark",
        "source_note",
        "source_image",
        "source_type",
        mode="before",
    )
    @classmethod
    def blank_string_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value: Any) -> Any:
        if value in (None, ""):
            return None
        try:
            score = float(value)
        except (TypeError, ValueError):
            return None
        return max(0.0, min(1.0, score))


class ExtractionResponse(BaseModel):
    record_count: int
    records: list[WireRecord]
    sources: list[str]


class ExportRequest(BaseModel):
    records: list[WireRecord]
    sheet_title: str | None = "放线表"
    filename: str | None = "wiring-table.xlsx"
