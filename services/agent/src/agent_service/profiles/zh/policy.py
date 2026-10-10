from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ...domain.models.drawing_index import DrawingIndex
from ...domain.models.wiring import WireConnection, WireRecord
from .drawing_index import build_drawing_index, parse_references
from .export_fields import ZhExportFields
from .normalization import normalize_wire_record
from .validation import (
    _collect_consistency_warnings,
    _orient_allowed_start_terminal,
    _validated_breaker_current,
)


class ZhExtractionPolicy:
    """ZH rules retained unchanged while the document Graph is migrated."""

    export_fields = ZhExportFields()

    def project_identity(self, text: str) -> tuple[str | None, str | None]:
        compact = " ".join(text.split())
        project = re.search(r"Project\.?\s*NR\s*[:.]?\s*([A-Z0-9_-]+)", compact, flags=re.IGNORECASE)
        prefix = re.search(r"\b(DQ[A-Z0-9_-]+)\b", compact, flags=re.IGNORECASE)
        return project.group(1) if project else None, prefix.group(1).upper() if prefix else None

    def build_drawing_index(self, path: Path) -> DrawingIndex:
        return build_drawing_index(path)

    def parse_references(self, page: Any) -> list[Any]:
        return parse_references(page)

    def prepare_reference(
        self, raw: Mapping[str, Any], *, source_page: Mapping[str, Any], drawing_index: Mapping[str, Any]
    ) -> dict[str, Any]:
        from .references import prepare_reference

        return prepare_reference(raw, source_page=source_page, drawing_index=drawing_index)

    def normalize_record(self, record: WireRecord, mapping: Mapping[str, str]) -> WireRecord:
        record = normalize_wire_record(record, mapping)
        # Diagnostic table semantics retained; DB unit mapping is independent.
        record.terminal_strip = None
        return record

    def orient_connection(self, connection: WireConnection) -> tuple[WireConnection | None, bool]:
        return _orient_allowed_start_terminal(connection)

    def validated_current(self, value: Any, basis: str | None, source_text: str | None) -> str | None:
        return _validated_breaker_current(value, basis, source_text)

    def validate_record(self, record: WireRecord, mapping: Mapping[str, str]) -> list[str]:
        return _collect_consistency_warnings(record, mapping)
