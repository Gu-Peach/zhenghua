from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from .models import ConnectionFields, Model, ReadModel, WorkspaceRead


class ProfileReferenceCreate(Model):
    profile_key: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")


class ProfileReferenceRead(ReadModel):
    id: str
    profile_key: str
    profile_version: str
    checksum: str
    display_name: str
    resource_ref: str
    created_at: str = ""
    can_delete: bool = False


class LocalProfileOption(Model):
    profile_key: str
    profile_version: str
    display_name: str
    checksum: str


class SimpleProjectInput(Model):
    name: str = Field(min_length=1, max_length=200, pattern=r"\S")
    profile_id: UUID | None = None


class SimpleSourceRead(Model):
    id: str
    original_filename: str
    page_count: int = 0


class SimpleProjectRead(ReadModel):
    id: str
    name: str
    owner_id: str
    status: str
    profile_id: str
    standard_profile: str | None = None
    updated_at: str
    workspaces: list[WorkspaceRead] = Field(default_factory=list)
    sources: list[SimpleSourceRead] = Field(default_factory=list)
    batch_id: str | None = None
    extraction_available: Literal[False] = False
    source_saved: bool = False


class TerminalCoordinates(Model):
    """Normalized terminal center on its own full-page image, not a business page number."""

    x: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    y: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    pdf_page_number: int = Field(ge=1)


class SimpleConnectionRead(ReadModel):
    connection_id: str
    project_id: str
    batch_id: str
    workspace_id: str
    workspace_name: str
    drawing_id: str
    workspace_page: str | None = None
    pdf_page_number: int
    wire_number: str | None = None
    row_order: int
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
    start_terminal_coordinates: TerminalCoordinates | None = None
    end_terminal_coordinates: TerminalCoordinates | None = None
    current_value: str | None = None
    color_mark: str | None = None
    remark: str | None = None
    is_cross_page: bool
    needs_review: bool


class SimpleConnectionPage(Model):
    items: list[SimpleConnectionRead]
    batch_id: str | None = None
    offset: int
    limit: int
    has_more: bool


class SimpleConnectionEdit(Model):
    record_version: int = Field(ge=1)
    changes: ConnectionFields


class SimpleConnectionCreate(Model):
    batch_id: str = Field(min_length=1, max_length=200)
    source_drawing_id: UUID
    target_drawing_id: UUID | None = None
    wire_number: str | None = Field(default=None, max_length=200)
    fields: ConnectionFields


class SimpleConnectionDelete(Model):
    record_version: int = Field(ge=1)
    confirmed: Literal[True]


class SimpleMutationReceipt(Model):
    connection_id: str
    batch_id: str
    action: Literal["add", "edit", "remove"]
    record_version: int
    idempotent: bool = False


class SimpleImportRead(Model):
    project_id: str
    source_document_id: str
    attachment_id: str
    filename: str
    checksum: str
    size: int
    page_count: int
    extraction_started: Literal[False] = False


class DrawingIndexPage(ReadModel):
    pdf_page_number: int = Field(gt=0)
    workspace_code: str = ""
    drawing_page: str | None = None
    image_bucket: str = "project-assets"
    image_path: str | None = None
    status: str = "classified"


class DrawingIndex(ReadModel):
    pages: list[DrawingIndexPage] = Field(default_factory=list)
    source: dict[str, Any] = Field(default_factory=dict)
    active_batch_id: str | None = None
