from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from agent_service.domain.models.wiring import (
    PageScanResult,
    WireRecord,
)
from agent_service.infrastructure.document.json_response import _loads_json
from agent_service.profiles.zh.terminal_strips import (
    ALLOWED_TERMINAL_CODES,
    normalize_terminal_strip,
)
from agent_service.profiles.zh.terminal_strips import (
    terminal_strip_for_device as configured_terminal_strip_for_device,
)


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
) -> WireRecord:
    line_number = _text(record.line_number)
    if line_number and line_number.upper() == "SPARE":
        record.terminal_strip = record.start_terminal_strip = record.end_terminal_strip = None
        record.start_terminal = record.end_terminal = "*"
        record.remark = record.remark or "SPARE"
        return record
    if line_number and line_number.upper() == "PE":
        record.terminal_strip = record.start_terminal_strip = record.end_terminal_strip = None
        record.start_terminal = record.end_terminal = "PE"
        record.color = record.color or "黄绿"
        record.remark = record.remark or "PE"
        return record
    record.start_terminal = _normalize_terminal(record.start_device, record.start_terminal, force_prefix=True)
    record.end_terminal = _normalize_terminal(record.end_device, record.end_terminal, force_prefix=False)
    record.start_terminal_code = _normalize_terminal_code(record.start_terminal_code)
    record.end_terminal_code = _normalize_terminal_code(record.end_terminal_code)
    start_strip = _terminal_strip(record.start_device, terminal_strip_mapping)
    record.terminal_strip = start_strip or normalize_terminal_strip(
        record.terminal_strip, terminal_strip_mapping
    )
    record.start_terminal_strip = start_strip or normalize_terminal_strip(
        record.start_terminal_strip or record.terminal_strip, terminal_strip_mapping
    )
    record.end_terminal_strip = _terminal_strip(
        record.end_device, terminal_strip_mapping
    ) or normalize_terminal_strip(record.end_terminal_strip, terminal_strip_mapping)
    return record




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


def _normalize_terminal(device: Any, terminal: Any, *, force_prefix: bool) -> Any:
    value = _text(terminal)
    if not value or value in {"*", "PE"}:
        return terminal
    device_text = _text(device)
    device_code = device_text.lstrip("-").upper() if device_text else None
    if device_code and (device_code in {"XA", "XH"} or device_code.startswith("XD")):
        suffix = value.rsplit(":", 1)[-1].strip()
        if suffix and not suffix.upper().startswith(("X", "XD")):
            return f"{device_code}:{suffix}"
    normalized = re.sub(r"^-?(XA|XD\d+|XH)\s*[-:]\s*", r"\1:", value, flags=re.IGNORECASE)
    if ":" in normalized and not (force_prefix and device_code and device_code.startswith("XD")):
        return normalized
    if force_prefix and device_code:
        return f"{device_code}:{value.rsplit(':', 1)[-1].strip()}"
    if device_code and (device_code in {"XA", "XH"} or device_code.startswith("XD")):
        return f"{device_code}:{value.rsplit(':', 1)[-1].strip()}"
    return value


def _terminal_strip(device: Any, mapping: Mapping[str, str] | None) -> str | None:
    text = _text(device)
    if not text:
        return None
    code = text.lstrip("-").upper()
    if code != "XA" and code != "XH" and not code.startswith("XD"):
        return None
    if mapping:
        return normalize_terminal_strip(mapping.get(code), mapping)
    return configured_terminal_strip_for_device(device)


def _normalize_terminal_code(value: Any) -> str | None:
    normalized = str(value).strip().upper() if value is not None else ""
    return normalized if normalized in ALLOWED_TERMINAL_CODES else None




def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_wire_record(record: WireRecord, mapping: Mapping[str, str] | None = None) -> WireRecord:
    return normalize_wire_record(record, mapping)
