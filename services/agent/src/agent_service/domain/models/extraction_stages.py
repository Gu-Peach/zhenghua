from __future__ import annotations

from pathlib import Path

from pydantic import Field

from ..enums import CrossPageState
from .common import StrictModel
from .profiles import ProfileBinding
from .runs import ProfileRef


class DrawingPageInput(StrictModel):
    """A rendered source page; physical and drawing-local numbering stay distinct."""

    pdf_page_number: int = Field(ge=1)
    image_path: Path
    drawing_id: str | None = None
    storage_bucket: str | None = None
    storage_path: str | None = None
    plant_function: str | None = None
    drawing_page_number: int | None = Field(default=None, ge=1)
    object_location: str | None = None
    blank: bool = False
    non_wiring: bool = False


class ExtractionStageRequest(StrictModel):
    run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    profile: ProfileBinding


class PageClassificationRequest(ExtractionStageRequest):
    page: DrawingPageInput
    known_context: str = ""


class PageScanRequest(ExtractionStageRequest):
    page: DrawingPageInput
    page_context: str = ""


class CrossPageCompletionRequest(ExtractionStageRequest):
    task_id: str = Field(min_length=1)
    target_page: DrawingPageInput
    task_context: str = Field(min_length=1)


class PageClassificationData(StrictModel):
    plant_function: str | None = None
    drawing_page_number: int | None = Field(default=None, ge=1)
    blank: bool = False
    non_wiring: bool = False
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    needs_review: bool = False
    reason: str | None = None


class DrawingEndpoint(StrictModel):
    part: str | None = None
    location: str | None = None
    device: str | None = None
    name: str | None = None
    terminal_board: str | None = None
    terminal_code: str | None = None
    terminal_strip: str | None = None
    terminal: str | int | None = None


class DrawingReference(StrictModel):
    raw: str | None = None
    target_function: str | None = None
    target_drawing_page: int | None = Field(default=None, ge=1)
    target_internal_page: int | None = Field(default=None, ge=1)
    target_pdf_page: int | None = Field(default=None, ge=1)
    target_column: int | None = Field(default=None, ge=1)
    target_object: str | None = None
    external: bool = False
    reason: str | None = None


class ScannedConnection(StrictModel):
    connection_id: str | None = None
    local_connection_id: str | None = None
    unit_id: str | None = None
    origin_pdf_page: int | None = Field(default=None, ge=1)
    core_number: int | str | None = None
    color: str | None = None
    line_number: str | None = None
    current: str | int | float | None = None
    current_basis: str | None = None
    current_source_text: str | None = None
    start: DrawingEndpoint | None = None
    end: DrawingEndpoint | None = None
    intermediate_points: list[DrawingEndpoint] = Field(default_factory=list)
    references: list[DrawingReference] = Field(default_factory=list)
    is_cross_page: CrossPageState = CrossPageState.UNKNOWN
    status: str = "complete"
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    remark: str | None = None
    source_note: str | None = None
    source_pdf_pages: list[int] = Field(default_factory=list)
    source_drawing_pages: list[str] = Field(default_factory=list)
    external_source_required: bool = False


class ScannedWireUnit(StrictModel):
    unit_id: str = Field(min_length=1)
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
    connections: list[ScannedConnection] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    source_drawing_pages: list[str] = Field(default_factory=list)
    status: str = "complete"
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class PageScanData(StrictModel):
    pdf_page_number: int | None = Field(default=None, ge=1)
    drawing_function: str | None = None
    drawing_page_number: int | None = Field(default=None, ge=1)
    drawing_object_location: str | None = None
    blank: bool = False
    needs_review: bool = False
    units: list[ScannedWireUnit] = Field(default_factory=list)
    page_references: list[DrawingReference] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CrossPageCompletionData(StrictModel):
    task_id: str | None = None
    end: DrawingEndpoint | None = None
    intermediate_points: list[DrawingEndpoint] = Field(default_factory=list)
    current: str | int | float | None = None
    current_basis: str | None = None
    current_source_text: str | None = None
    status: str = "needs_review"
    needs_review: bool = False
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_note: str | None = None
    warnings: list[str] = Field(default_factory=list)


class StageResultMetadata(StrictModel):
    run_id: str
    project_id: str
    profile: ProfileRef


class PageClassificationResult(StageResultMetadata):
    pdf_page_number: int = Field(ge=1)
    plant_function: str | None = None
    drawing_page_number: int | None = Field(default=None, ge=1)
    blank: bool = False
    non_wiring: bool = False
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    needs_review: bool = False
    reason: str | None = None


class PageScanResult(StageResultMetadata):
    pdf_page_number: int = Field(ge=1)
    drawing_function: str | None = None
    drawing_page_number: int | None = Field(default=None, ge=1)
    drawing_object_location: str | None = None
    blank: bool = False
    needs_review: bool = False
    units: list[ScannedWireUnit] = Field(default_factory=list)
    page_references: list[DrawingReference] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CrossPageCompletionResult(StageResultMetadata):
    task_id: str
    end: DrawingEndpoint | None = None
    intermediate_points: list[DrawingEndpoint] = Field(default_factory=list)
    current: str | int | float | None = None
    current_basis: str | None = None
    current_source_text: str | None = None
    status: str = "needs_review"
    needs_review: bool = False
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_note: str | None = None
    warnings: list[str] = Field(default_factory=list)
