from __future__ import annotations

from typing import Any, TypedDict


class PageMeta(TypedDict, total=False):
    page_number: int
    image_path: str
    function: str | None
    internal_page: int | None
    object_loc: str | None
    title: str | None
    is_stub: bool
    is_non_wiring: bool
    blank: bool
    project_no: str | None
    drawing_prefix: str | None
    page_label: str | None
    function_folder: str | None


class ExtractionBatch(TypedDict, total=False):
    batch_id: str
    source_page: int
    target_pages: list[int]
    references: list[dict[str, Any]]
    needs_review: bool


class CrossPageTask(TypedDict, total=False):
    task_id: str
    unit_id: str
    connection_id: str
    source_pdf_page: int
    target_pdf_pages: list[int]
    references: list[dict[str, Any]]
    wire_number: str | None
    line_number: str | None
    core_number: int | str | None
    source_record: dict[str, Any]
    needs_review: bool


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


class GraphState(TypedDict, total=False):
    pdf_path: str
    pages: list[PageMeta]
    merge_decisions: list[MergeDecision]
    segments: list[list[int]]
    wiring_records: dict[str, list[Any]]
    output_path: str
    drawing_index: dict[str, Any]
    extraction_batches: list[ExtractionBatch]
    validation_warnings: list[str]
    current_pdf_page: int
    page_scan_results: dict[str, dict[str, Any]]
    wire_units: dict[str, dict[str, Any]]
    processed_pages: list[int]
    connection_records: list[dict[str, Any]]
    page_classifications: dict[str, dict[str, Any]]
    plant_function_groups: dict[str, list[int]]
    table_headers: list[str]
    table_rows_by_unit: dict[str, list[list[Any]]]
    cross_page_tasks: list[CrossPageTask]
    cross_page_results: dict[str, dict[str, Any]]
