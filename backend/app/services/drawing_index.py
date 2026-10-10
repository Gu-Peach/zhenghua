from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


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


@dataclass
class DrawingPage:
    pdf_page: int
    function: str | None = None
    internal_page: int | None = None
    object_loc: str | None = None
    title: str | None = None
    text: str = ""
    is_stub: bool = False
    is_non_wiring: bool = False


@dataclass
class DrawingReference:
    source_pdf_page: int
    target_function: str | None
    target_internal_page: int | None
    target_column: int | None
    target_object: str | None
    raw: str
    direction: str = "outgoing"
    external: bool = False
    reason: str | None = None


@dataclass
class DrawingIndex:
    pdf_path: str
    pages: list[DrawingPage] = field(default_factory=list)
    references: list[DrawingReference] = field(default_factory=list)
    page_lookup: dict[str, int] = field(default_factory=dict)

    def resolve(self, function: str | None, internal_page: int | None) -> list[int]:
        if not function or internal_page is None:
            return []
        key = _lookup_key(function, internal_page)
        page = self.page_lookup.get(key)
        return [page] if page is not None else []

    def referenced_pages(self, pdf_page: int) -> list[int]:
        return sorted(
            {
                page
                for reference in self.references
                if reference.source_pdf_page == pdf_page
                for page in self.resolve(reference.target_function, reference.target_internal_page)
            }
        )

    def outgoing_references(self, pdf_page: int) -> list[DrawingReference]:
        return [reference for reference in self.references if reference.source_pdf_page == pdf_page]

    def pages_for_function(self, function: str | None) -> list[int]:
        normalized = _normalize_function(function or "")
        return sorted(page.pdf_page for page in self.pages if page.function == normalized)

    def plan_batches(self, *, target_limit: int = 4, include_unreferenced: bool = True) -> list[dict]:
        """Plan small VLM units from deterministic page/reference evidence.

        Each source page is paired with its resolved target pages. Unresolved
        references remain in the batch metadata so the extractor can emit an
        external/needs-review record instead of inventing an endpoint.
        """
        limit = max(1, int(target_limit))
        batches: list[dict] = []
        for page in self.pages:
            refs = self.outgoing_references(page.pdf_page)
            resolved = self.referenced_pages(page.pdf_page)
            if page.is_non_wiring:
                continue
            if not refs and not include_unreferenced:
                continue
            if not refs:
                batches.append({"batch_id": f"page-{page.pdf_page}", "source_page": page.pdf_page,
                                "target_pages": [], "references": [], "needs_review": page.is_stub})
                continue
            for offset in range(0, max(len(resolved), 1), limit):
                targets = resolved[offset:offset + limit]
                target_set = set(targets)
                selected_references: list[dict] = []
                for reference in refs:
                    resolved_pages = self.resolve(reference.target_function, reference.target_internal_page)
                    include = (
                        not target_set
                        or reference.target_internal_page is None
                        or not resolved_pages
                        or bool(set(resolved_pages) & target_set)
                    )
                    if offset and not resolved_pages:
                        include = False
                    if include:
                        selected_references.append(asdict(reference))
                for selected in selected_references:
                    resolved_target = self.resolve(selected.get("target_function"), selected.get("target_internal_page"))
                    selected["target_pdf_page"] = resolved_target[0] if resolved_target else None
                    if selected["target_internal_page"] is not None and not resolved_target:
                        selected["external"] = True
                        selected["reason"] = "target page not found in PDF index"
                batches.append({
                    "batch_id": f"page-{page.pdf_page}-{offset // limit + 1}",
                    "source_page": page.pdf_page,
                    "target_pages": targets,
                    "references": selected_references,
                    "needs_review": page.is_stub or any(
                        reference.external or not self.resolve(reference.target_function, reference.target_internal_page)
                        for reference in refs
                    ),
                })
        return batches

    def to_dict(self) -> dict:
        return {
            "pdf_path": self.pdf_path,
            "pages": [asdict(page) for page in self.pages],
            "references": [asdict(reference) for reference in self.references],
            "page_lookup": self.page_lookup,
        }


def normalize_function(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().upper()
    return normalized[1:] if normalized.startswith("=") else normalized


def drawing_page_key(function: str | None, internal_page: int | None) -> str | None:
    normalized = normalize_function(function)
    if not normalized or internal_page is None:
        return None
    return f"{normalized}:{int(internal_page)}"


def build_drawing_index(pdf_path: Path) -> DrawingIndex:
    """Build a deterministic EPLAN page/reference index from embedded PDF text."""
    try:
        import pymupdf as pdf_module
    except ImportError:
        try:
            import fitz as pdf_module  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Drawing index requires PyMuPDF") from exc

    index = DrawingIndex(pdf_path=str(pdf_path))
    document = pdf_module.open(pdf_path)
    try:
        for page_number, page in enumerate(document, start=1):
            text = "\n".join(line.strip() for line in page.get_text("text").splitlines() if line.strip())
            drawing_page = parse_drawing_page(page_number, text)
            index.pages.append(drawing_page)
            if drawing_page.function and drawing_page.internal_page is not None:
                index.page_lookup[_lookup_key(drawing_page.function, drawing_page.internal_page)] = page_number
    finally:
        document.close()

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
    object_loc = _header_object_location(text) or (parsed_object if parsed_object and parsed_object.upper() != "ZPMC-EZ" else None)
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
        for page_index, candidate in enumerate(lines[index + 1:index + 8], start=index + 1):
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
    return any(token in normalized for token in (
        "COVER", "INDEX SHEET", "TABLE OF CONTENTS", "SYMBOL VIEW",
        "STRUCTURE IDENTIFIER", "GENERAL DEFINITION", "SAMPLE DRAWING",
    ))


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


def _normalize_function(value: str) -> str:
    value = value.strip().upper()
    if value.startswith("="):
        value = value[1:]
    if value.startswith("."):
        return value
    return value


def _lookup_key(function: str, internal_page: int) -> str:
    normalized = _normalize_function(function)
    return f"{normalized}:{internal_page}"
