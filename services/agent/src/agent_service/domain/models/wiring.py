from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..enums import CrossPageState
from .extraction_stages import (
    CrossPageCompletionData as CrossPageCompletion,
)
from .extraction_stages import (
    DrawingEndpoint as Endpoint,
)
from .extraction_stages import (
    DrawingReference as ReferenceEvidence,
)
from .extraction_stages import (
    PageScanData as PageScanResult,
)
from .extraction_stages import (
    ScannedConnection as WireConnection,
)
from .extraction_stages import (
    ScannedWireUnit as WireUnit,
)

__all__ = [
    "CrossPageCompletion",
    "Endpoint",
    "ReferenceEvidence",
    "PageScanResult",
    "WireConnection",
    "WireUnit",
    "PageClassification",
    "WireRecord",
    "ExtractionResponse",
    "ExportRequest",
]


def parse_wire_unit(payload: Mapping[str, Any]) -> WireUnit:
    """Read an existing unit checkpoint, separating internal index metadata from model output."""
    data = {
        key: value for key, value in payload.items() if key not in {"_identity_project", "_identity_prefix"}
    }
    connections = []
    for connection in data.get("connections", []):
        copied = dict(connection)
        copied["references"] = [
            {
                key: value
                for key, value in reference.items()
                if key not in {"source_pdf_page", "direction", "target_page"}
            }
            for reference in copied.get("references", [])
        ]
        connections.append(copied)
    data["connections"] = connections
    return WireUnit.model_validate(data)


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
    is_cross_page: CrossPageState = CrossPageState.UNKNOWN
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
