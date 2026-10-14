from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.agent.extraction_agent.domain.models.drawing_index import DrawingIndex
from src.agent.extraction_agent.domain.models.wiring import WireConnection, WireRecord
from src.agent.extraction_agent.profiles.zh.drawing_index import build_drawing_index, parse_references
from src.agent.extraction_agent.profiles.zh.export_fields import ZhExportFields
from src.agent.extraction_agent.profiles.zh.normalization import (
    complete_terminal_identifier,
    normalize_wire_record,
)
from src.agent.extraction_agent.profiles.zh.validation import (
    _collect_consistency_warnings,
    _validated_breaker_current,
    endpoint_identity_warnings,
)


class ZhExtractionPolicy:
    """ZH evidence-driven page extraction policy."""

    export_fields = ZhExportFields()
    enforce_evidence_contract = True

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
        from src.agent.extraction_agent.profiles.zh.references import prepare_reference

        return prepare_reference(raw, source_page=source_page, drawing_index=drawing_index)

    def normalize_record(self, record: WireRecord, mapping: Mapping[str, str]) -> WireRecord:
        record = normalize_wire_record(record, mapping)
        return record

    def orient_connection(self, connection: WireConnection) -> tuple[WireConnection | None, bool]:
        # Direction is established by page evidence, never a terminal prefix.
        if connection.endpoint_role == "receiver":
            return None, False
        if not self.enforce_evidence_contract:
            if connection.endpoint_role == "unknown" or connection.start is None:
                connection.status = "needs_review"
            return connection, False
        if not (connection.direction_basis or "").strip():
            connection.endpoint_role = "unknown"
        issues: list[str] = []
        for side in ("start", "end"):
            endpoint = getattr(connection, side)
            if endpoint is not None:
                endpoint.terminal = complete_terminal_identifier(
                    endpoint.terminal, endpoint.terminal_board, endpoint.device
                )
                endpoint.terminal_strip = None
                endpoint_issues = endpoint_identity_warnings(
                    endpoint.terminal, endpoint.device, endpoint.terminal_board
                )
                issues.extend(f"{side}: {warning}" for warning in endpoint_issues)
                if any("not a physical terminal" in warning for warning in endpoint_issues):
                    issues.append(f"{side}: rejected terminal label {endpoint.terminal}")
                    endpoint.terminal = None
        if connection.endpoint_role == "unknown":
            issues.append("direction unconfirmed")
        if connection.start is None:
            issues.append("missing source endpoint")
        if issues:
            connection.status = "needs_review"
            connection.source_note = "; ".join(
                dict.fromkeys(filter(None, [connection.source_note, *issues]))
            )
        return connection, False

    def validated_current(self, value: Any, basis: str | None, source_text: str | None) -> str | None:
        return _validated_breaker_current(value, basis, source_text)

    def validate_record(self, record: WireRecord, mapping: Mapping[str, str]) -> list[str]:
        warnings = _collect_consistency_warnings(
            record, mapping, require_endpoint_identity=self.enforce_evidence_contract
        )
        if warnings and self.enforce_evidence_contract:
            record.status = "needs_review"
        return warnings
