from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, cast

from agent_service.application.document_extraction.runtime import (
    GraphRuntime,
)
from agent_service.domain.enums import (
    ErrorCode,
)
from agent_service.domain.models.drawing_index import (
    DrawingIndex,
    DrawingPage,
    DrawingReference,
)
from agent_service.domain.models.image_payload import (
    ImagePayload,
)
from agent_service.domain.models.wiring import (
    Endpoint,
    WireConnection,
    WireRecord,
    WireUnit,
)
from agent_service.graphs.document_extraction.state import (
    PageMeta,
)

logger = logging.getLogger(__name__)


def _normalize_plant_function(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper().lstrip("=")
    return normalized or None


def _safe_plant_function_folder(value: str) -> str:
    normalized = _normalize_plant_function(value) or "UNKNOWN"
    return re.sub(r"[^0-9A-Z._-]+", "_", normalized).strip("._") or "UNKNOWN"


def _drawing_index_from_dict(value: Mapping[str, Any]) -> Any:

    pages = [DrawingPage(**page) for page in value.get("pages", [])]
    references = [DrawingReference(**reference) for reference in value.get("references", [])]
    return DrawingIndex(
        pdf_path=str(value.get("pdf_path") or ""),
        pages=pages,
        references=references,
        page_lookup=dict(value.get("page_lookup") or {}),
    )


def _is_fatal_model_request_error(exc: Exception) -> bool:
    return getattr(exc, "code", None) in {ErrorCode.INVALID_REQUEST, ErrorCode.RUN_CANCELLED}


def _page_scan_context(
    page: PageMeta,
    drawing_index: Mapping[str, Any],
    *,
    related_pages: list[ImagePayload] | None = None,
) -> str:
    return json.dumps(
        {
            "pdf_page_number": page["page_number"],
            "drawing_function": page.get("function"),
            "drawing_page_number": page.get("internal_page"),
            "drawing_object_location": page.get("object_loc"),
            "known_references": [],
            "related_target_images": [],
        },
        ensure_ascii=False,
    )


def _find_or_create_unit_id(
    wire_units: Mapping[str, Mapping[str, Any]],
    unit: WireUnit,
    page: PageMeta,
    page_number: int,
    local_unit_index: int,
) -> str:
    wire_number = _text_value(unit.wire_number)
    project = _text_value(page.get("project_no")) or "unknown-project"
    prefix = _text_value(page.get("drawing_prefix")) or _text_value(page.get("function")) or "unknown-prefix"
    context = _unit_cable_context(unit)
    if wire_number:
        for existing_id, existing in wire_units.items():
            if existing.get("wire_number") != wire_number:
                continue
            return existing_id
    raw_key = (
        f"{project}|{wire_number or 'missing'}|{context or 'none'}"
        if wire_number
        else f"{project}|{prefix}|page:{page_number}|local:{local_unit_index}"
    )
    digest = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:8]
    slug = re.sub(r"[^0-9A-Za-z_-]+", "-", raw_key).strip("-").lower()[:70]
    return f"unit-{slug}-{digest}" if slug else f"unit-{digest}"


