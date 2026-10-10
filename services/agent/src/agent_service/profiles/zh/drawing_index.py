from __future__ import annotations

import json
import re
from pathlib import Path

from agent_service.domain.models.drawing_index import (
    DrawingIndex,
    DrawingPage,
    DrawingReference,
    _lookup_key,
    _normalize_function,
    drawing_page_key,
    normalize_function,
)

__all__ = [
    "DrawingIndex",
    "DrawingPage",
    "DrawingReference",
    "normalize_function",
    "drawing_page_key",
    "build_drawing_index",
    "parse_drawing_page",
    "parse_references",
    "write_drawing_index",
]

FUNCTION_RE = re.compile(r"(?:Plant\s+Function|Function)\s*:?\s*(=?[0-9]{3}(?:\.[A-Z])?)", re.I)
PAGE_RE = re.compile(r"Page\s+Number\s*:?\s*(\d+)", re.I)
OBJECT_RE = re.compile(r"Object\s+Loc\.?\s*:?\s*([^\s]+)", re.I)
TITLE_RE = re.compile(r"Page\s+description\s*:\s*(.+?)(?=Project\.NR|DQ\d|Total\s+Page|$)", re.I)
REFERENCE_RE = re.compile(
    r"(?P<sheet>=?(?:\d{3}\.[A-Z]|\.[A-Z]))?"
    r"(?P<object>\+[A-Za-z0-9][A-Za-z0-9_.-]*)"
    r"/(?P<page>\d{1,3})(?:[.]|\s+)(?P<column>\d{1,2})",
    re.I,
)
STUB_RE = re.compile(r"FOR\s+(?:DETAIL\s+)?(?:PLEASE\s+)?SEE\s+(.+?)(?:DIAGRAM|$)", re.I)


def build_drawing_index(pdf_path: Path) -> DrawingIndex:
    """Build a deterministic EPLAN page/reference index from embedded PDF text."""
    from agent_service.infrastructure.document.pdf_runtime import read_pdf_text_pages

    index = DrawingIndex(pdf_path=str(pdf_path))
    for page_number, text in read_pdf_text_pages(pdf_path):
        drawing_page = parse_drawing_page(page_number, text)
        index.pages.append(drawing_page)
        if drawing_page.function and drawing_page.internal_page is not None:
            index.page_lookup[_lookup_key(drawing_page.function, drawing_page.internal_page)] = page_number

    for page in index.pages:
        index.references.extend(parse_references(page))
    return index


def parse_drawing_page(pdf_page: int, text: str) -> DrawingPage:
    normalized_text = " ".join(text.split())
    function_match = FUNCTION_RE.search(normalized_text)
    page_match = PAGE_RE.search(normalized_text)
    object_match = OBJECT_RE.search(normalized_text)
    title_match = TITLE_RE.search(normalized_text)
    function = _normalize_function(function_match.group(1)) if function_match else None
    header_function, header_page, header_title = _header_identity(text)
    function = function or header_function
    internal_page = int(page_match.group(1)) if page_match else header_page
    parsed_object = object_match.group(1) if object_match else None
    object_loc = _header_object_location(text) or (
        parsed_object if parsed_object and parsed_object.upper() != "ZPMC-EZ" else None
    )
    title = header_title or (title_match.group(1).strip() if title_match else None)
    is_non_wiring = _is_non_wiring_title(title, function)
    return DrawingPage(
        pdf_page=pdf_page,
        function=function,
        internal_page=internal_page,
        object_loc=object_loc,
        title=title,
        text=text,
        is_stub=bool(STUB_RE.search(text)),
        is_non_wiring=is_non_wiring,
    )


def _header_identity(text: str) -> tuple[str | None, int | None, str | None]:
    """Read the EPLAN page identity from the title-block text order."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    # The first function token after the copyright/header block is the page
    # identity; index sheets may contain many later function tokens.
    for index, line in enumerate(lines[:45]):
        match = re.fullmatch(r"=?(\d{3}(?:\.[A-Z])?)", line, flags=re.I)
        if not match:
            continue
        for page_index, candidate in enumerate(lines[index + 1 : index + 8], start=index + 1):
            if re.fullmatch(r"\d{1,3}(?:\.[A-Za-z])?", candidate):
                title = lines[page_index + 1] if page_index + 1 < len(lines) else None
                return _normalize_function(match.group(1)), int(candidate.split(".", 1)[0]), title
    return None, None, None


def _header_object_location(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:16]:
        if re.fullmatch(r"\+[A-Za-z0-9][A-Za-z0-9_.-]*", line):
            return line
    return None


def _is_non_wiring_title(title: str | None, function: str | None) -> bool:
    if function and function.startswith("000"):
        return True
    normalized = (title or "").upper()
    return any(
        token in normalized
        for token in (
            "COVER",
            "INDEX SHEET",
            "TABLE OF CONTENTS",
            "SYMBOL VIEW",
            "STRUCTURE IDENTIFIER",
            "GENERAL DEFINITION",
            "SAMPLE DRAWING",
        )
    )


def parse_references(page: DrawingPage) -> list[DrawingReference]:
    references: list[DrawingReference] = []
    compact_text = " ".join(page.text.split())
    for match in REFERENCE_RE.finditer(compact_text):
        target_function = _resolve_target_function(match.group("sheet"), page.function)
        target_page = int(match.group("page"))
        target_column = int(match.group("column"))
        raw = match.group(0)
        references.append(
            DrawingReference(
                source_pdf_page=page.pdf_page,
                target_function=target_function,
                target_internal_page=target_page,
                target_column=target_column,
                target_object=match.group("object"),
                raw=raw,
                direction="outgoing",
            )
        )
    if page.is_stub:
        references.append(
            DrawingReference(
                source_pdf_page=page.pdf_page,
                target_function=None,
                target_internal_page=None,
                target_column=None,
                target_object=None,
                raw=STUB_RE.search(compact_text).group(0),  # type: ignore[union-attr]
                direction="outgoing",
                external=True,
                reason="stub page points to an external diagram",
            )
        )
    return references


def _resolve_target_function(sheet: str | None, source_function: str | None) -> str | None:
    if not sheet:
        return source_function
    normalized = sheet.strip().upper().lstrip("=")
    if normalized.startswith(".") and source_function:
        source = _normalize_function(source_function)
        return f"{source.split('.', 1)[0]}{normalized}"
    return normalized


def write_drawing_index(index: DrawingIndex, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
