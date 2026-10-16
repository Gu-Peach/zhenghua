from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from src.agent.extraction_agent.domain.models.wiring import (
    WireRecord,
)


def endpoint_identity_warnings(terminal: Any, device: Any, board: Any) -> list[str]:
    """Check endpoint identity without restricting terminal families."""
    warnings: list[str] = []
    value = str(terminal if terminal is not None else "").strip()
    if not value:
        warnings.append("missing physical terminal")
    elif re.fullmatch(r"[IQ]\d+\.\d+", value, re.IGNORECASE):
        warnings.append("PLC address is not a physical terminal")
    elif re.search(r"(?:^|:)\w+_(?:L\d?|N|PE|\+|-)(?:\.\d+)?$", value, re.IGNORECASE):
        warnings.append("potential label is not a physical terminal")
    if (
        not str(device or board or "").strip()
        and ":" not in value
        and value.upper() not in {"N-BAR", "PE-BAR"}
    ):
        warnings.append("missing device or terminal board identity")
    return warnings


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
    *,
    require_endpoint_identity: bool = False,
) -> list[str]:
    warnings: list[str] = []
    if require_endpoint_identity:
        for side in ("start", "end"):
            warnings.extend(
                f"{side}: {warning}"
                for warning in endpoint_identity_warnings(
                    getattr(record, f"{side}_terminal"),
                    getattr(record, f"{side}_device"),
                    getattr(record, f"{side}_terminal_board"),
                )
            )
    line_number = (record.line_number or "").strip().upper()
    if line_number == "SPARE":
        if record.start_terminal not in (None, "*") or record.end_terminal not in (None, "*"):
            warnings.append("SPARE record has a non-* terminal")
        return warnings
    if line_number == "PE":
        allowed = {"PE", "PE-BAR"} if require_endpoint_identity else {"PE"}
        if any(
            value and str(value).rsplit(":", 1)[-1].upper() not in allowed
            for value in (record.start_terminal, record.end_terminal)
        ):
            warnings.append("PE record has a non-PE terminal")
        return warnings
    if record.start_device and record.start_terminal is None:
        warnings.append(f"{record.source_image or 'record'} has a start device but no start terminal")
    return warnings
