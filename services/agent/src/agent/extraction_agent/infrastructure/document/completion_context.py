from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import Field

from src.agent.extraction_agent.domain.models.extraction_stages import (
    CrossPageCompletionRequest,
    DrawingReference,
)
from src.agent.extraction_agent.infrastructure.document.completion_view import CompletionInputView
from src.domain.models.common import StrictModel


class CompletionPageContext(StrictModel):
    pdf_page_number: int | None = Field(default=None, ge=1)
    drawing_function: str | None = None
    drawing_page_number: int | None = Field(default=None, ge=1)
    object_location: str | None = None
    drawing_label: str | None = None


class CompletionSourceComponent(StrictModel):
    device: str | None = None
    location: str | None = None


class TargetOnlyCompletionContext(StrictModel):
    """Read-only source facts plus the address of the one supplied target image."""

    context_version: Literal[2, 3] = 2
    task_id: str
    source_page: CompletionPageContext
    target_page: CompletionPageContext
    image_view: CompletionInputView | None = None
    source_component: CompletionSourceComponent | None = None
    line_number: str | None = None
    signal_name: str | None = None
    core_number: int | str | None = None
    references: list[DrawingReference] = Field(default_factory=list)
    current: str | int | float | None = None
    current_basis: str | None = None
    current_source_text: str | None = None


def target_only_context(request: CrossPageCompletionRequest) -> TargetOnlyCompletionContext:
    """Project the graph task without images, paths, unrelated rows or diagnostics."""
    task: dict[str, Any] = json.loads(request.task_context)
    # Project old compact tasks too; source pins/coordinates never reach the VLM.
    if task.get("context_version") in (1, 2, 3):
        compact = dict(task)
        old_start = compact.pop("start", None) or {}
        compact.pop("endpoint_role", None)
        compact.pop("direction_basis", None)
        compact.pop("image_view", None)
        component = compact.get("source_component") or old_start
        compact["source_component"] = (
            {key: component.get(key) for key in CompletionSourceComponent.model_fields} if component else None
        )
        compact["context_version"] = 2
        compact["task_id"] = request.task_id
        target = dict(compact.get("target_page") or {})
        target["pdf_page_number"] = request.target_page.pdf_page_number
        compact["target_page"] = target
        return TargetOnlyCompletionContext.model_validate(compact)
    record = task.get("source_record") or {}
    source = dict(task.get("source_page_context") or {})
    source_fallback = {
        "pdf_page_number": task.get("source_pdf_page") or record.get("pdf_page_number"),
        "drawing_function": record.get("drawing_function"),
        "drawing_page_number": record.get("drawing_page_number"),
    }
    for key, value in source_fallback.items():
        source[key] = source.get(key) or value
    if request.source_page is not None:
        for key, page_key in (
            ("pdf_page_number", "pdf_page_number"),
            ("drawing_function", "plant_function"),
            ("drawing_page_number", "drawing_page_number"),
            ("object_location", "object_location"),
        ):
            source[key] = source.get(key) or getattr(request.source_page, page_key)
    target = dict(task.get("target_page_context") or {})
    target["pdf_page_number"] = request.target_page.pdf_page_number
    target["drawing_function"] = target.get("drawing_function") or request.target_page.plant_function
    target["drawing_page_number"] = (
        target.get("drawing_page_number") or request.target_page.drawing_page_number
    )
    target["object_location"] = target.get("object_location") or request.target_page.object_location
    component = {key: record.get(f"start_{key}") for key in CompletionSourceComponent.model_fields}
    return TargetOnlyCompletionContext(
        task_id=request.task_id,
        source_page=CompletionPageContext.model_validate(source),
        target_page=CompletionPageContext.model_validate(target),
        source_component=CompletionSourceComponent.model_validate(component)
        if any(component.values())
        else None,
        line_number=task.get("line_number") or record.get("line_number"),
        signal_name=record.get("signal_name"),
        core_number=task.get("core_number"),
        references=[DrawingReference.model_validate(item) for item in task.get("references") or []],
        current=record.get("current"),
        current_basis=record.get("current_basis"),
        current_source_text=record.get("current_source_text"),
    )