def _merge_scanned_unit(
    wire_units: dict[str, dict[str, Any]],
    unit: WireUnit,
    *,
    unit_id: str,
    page: PageMeta,
    page_number: int,
    unit_index: int,
) -> list[str]:
    context = _unit_cable_context(unit)
    existing = wire_units.setdefault(
        unit_id,
        {
            "unit_id": unit_id,
            "wire_number": unit.wire_number,
            "project_no": page.get("project_no"),
            "drawing_prefix": page.get("drawing_prefix") or page.get("function"),
            "attribute": unit.attribute,
            "model": unit.model,
            "spec": unit.spec,
            "length": unit.length,
            "cable_context": context,
            "unit_identity_confidence": "high" if unit.wire_number else "low",
            "connections": [],
            "source_pages": [],
            "source_drawing_pages": [],
            "status": unit.status,
            "confidence": unit.confidence,
            "_identity_project": page.get("project_no") or "unknown-project",
            "_identity_prefix": page.get("drawing_prefix") or page.get("function") or "unknown-prefix",
        },
    )
    for field in (
        "wire_number",
        "project_no",
        "drawing_prefix",
        "attribute",
        "model",
        "spec",
        "length",
        "confidence",
    ):
        if existing.get(field) in (None, "") and getattr(unit, field) not in (None, ""):
            existing[field] = getattr(unit, field)
    if existing.get("current") in (None, "") and unit.current not in (None, ""):
        existing["current"] = unit.current
    existing["source_pages"] = sorted(
        {int(value) for value in existing.get("source_pages", [])} | {page_number}
    )
    label = _drawing_page_label(page)
    if label:
        existing["source_drawing_pages"] = _unique_strings([*existing.get("source_drawing_pages", []), label])
    connection_ids: list[str] = []
    for connection_index, raw_connection in enumerate(unit.connections, start=1):
        connection = (
            raw_connection
            if isinstance(raw_connection, WireConnection)
            else WireConnection.model_validate(raw_connection)
        )
        connection_id = f"{unit_id}:p{page_number}:c{connection_index}"
        connection_dict = connection.model_dump(mode="json", exclude_none=False)
        connection_dict["connection_id"] = connection_id
        connection_dict["unit_id"] = unit_id
        connection_dict["origin_pdf_page"] = page_number
        connection_dict["source_pdf_pages"] = sorted(
            {page_number, *[int(value) for value in connection.source_pdf_pages]}
        )
        connection_dict["source_drawing_pages"] = _unique_strings(
            [
                *connection.source_drawing_pages,
                label,
            ]
        )
        existing["connections"].append(connection_dict)
        connection_ids.append(connection_id)
        if connection.status not in {"complete", "resolved"}:
            existing["status"] = "needs_review"
    return connection_ids


def _find_connection(unit: Mapping[str, Any], connection_id: str) -> dict[str, Any] | None:
    for connection in unit.get("connections", []):
        if str(connection.get("connection_id")) == connection_id:
            return cast(dict[str, Any], connection)
    return None


def _wire_record_from_connection(
    unit: WireUnit,
    connection: WireConnection,
    *,
    page_by_number: Mapping[int, PageMeta],
    terminal_strip_mapping: Mapping[str, str],
) -> WireRecord:
    start = connection.start or Endpoint()
    end = connection.end or Endpoint()
    source_pages = sorted({int(value) for value in (*unit.source_pages, *connection.source_pdf_pages)})
    source_drawing_pages = _unique_strings([*unit.source_drawing_pages, *connection.source_drawing_pages])
    source_images = [
        Path(page_by_number[page]["image_path"]).name for page in source_pages if page in page_by_number
    ]
    primary_page_number = connection.origin_pdf_page or (source_pages[0] if source_pages else None)
    primary_page = page_by_number.get(primary_page_number) if primary_page_number else None
    status = connection.status or unit.status
    external = bool(
        connection.external_source_required or status in {"external", "needs_review"} and end.terminal is None
    )
    source_type = "external" if external else "pdf"
    source_note = connection.source_note
    page_note = f"PDF第{','.join(str(page) for page in source_pages)}页"
    if source_drawing_pages:
        page_note += f"；图纸页{','.join(source_drawing_pages)}"
    source_note = f"{source_note}；{page_note}" if source_note else page_note
    return WireRecord(
        wire_number=unit.wire_number,
        attribute=unit.attribute,
        model=unit.model,
        spec=unit.spec,
        length=unit.length,
        current=connection.current,
        current_basis=connection.current_basis,
        current_source_text=connection.current_source_text,
        line_number=connection.line_number,
        core_number=connection.core_number,
        color=connection.color,
        start_part=start.part,
        start_location=start.location,
        start_device=start.device,
        start_name=start.name,
        start_terminal_board=start.terminal_board,
        start_terminal_code=start.terminal_code,
        start_terminal=start.terminal,
        end_part=end.part,
        end_location=end.location,
        end_device=end.device,
        end_name=end.name,
        end_terminal_board=end.terminal_board,
        end_terminal_code=end.terminal_code,
        end_terminal=end.terminal,
        terminal_strip=start.terminal_strip,
        start_terminal_strip=start.terminal_strip,
        end_terminal_strip=end.terminal_strip,
        remark=connection.remark,
        confidence=connection.confidence or unit.confidence,
        source_note=source_note,
        source_image=", ".join(source_images) or None,
        source_pages=source_pages,
        source_type=source_type,
        external_source_required=external,
        unit_id=unit.unit_id,
        connection_id=connection.connection_id,
        intermediate_points=[
            point.model_dump(mode="json", exclude_none=False) for point in connection.intermediate_points
        ],
        references=[
            reference.model_dump(mode="json", exclude_none=False) for reference in connection.references
        ],
        is_cross_page=connection.is_cross_page,
        drawing_function=primary_page.get("function") if primary_page else None,
        drawing_page_number=primary_page.get("internal_page") if primary_page else None,
        pdf_page_number=primary_page_number,
        drawing_source_pages=source_drawing_pages,
        drawing_page=_drawing_page_label(primary_page) if primary_page else None,
        status=status,
        unit_identity_confidence=unit.unit_identity_confidence,
    )


