from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .wire import WireRecord


class PageAsset(BaseModel):
    page_id: str
    page_number: int
    filename: str
    url: str
    drawing_function: str | None = None
    drawing_page_number: int | None = None
    drawing_object_location: str | None = None
    blank: bool = False


class WireTableGroup(BaseModel):
    group_id: str
    title: str
    pages: list[int]
    reason: str | None = None
    status: str = "pending"
    record_count: int = 0
    records: list[WireRecord] = Field(default_factory=list)
    table_headers: list[str] = Field(default_factory=list)
    table_rows: list[list[Any]] = Field(default_factory=list)
    json_url: str | None = None
    xlsx_url: str | None = None
    import_xlsx_url: str | None = None
    import_xls_url: str | None = None
    error: str | None = None


class JobSummary(BaseModel):
    job_id: str
    name: str
    status: str
    created_at: datetime
    source_filename: str
    source_url: str | None = None
    page_count: int
    group_count: int
    record_count: int
    status_message: str | None = None


class JobDetail(JobSummary):
    pages: list[PageAsset]
    groups: list[WireTableGroup]
    table_headers: list[str] = Field(default_factory=list)
    table_rows: list[list[Any]] = Field(default_factory=list)
    manifest: dict[str, Any] = Field(default_factory=dict)


class ProcessUploadResponse(BaseModel):
    job: JobDetail
