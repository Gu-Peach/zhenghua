from __future__ import annotations

from typing import Any, TypedDict


class PageMeta(TypedDict):
    page_number: int
    image_path: str


class MergeDecision(TypedDict):
    a: int
    b: int
    merge: bool
    project_no_a: str | None
    project_no_b: str | None
    drawing_prefix_a: str | None
    drawing_prefix_b: str | None
    reason: str
    confidence: float
    needs_review: bool


class GraphState(TypedDict):
    pdf_path: str
    pages: list[PageMeta]
    merge_decisions: list[MergeDecision]
    segments: list[list[int]]
    wiring_records: dict[str, list[Any]]
    output_path: str
