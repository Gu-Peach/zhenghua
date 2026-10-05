from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WireRecord(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    wire_number: str | None = Field(default=None, description="放线表线号，如 0272、4111")
    attribute: str | None = Field(default=None, description="放线表属性，如 D")
    model: str | None = Field(default=None, description="电缆型号，如 CJV/DA")
    length: int | float | str | None = Field(default=None, description="电缆长度")

    line_number: str | None = Field(default=None, description="图纸原理号，如 003G0121、082R5001")
    core_number: int | str | None = None
    color: str | None = None
    spec: str | None = None
    start_part: str | None = None
    start_location: str | None = None
    start_device: str | None = None
    start_name: str | None = None
    start_terminal: int | str | None = None
    end_part: str | None = None
    end_location: str | None = None
    end_device: str | None = None
    end_name: str | None = None
    end_terminal: int | str | None = None
    terminal_strip: str | None = None
    remark: str | None = None
    confidence: float | None = None
    source_note: str | None = None
    source_image: str | None = None
    # Filled by the backend from the rendered PDF page manifest.
    source_pages: list[int] = Field(default_factory=list)
    source_type: str | None = None
    external_source_required: bool = False

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
        "end_part",
        "end_location",
        "end_device",
        "end_name",
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
