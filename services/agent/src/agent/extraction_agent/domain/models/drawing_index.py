from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


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

    def to_dict(self) -> dict[str, Any]:
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