def _connection_identity(unit_id: str, connection: WireConnection) -> str:
    start = _endpoint_signature(connection.start)
    end = _endpoint_signature(connection.end)
    points = tuple(_endpoint_signature(point) for point in connection.intermediate_points)
    if connection.line_number or connection.core_number or start != "" or end != "":
        return json.dumps(
            [unit_id, connection.core_number, connection.line_number, start, end, points],
            ensure_ascii=False,
            sort_keys=True,
        )
    return f"{unit_id}:{connection.connection_id or connection.local_connection_id or id(connection)}"


def _merge_connection_data(target: WireConnection, source: WireConnection) -> None:
    for field in (
        "core_number",
        "color",
        "line_number",
        "current",
        "current_basis",
        "current_source_text",
        "confidence",
        "remark",
        "source_note",
        "is_cross_page",
    ):
        if getattr(target, field) in (None, "") and getattr(source, field) not in (None, ""):
            setattr(target, field, getattr(source, field))
    if target.start is None:
        target.start = source.start
    elif source.start:
        target.start = _merge_endpoint(target.start, source.start)
    if target.end is None:
        target.end = source.end
    elif source.end:
        target.end = _merge_endpoint(target.end, source.end)
    target.source_pdf_pages = sorted({*target.source_pdf_pages, *source.source_pdf_pages})
    target.source_drawing_pages = _unique_strings(
        [*target.source_drawing_pages, *source.source_drawing_pages]
    )
    target.references.extend(
        reference
        for reference in source.references
        if reference.raw not in {item.raw for item in target.references}
    )
    target.external_source_required = target.external_source_required or source.external_source_required
    if target.status in {"complete", "resolved"} and source.status not in {"complete", "resolved"}:
        target.status = source.status


def _merge_endpoint(left: Endpoint, right: Endpoint) -> Endpoint:
    values = left.model_dump(mode="python", exclude_none=False)
    for key, value in right.model_dump(mode="python", exclude_none=False).items():
        if values.get(key) in (None, "") and value not in (None, ""):
            values[key] = value
    return Endpoint.model_validate(values)


def _endpoint_signature(endpoint: Endpoint | None) -> str:
    if endpoint is None:
        return ""
    return json.dumps(
        endpoint.model_dump(mode="json", exclude_none=False), ensure_ascii=False, sort_keys=True
    )


def _unit_cable_context(unit: WireUnit) -> str:
    return "|".join(
        str(value).strip()
        for value in (unit.attribute, unit.model, unit.spec, unit.length)
        if value not in (None, "")
    )


def _contexts_compatible(left: str, right: str) -> bool:
    if not left or not right:
        return True
    return left == right


def _drawing_page_label(page: Mapping[str, Any] | None) -> str | None:
    if not page:
        return None
    function = page.get("function")
    internal_page = page.get("internal_page")
    if function and internal_page is not None:
        return f"{function}/{internal_page}"
    if function:
        return str(function)
    return None


def _unique_strings(values: Iterable[Any]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value not in (None, "")))


def _text_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _append_remark(current: str | None, message: str) -> str:
    return f"{current}; {message}" if current else message


def _attach_drawing_page(record: WireRecord, drawing_index: Mapping[str, Any]) -> None:
    if record.drawing_page or not record.source_pages:
        return
    pages = {int(page.get("pdf_page")): page for page in drawing_index.get("pages", [])}
    for pdf_page in sorted(record.source_pages):
        page = pages.get(int(pdf_page))
        if page and page.get("function") and page.get("internal_page") is not None:
            function = str(page["function"]).replace(".", "")
            record.drawing_page = f"{function}{int(page['internal_page']):02d}"
            return


def _warning(runtime: GraphRuntime, message: str) -> None:
    assert runtime.validation_warnings is not None
    runtime.validation_warnings.append(message)
    logger.warning("assemble_xlsx validation: %s", message)
