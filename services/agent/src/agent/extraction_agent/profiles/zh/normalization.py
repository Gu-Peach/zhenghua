from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from src.agent.extraction_agent.domain.models.wiring import (
    PageScanResult,
    WireRecord,
)
from src.agent.extraction_agent.infrastructure.document.json_response import _loads_json
from src.agent.extraction_agent.profiles.zh.terminal_strips import BUSINESS_TERMINAL_STRIP_MAPPING


def parse_page_scan_result(content: str, *, default_pdf_page: int | None = None) -> PageScanResult:
    parsed = _loads_json(content)
    if isinstance(parsed, list):
        parsed = {"units": [{"unit_id": "page-unit-1", "connections": parsed}]}
    if not isinstance(parsed, dict):
        raise ValueError("Page scan response must be a JSON object or array.")
    parsed = dict(parsed)
    if not isinstance(parsed.get("units"), list):
        records = parsed.get("records") or parsed.get("connections") or parsed.get("items")
        parsed["units"] = (
            [{"unit_id": "page-unit-1", "connections": records}] if isinstance(records, list) else []
        )
    units: list[dict[str, Any]] = []
    for unit_index, raw_unit in enumerate(parsed["units"], start=1):
        if not isinstance(raw_unit, dict):
            continue
        unit = dict(raw_unit)
        unit.setdefault("unit_id", f"page-unit-{unit_index}")
        connections = unit.get("connections") or unit.get("records") or []
        unit["connections"] = (
            [
                _normalize_connection(connection, index)
                for index, connection in enumerate(connections, start=1)
                if isinstance(connection, dict)
            ]
            if isinstance(connections, list)
            else []
        )
        units.append(unit)
    parsed["units"] = units
    parsed.setdefault("pdf_page_number", default_pdf_page)
    parsed["page_references"] = [
        {"raw": item} if isinstance(item, str) else item
        for item in parsed.get("page_references", parsed.get("references", []))
        if isinstance(item, (dict, str))
    ]
    return PageScanResult.model_validate(parsed)


def normalize_wire_record(
    record: WireRecord,
    terminal_strip_mapping: Mapping[str, str] | None = None,
    *,
    require_pin: bool = False,
) -> WireRecord:
    line_number = _text(record.line_number)
    if line_number and line_number.upper() == "SPARE":
        record.terminal_strip = record.start_terminal_strip = record.end_terminal_strip = None
        record.start_terminal = record.end_terminal = "*"
        record.remark = record.remark or "SPARE"
        return record
    if line_number and line_number.upper() == "PE":
        record.start_terminal = record.start_terminal or "PE"
        # An unresolved PE endpoint must stay null.
    for side in ("start", "end"):
        setattr(
            record, f"{side}_terminal",
            complete_terminal_identifier(
                getattr(record, f"{side}_terminal"),
                getattr(record, f"{side}_terminal_board"),
                getattr(record, f"{side}_device"),
                require_pin=require_pin,
            ),
        )
        if require_pin and getattr(record, f"{side}_terminal") is None:
            setattr(record, f"{side}_terminal_coordinates", None)
    # Business classification is deterministic; never trust model-provided strips.
    start_strip = _mapped_endpoint_strip(record, "start", terminal_strip_mapping)
    end_strip = _mapped_endpoint_strip(record, "end", terminal_strip_mapping)
    record.start_terminal_strip = start_strip
    record.end_terminal_strip = end_strip
    record.terminal_strip = start_strip or end_strip
    return record


def _mapped_endpoint_strip(record: WireRecord, side: str, mapping: Mapping[str, str] | None) -> str | None:
    terminal = str(getattr(record, f"{side}_terminal") or "")
    if ":" in terminal:
        return _terminal_strip(terminal.split(":", 1)[0], mapping)
    for value in (
        terminal,
        getattr(record, f"{side}_terminal_board"),
        getattr(record, f"{side}_device"),
    ):
        result = _terminal_strip(value, mapping)
        if result:
            return result
    return None


def _normalize_connection(value: dict[str, Any], index: int) -> dict[str, Any]:
    connection = dict(value)
    for side in ("start", "end"):
        if not isinstance(connection.get(side), dict):
            prefix = f"{side}_"
            fields = (
                "part",
                "location",
                "device",
                "name",
                "terminal_board",
                "terminal_code",
                "terminal_strip",
                "terminal",
                "terminal_coordinates",
            )
            endpoint = {
                field: connection.pop(prefix + field) for field in fields if prefix + field in connection
            }
            if endpoint:
                connection[side] = endpoint
    connection.setdefault("local_connection_id", f"connection-{index}")
    refs = connection.get("references") or []
    connection["references"] = [
        {"raw": item} if isinstance(item, str) else item for item in refs if isinstance(item, (str, dict))
    ]
    return connection


def complete_terminal_identifier(
    terminal: Any, board: Any = None, device: Any = None, *, require_pin: bool = False,
) -> Any:
    """Combine an observed X-family board with a pin, preserving complete labels."""
    value = _text(terminal)
    if not value or value in {"*", "PE"}:
        return terminal
    value = value.replace("：", ":")
    if require_pin:
        if value.upper() in {"N-BAR", "PE-BAR"}:
            return value.upper()
        if re.fullmatch(r"-?X(?:D\d+|\d+|[A-Z])", value, re.IGNORECASE):
            return None
    if ":" in value:
        prefix, pin = value.split(":", 1)
        prefix = prefix.strip().lstrip("-").upper()
        if require_pin and (not pin.strip() or prefix == pin.strip().lstrip("-").upper()):
            return None
        return f"{prefix}:{pin.strip()}"
    for candidate in (board, device):
        code = (_text(candidate) or "").lstrip("-").upper()
        if re.fullmatch(r"X(?:D\d+|\d+|[A-Z])", code):
            return f"{code}:{value}"
    return value


def _terminal_strip(device: Any, mapping: Mapping[str, str] | None) -> str | None:
    text = _text(device)
    if not text:
        return None
    code = text.lstrip("-").upper()
    if code != "XA" and code != "XH" and not code.startswith("XD"):
        return None
    return BUSINESS_TERMINAL_STRIP_MAPPING.get(code)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_wire_record(record: WireRecord, mapping: Mapping[str, str] | None = None) -> WireRecord:
    return normalize_wire_record(record, mapping)
