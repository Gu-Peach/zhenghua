"""Incremental publication contract, independent of HTTP and database adapters."""

from __future__ import annotations

from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.agent.extraction_agent.domain.models.wiring import WireRecord
from src.domain.models.runs import ProfileRef


class WorkerRun(BaseModel):
    id: UUID
    project_id: UUID
    requested_by: UUID
    profile: ProfileRef
    options: dict[str, Any]


class WorkerProject(BaseModel):
    id: UUID
    owner_id: UUID
    source_pdf_bucket: str
    source_pdf_path: str
    drawing_index: dict[str, Any]


class WorkerLease(BaseModel):
    worker: str
    token: UUID


class WorkerClaim(BaseModel):
    """Validate the external claim before its IDs are used in paths or model requests."""

    run: WorkerRun
    project: WorkerProject
    lease: WorkerLease

    @model_validator(mode="after")
    def check_scope(self) -> WorkerClaim:
        if self.run.project_id != self.project.id or self.run.requested_by != self.project.owner_id:
            raise ValueError("Claimed project owner mismatch")
        if self.run.options.get("workflow") != "simple_extraction_v1":
            raise ValueError("Claimed workflow mismatch")
        prefix = f"projects/{self.project.id}/"
        if not self.project.source_pdf_path.startswith(prefix) or ".." in self.project.source_pdf_path.split(
            "/"
        ):
            raise ValueError("Claimed source scope mismatch")
        return self


class PublishedPage(BaseModel):
    pdf_page_number: int = Field(ge=1)
    workspace_code: str = ""
    drawing_page: str | None = None
    image_bucket: str = "project-assets"
    image_path: str
    status: str


class PublishedRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    project_id: str
    batch_id: str
    page_item_id: str
    row_order: int
    workspace_code: str
    source_drawing_page: str | None
    source_pdf_page_number: int = Field(ge=1)
    target_drawing_page: str | None = None
    target_pdf_page_number: int | None = Field(default=None, ge=1)
    wire_number: str | None = None
    principle_number: str | None = None
    terminal_strip: str | None = None
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
    start_terminal_coordinates: dict[str, Any] | None = None
    end_terminal_coordinates: dict[str, Any] | None = None
    evidence: dict[str, Any]


class ExtractionStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal[
        "rendered", "classified", "scan", "completion", "page_completed", "finished", "failed", "cache"
    ]
    stage: str
    page: PublishedPage | None = None
    pdf_page_number: int | None = None
    rows: list[PublishedRow] = Field(default_factory=list)
    snapshot: dict[str, Any] | None = None
    error: dict[str, str] | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


def published_rows(
    state: dict[str, Any],
    *,
    project_id: str,
    run_id: str,
    profile: dict[str, Any],
    number: int,
) -> list[PublishedRow]:
    """Keep identity across scan/completion; physical pages never use line-number guesses."""
    pages = {int(p["page_number"]): p for p in state["pages"]}
    records = [r for group in state.get("wiring_records", {}).values() for r in group]
    result = []
    for order, value in enumerate(records):
        record = value if isinstance(value, WireRecord) else WireRecord.model_validate(value)
        if record.pdf_page_number != number:
            continue
        item = f"{record.unit_id}:{record.connection_id}"
        if not record.connection_id or not record.unit_id:
            raise ValueError("Published connection requires a stable scan identity")
        matched = [
            t
            for t in state.get("cross_page_tasks", [])
            if t.get("unit_id") == record.unit_id
            and t.get("connection_id") == record.connection_id
            and (state.get("cross_page_results", {}).get(t["task_id"], {}).get("end") or {}).get("terminal")
        ]
        target_numbers = {int(t["target_pdf_page"]) for t in matched if t.get("target_pdf_page")}
        target = (
            record.end_terminal_coordinates.pdf_page_number
            if record.end_terminal_coordinates
            else (next(iter(target_numbers)) if len(target_numbers) == 1 and record.end_terminal else None)
        )
        if target == number:
            target = None
        target_page = pages.get(target or -1, {})
        result.append(
            PublishedRow(
                id=str(uuid5(NAMESPACE_URL, f"extraction-row:{project_id}:{run_id}:{number}:{item}")),
                project_id=project_id,
                batch_id=run_id,
                page_item_id=item,
                row_order=order,
                workspace_code=str(pages[number].get("function") or ""),
                source_drawing_page=_drawing_label(pages[number]),
                source_pdf_page_number=number,
                target_pdf_page_number=target,
                target_drawing_page=_drawing_label(target_page),
                wire_number=record.wire_number,
                principle_number=record.line_number,
                terminal_strip=record.terminal_strip,
                start_code=record.start_device,
                start_description=record.start_name,
                start_terminal=_text(record.start_terminal),
                end_code=record.end_device,
                end_description=record.end_name,
                end_terminal=_text(record.end_terminal),
                current_value=_text(record.current),
                color_mark=record.color,
                remark=record.remark,
                is_cross_page=bool(record.references or target or str(record.is_cross_page) == "cross_page"),
                needs_review=record.needs_review,
                start_terminal_coordinates=record.start_terminal_coordinates.model_dump()
                if record.start_terminal_coordinates
                else None,
                end_terminal_coordinates=record.end_terminal_coordinates.model_dump()
                if record.end_terminal_coordinates
                else None,
                evidence={
                    "profile": profile,
                    "processing_status": record.processing_status,
                    "review_reasons": [r.model_dump() for r in record.review_reasons],
                    "record": record.model_dump(mode="json"),
                    "voltage_level": record.attribute,
                },
            )
        )
    return result


def _text(value: Any) -> str | None:
    return str(value) if value is not None else None


def _drawing_label(page: dict[str, Any]) -> str | None:
    if page.get("function") and page.get("internal_page") is not None:
        return f"{str(page['function']).replace('.', '')}{int(page['internal_page']):02d}"
    return None
