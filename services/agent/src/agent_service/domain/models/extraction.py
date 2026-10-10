from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from .common import StrictModel
from .profiles import ProfileBinding


class LegacyExtractionRequest(StrictModel):
    """Migration-only request used by the legacy ZH adapter."""

    run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    pdf_path: Path
    output_path: Path
    profile: ProfileBinding
    max_pdf_pages: int = Field(default=0, ge=0)
    output_mode: str = Field(default="library", pattern=r"^(library|single_xlsx)$")


class ExtractionExecutionResult(StrictModel):
    run_id: str
    state: dict[str, Any]
    extraction_errors: dict[str, str] = Field(default_factory=dict)
    validation_warnings: list[str] = Field(default_factory=list)
    adapter: str
