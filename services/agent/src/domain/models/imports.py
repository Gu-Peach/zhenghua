"""Internal business-import and read-model contracts (not browser JWT APIs)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from src.domain.models.common import StrictModel


class ImportedDocument(StrictModel):
    project_id: str
    source_document_id: str
    attachment_id: str
    filename: str
    checksum: str
    size: int = Field(gt=0)
    page_count: int = Field(gt=0)
    persistence_backend: str = "supabase"


class ProjectTreeResponse(StrictModel):
    project_id: str
    name: str
    published_snapshot_id: str | None = None
    sources: list[dict[str, Any]]
    workspaces: list[dict[str, Any]]


class ProjectResultsResponse(StrictModel):
    project_id: str
    result_version_id: str | None = None
    result_version: int | None = None
    result_revision: int | None = None
    offset: int
    limit: int
    items: list[dict[str, Any]]
    has_more: bool


class RunStageSummaryResponse(StrictModel):
    agent_run_id: str
    status: str
    model_name: str | None
    profile: dict[str, Any] | None
    stages: list[dict[str, Any]]
    final_receipt: dict[str, Any] | None
    cost: float | None = None
    cost_status: str = "unknown"
