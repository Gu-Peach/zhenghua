from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from agent_service.domain.models.wiring import (
    Endpoint,
    WireConnection,
    WireRecord,
)
from agent_service.profiles.zh.terminal_strips import (
    ALLOWED_TERMINAL_STRIPS,
    allowed_start_terminal_code,
    normalize_terminal_strip,
    terminal_strip_for_device,
)


def _orient_allowed_start_terminal(
    connection: WireConnection,
) -> tuple[WireConnection | None, bool]:
    start_code = _endpoint_allowed_start_code(connection.start)
    end_code = _endpoint_allowed_start_code(connection.end)
    if start_code:
        return connection, False
    if end_code and connection.end is not None:
        connection.start, connection.end = connection.end, connection.start
        return connection, True
    return None, False


def _endpoint_allowed_start_code(endpoint: Endpoint | None) -> str | None:
    if endpoint is None:
        return None
    return allowed_start_terminal_code(
        endpoint.terminal_board,
        endpoint.device,
        endpoint.terminal,
    )


def _validated_breaker_current(
    value: Any,
    basis: str | None,
    source_text: str | None,
) -> str | None:
    if value in (None, "") or not basis or not source_text:
        return None
    normalized_basis = re.sub(r"[^A-Z]", "", str(basis).upper())
    if normalized_basis not in {"IR", "IN", "IE"}:
        return None
    evidence = str(source_text).strip()
    if not re.search(rf"(?i)\b{normalized_basis}\b\s*[:=]", evidence):
        return None
    current = str(value).strip().replace(" ", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(mA|A|kA)", current, flags=re.IGNORECASE)
    if not match:
        return None
    unit = match.group(2)
    canonical_unit = "mA" if unit.lower() == "ma" else "kA" if unit.lower() == "ka" else "A"
    return f"{match.group(1)}{canonical_unit}"


def _collect_consistency_warnings(
    record: WireRecord,
    mapping: Mapping[str, str],
) -> list[str]:
    warnings: list[str] = []
    line_number = (record.line_number or "").strip().upper()
    if line_number == "SPARE":
        if record.start_terminal not in (None, "*") or record.end_terminal not in (None, "*"):
            warnings.append("SPARE record has a non-* terminal")
        return warnings
    if line_number == "PE":
        if record.start_terminal not in (None, "PE") or record.end_terminal not in (None, "PE"):
            warnings.append("PE record has a non-PE terminal")
        return warnings
    for field_name in ("terminal_strip", "start_terminal_strip", "end_terminal_strip"):
        value = getattr(record, field_name)
        if value not in (None, "") and normalize_terminal_strip(value, mapping) is None:
            warnings.append(
                f"{record.source_image or 'record'} {field_name}={value!r} is outside the allowed "
                f"terminal strips: {', '.join(ALLOWED_TERMINAL_STRIPS)}",
            )

    expected_strip = terminal_strip_for_device(record.start_device, mapping)
    if expected_strip and record.terminal_strip not in (None, expected_strip):
        warnings.append(
            f"{record.source_image or 'record'} start device {record.start_device} "
            f"maps to {expected_strip}, got {record.terminal_strip}",
        )
    if record.start_device and record.start_terminal is None:
        warnings.append(f"{record.source_image or 'record'} has a start device but no start terminal")
    return warnings
