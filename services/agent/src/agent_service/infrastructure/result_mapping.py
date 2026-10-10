from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..domain.enums import ErrorCode
from ..domain.errors import AgentServiceError
from ..domain.models.proposals import ResultProposal


def proposal_to_normalized_units(
    proposal: ResultProposal,
    *,
    drawings: Sequence[Mapping[str, Any]],
    workspaces: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Map full-extraction add operations to the normalized result RPC payload."""

    drawing_by_pdf = {int(row["pdf_page_number"]): row for row in drawings}
    workspace_by_id = {str(row["id"]): row for row in workspaces}
    workspace_by_code = {
        _normalized_code(row.get("code")): row for row in workspaces if row.get("code")
    }
    grouped: dict[tuple[str, str], dict[str, Any]] = {}

    for index, operation in enumerate(proposal.operations, start=1):
        if operation.op != "add" or operation.after is None:
            raise AgentServiceError(
                ErrorCode.INVALID_REQUEST,
                "Full extraction persistence accepts add operations only.",
                retryable=False,
            )
        record = dict(operation.after)
        source_pages = _source_pages(record)
        primary = next((drawing_by_pdf[page] for page in source_pages if page in drawing_by_pdf), None)
        if primary is None and len(drawings) == 1:
            primary = drawings[0]
        if primary is None:
            function = _normalized_code(record.get("drawing_function"))
            workspace = workspace_by_code.get(function)
            candidates = [
                row for row in drawings if workspace and str(row["workspace_id"]) == str(workspace["id"])
            ]
            primary = candidates[0] if len(candidates) == 1 else None
        if primary is None:
            raise AgentServiceError(
                ErrorCode.PROJECT_CONTEXT_NOT_FOUND,
                "An extracted connection could not be mapped to a persisted drawing.",
                retryable=False,
                details={"target_id": operation.target_id, "source_pages": source_pages},
            )

        workspace_id = str(primary["workspace_id"])
        if workspace_id not in workspace_by_id:
            raise AgentServiceError(
                ErrorCode.PROJECT_CONTEXT_NOT_FOUND,
                "The extracted drawing workspace is missing.",
                retryable=False,
            )
        terminal_strip = _text(record.get("terminal_strip") or record.get("start_terminal_strip"))
        logical_key = (
            terminal_strip
            or _text(record.get("unit_id"))
            or _text(record.get("wire_number"))
            or f"connection-{index}"
        )
        group_key = (workspace_id, logical_key)
        unit = grouped.setdefault(
            group_key,
            {
                "workspace_id": workspace_id,
                "drawing_id": str(primary["id"]),
                "voltage_level": _text(
                    record.get("voltage_level")
                    or record.get("attribute")
                    or record.get("model")
                ),
                "terminal_strip": terminal_strip,
                "status": "needs_review" if _needs_review(record) else "extracted",
                "needs_review": _needs_review(record),
                "raw_payload": {
                    "logical_key": logical_key,
                    "source_unit_id": record.get("unit_id"),
                    "source_wire_number": record.get("wire_number"),
                },
                "connections": [],
            },
        )
        unit["needs_review"] = bool(unit["needs_review"] or _needs_review(record))
        if unit["needs_review"]:
            unit["status"] = "needs_review"
        evidence = _evidence_rows(record, primary, drawing_by_pdf)
        raw_payload = dict(record)
        raw_payload["connection_id"] = operation.target_id
        unit["connections"].append(
            _connection_payload(
                record,
                source_drawing_id=str(primary["id"]),
                core_order=len(unit["connections"]) + 1,
                record_version=1,
                raw_payload=raw_payload,
                evidence=evidence,
            )
        )
    return list(grouped.values())


def normalized_connection_from_record(
    record: Mapping[str, Any],
    *,
    current: Mapping[str, Any],
    record_version: int,
) -> dict[str, Any]:
    """Overlay a correction result on a normalized connection payload."""

    value = dict(current)
    value.update(
        _connection_payload(
            record,
            source_drawing_id=str(current.get("source_drawing_id") or ""),
            core_order=int(current["core_order"]),
            record_version=record_version,
            raw_payload=dict(record),
            evidence=list(current.get("evidence") or []),
        )
    )
    return value


def _connection_payload(
    record: Mapping[str, Any],
    *,
    source_drawing_id: str,
    core_order: int,
    record_version: int,
    raw_payload: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    raw_start = record.get("start")
    raw_end = record.get("end")
    start: Mapping[str, Any] = raw_start if isinstance(raw_start, Mapping) else {}
    end: Mapping[str, Any] = raw_end if isinstance(raw_end, Mapping) else {}
    needs_review = _needs_review(record)
    return {
        "source_drawing_id": source_drawing_id,
        "core_order": core_order,
        "principle_number": _text(record.get("principle_number") or record.get("line_number")),
        "start_code": _text(
            record.get("start_code")
            or record.get("start_location")
            or record.get("start_device")
            or start.get("location")
            or start.get("device")
        ),
        "start_description": _text(
            record.get("start_description")
            or record.get("start_name")
            or record.get("start_part")
            or start.get("name")
            or start.get("part")
        ),
        "start_terminal": _text(record.get("start_terminal") or start.get("terminal")),
        "end_code": _text(
            record.get("end_code")
            or record.get("end_location")
            or record.get("end_device")
            or end.get("location")
            or end.get("device")
        ),
        "end_description": _text(
            record.get("end_description")
            or record.get("end_name")
            or record.get("end_part")
            or end.get("name")
            or end.get("part")
        ),
        "end_terminal": _text(record.get("end_terminal") or end.get("terminal")),
        "current_value": _text(record.get("current_value") or record.get("current")),
        "remark": _text(record.get("remark")),
        "color_mark": _text(record.get("color_mark") or record.get("color")),
        "is_cross_page": str(record.get("is_cross_page") or "unknown"),
        "confidence": _confidence(record.get("confidence")),
        "status": "needs_review" if needs_review else "extracted",
        "needs_review": needs_review,
        "raw_payload": raw_payload,
        "record_version": record_version,
        "evidence": evidence,
    }


def _evidence_rows(
    record: Mapping[str, Any],
    primary: Mapping[str, Any],
    drawing_by_pdf: Mapping[int, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    pages = _source_pages(record)
    rows: list[dict[str, Any]] = []
    for index, page in enumerate(pages):
        drawing = drawing_by_pdf.get(page)
        if drawing is None:
            continue
        kind = "source"
        if index > 0 and str(record.get("is_cross_page")) == "cross_page":
            kind = "target"
        rows.append(
            {
                "drawing_id": str(drawing["id"]),
                "kind": kind,
                "raw_text": _text(record.get("source_note")),
            }
        )
    if not rows:
        rows.append(
            {
                "drawing_id": str(primary["id"]),
                "kind": "source",
                "raw_text": _text(record.get("source_note")),
            }
        )
    return rows


def _source_pages(record: Mapping[str, Any]) -> list[int]:
    raw = record.get("source_pages") or record.get("source_pdf_pages") or []
    if not isinstance(raw, list):
        raw = [raw]
    for fallback in (record.get("pdf_page_number"), record.get("origin_pdf_page")):
        if not raw and fallback not in (None, ""):
            raw = [fallback]
    pages: list[int] = []
    for item in raw:
        try:
            page = int(item)
        except (TypeError, ValueError):
            continue
        if page > 0 and page not in pages:
            pages.append(page)
    return pages


def _text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _normalized_code(value: Any) -> str:
    return str(value or "").strip().lstrip("=").casefold()


def _confidence(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def _needs_review(record: Mapping[str, Any]) -> bool:
    return str(record.get("status") or "").casefold() == "needs_review" or bool(
        record.get("needs_review") or record.get("external_source_required")
    )
