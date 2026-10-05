from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


FUNCTION_RE = re.compile(r"(?:Plant\s+Function|Function)\s*:\s*(=?[0-9]{3}\.[A-Z])", re.I)
PAGE_RE = re.compile(r"Page\s+Number\s*:\s*(\d+)", re.I)
OBJECT_RE = re.compile(r"Object\s+Loc\.?\s*:\s*([^\s]+)", re.I)
TITLE_RE = re.compile(r"Page\s+description\s*:\s*(.+?)(?=Project\.NR|DQ\d|Total\s+Page|$)", re.I)
REFERENCE_RE = re.compile(
    r"(?:=)?(?P<sheet>\d{3}\.[A-Z])?\+?(?P<object>[+][\w.]+)"
    r"/(?P<page>\d{1,3})[.\s](?P<column>\d{1,2})",
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


@dataclass
class DrawingReference:
    source_pdf_page: int
    target_function: str | None
    target_internal_page: int | None
    target_column: int | None
    target_object: str | None
    raw: str
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

    def to_dict(self) -> dict:
        return {
            "pdf_path": self.pdf_path,
            "pages": [asdict(page) for page in self.pages],
            "references": [asdict(reference) for reference in self.references],
            "page_lookup": self.page_lookup,
        }


def build_drawing_index(pdf_path: Path) -> DrawingIndex:
    """Build a deterministic EPLAN page/reference index from embedded PDF text."""
    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Drawing index requires PyMuPDF") from exc

    index = DrawingIndex(pdf_path=str(pdf_path))
    document = pymupdf.open(pdf_path)
    for page_number, page in enumerate(document, start=1):
        text = "\n".join(line.strip() for line in page.get_text("text").splitlines() if line.strip())
        drawing_page = parse_drawing_page(page_number, text)
        index.pages.append(drawing_page)
        if drawing_page.function and drawing_page.internal_page is not None:
            index.page_lookup[_lookup_key(drawing_page.function, drawing_page.internal_page)] = page_number

    for page in index.pages:
        index.references.extend(parse_references(page))
    return index


def parse_drawing_page(pdf_page: int, text: str) -> DrawingPage:
    function_match = FUNCTION_RE.search(text)
    page_match = PAGE_RE.search(text)
    object_match = OBJECT_RE.search(text)
    title_match = TITLE_RE.search(" ".join(text.split()))
    function = _normalize_function(function_match.group(1)) if function_match else None
    return DrawingPage(
        pdf_page=pdf_page,
        function=function,
        internal_page=int(page_match.group(1)) if page_match else None,
        object_loc=object_match.group(1) if object_match else None,
        title=title_match.group(1).strip() if title_match else None,
        text=text,
        is_stub=bool(STUB_RE.search(text)),
    )


def parse_references(page: DrawingPage) -> list[DrawingReference]:
    references: list[DrawingReference] = []
    compact_text = " ".join(page.text.split())
    for match in REFERENCE_RE.finditer(compact_text):
        target_function = _normalize_function(match.group("sheet")) if match.group("sheet") else page.function
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
                external=True,
                reason="stub page points to an external diagram",
            )
        )
    return references


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
