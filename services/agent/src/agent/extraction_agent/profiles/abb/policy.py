from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.agent.extraction_agent.domain.models.drawing_index import DrawingIndex, DrawingPage, DrawingReference
from src.agent.extraction_agent.domain.models.wiring import WireConnection, WireRecord
from src.agent.extraction_agent.profiles.export_fields import PREPARED_EXPORT_FIELDS

FUNCTION_RE = re.compile(r"(?:Plant\s+Function|Function)\s*:?[ \t]*(=?[A-Z]{2}\d{2})", re.I)
SHEET_RE = re.compile(r"\bSheet\s*:?[ \t]*(\d{1,4})\b", re.I)
OBJECT_RE = re.compile(r"(?:Object\s+Loc\.?|Location)\s*:?[ \t]*(\+[A-Z0-9_.-]+)", re.I)
REFERENCE_RE = re.compile(r"/(?P<sheet>\d{1,4})[.](?P<column>\d{1,2})(?P<row>[A-Z])\b", re.I)


class AbbExtractionPolicy:
    """ABB deterministic boundaries; intentionally independent from ZH rules."""

    export_fields = PREPARED_EXPORT_FIELDS

    def project_identity(self, text: str) -> tuple[str | None, str | None]:
        drawing = re.search(r"\b\d[A-Z]{3}\d{6}-[A-Z]{3}\b", text, flags=re.I)
        return (drawing.group(0).upper() if drawing else None, None)

    def build_drawing_index(self, path: Path) -> DrawingIndex:
        from src.agent.extraction_agent.infrastructure.document.pdf_runtime import read_pdf_text_pages

        index = DrawingIndex(pdf_path=str(path))
        for pdf_page, text in read_pdf_text_pages(path):
            function_match = FUNCTION_RE.search(text)
            sheet_match = SHEET_RE.search(text)
            object_match = OBJECT_RE.search(text)
            function = _function(function_match.group(1)) if function_match else None
            sheet = int(sheet_match.group(1)) if sheet_match else None
            page = DrawingPage(
                pdf_page=pdf_page,
                function=function,
                internal_page=sheet,
                object_loc=object_match.group(1) if object_match else None,
                text=text,
            )
            index.pages.append(page)
            if function and sheet is not None:
                index.page_lookup[f"{function}:{sheet}"] = pdf_page
            index.references.extend(self.parse_references(page))
        return index

    def parse_references(self, page: Any) -> list[Any]:
        references: list[DrawingReference] = []
        for match in REFERENCE_RE.finditer(str(page.text or "")):
            references.append(
                DrawingReference(
                    source_pdf_page=int(page.pdf_page),
                    target_function=None,
                    target_internal_page=int(match.group("sheet")),
                    target_column=int(match.group("column")),
                    target_object=None,
                    raw=match.group(0),
                )
            )
        return references

    def prepare_reference(
        self,
        raw: Mapping[str, Any],
        *,
        source_page: Mapping[str, Any],
        drawing_index: Mapping[str, Any],
    ) -> dict[str, Any]:
        reference = dict(raw)
        parsed = REFERENCE_RE.search(str(reference.get("raw") or ""))
        if parsed:
            for field, value in (
                ("target_drawing_page", int(parsed.group("sheet"))),
                ("target_internal_page", int(parsed.group("sheet"))),
                ("target_column", int(parsed.group("column"))),
            ):
                if reference.get(field) in (None, ""):
                    reference[field] = value
        target_sheet = reference.get("target_drawing_page") or reference.get("target_internal_page")
        target_pdf = reference.get("target_pdf_page")
        target_function = reference.get("target_function")
        if target_pdf is None and target_sheet is not None:
            candidates = [
                page
                for page in drawing_index.get("pages", [])
                if page.get("internal_page") is not None
                and int(page["internal_page"]) == int(target_sheet)
                and (not target_function or _function(page.get("function")) == _function(target_function))
            ]
            if len(candidates) == 1:
                target_pdf = int(candidates[0]["pdf_page"])
                reference["target_function"] = candidates[0].get("function")
        reference["target_pdf_page"] = int(target_pdf) if target_pdf is not None else None
        if target_pdf is None:
            reference["external"] = True
            if not reference.get("reason"):
                reference["reason"] = "ABB target Sheet is absent or ambiguous in the page index"
        return reference

    def normalize_record(self, record: WireRecord, mapping: Mapping[str, str]) -> WireRecord:
        del mapping
        for field in (
            "start_location",
            "start_device",
            "start_terminal_strip",
            "end_location",
            "end_device",
            "end_terminal_strip",
            "line_number",
        ):
            value = getattr(record, field)
            if isinstance(value, str):
                setattr(record, field, value.strip() or None)
        record.terminal_strip = record.start_terminal_strip or record.terminal_strip
        return record

    def orient_connection(self, connection: WireConnection) -> tuple[WireConnection | None, bool]:
        if connection.endpoint_role == "receiver":
            return None, False
        if connection.start is None or connection.start.terminal in (None, ""):
            connection.status = "needs_review"
        return connection, False

    def validated_current(
        self, value: Any, basis: str | None, source_text: str | None
    ) -> str | None:
        if value in (None, "") or not source_text:
            return None
        if re.search(r"\d\s*[-–]\s*\d|\b[0-9.]+\s*[kK]?[vV]\b", source_text):
            return None
        return str(value).strip() or None

    def validate_record(self, record: WireRecord, mapping: Mapping[str, str]) -> list[str]:
        del mapping
        warnings: list[str] = []
        if not record.line_number:
            warnings.append(f"ABB connection {record.connection_id or '?'} has no principle number")
        if not record.start_terminal:
            warnings.append(f"ABB connection {record.connection_id or '?'} has no start terminal")
        if record.is_cross_page.value == "cross_page" and not record.end_terminal:
            warnings.append(f"ABB connection {record.connection_id or '?'} still needs cross-page review")
        return warnings


def _function(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text.removeprefix("=") or None
