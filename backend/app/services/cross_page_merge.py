from __future__ import annotations

"""Conservative merge of VLM records emitted from source/target page batches."""

from typing import Iterable

from ..schemas.wire import WireRecord


def merge_cross_page_records(records: Iterable[WireRecord]) -> list[WireRecord]:
    """Merge only records with an unambiguous page/device/terminal identity.

    A missing endpoint is deliberately left as a half-line and marked for
    review. Wire numbers are never invented or used as the sole join key.
    """
    items = list(records)
    merged: list[WireRecord] = []
    for record in items:
        if not record.start_device or record.start_terminal in (None, ""):
            record.external_source_required = True
            record.source_type = record.source_type or "unknown"
            record.remark = _mark(record.remark, "起点端子缺失，待人工复核")
            merged.append(record)
            continue

        candidates = [candidate for candidate in merged if _compatible(candidate, record)]
        if len(candidates) == 1:
            _merge_into(candidates[0], record)
            continue
        if len(candidates) > 1:
            record.external_source_required = True
            record.source_type = record.source_type or "mixed"
            record.remark = _mark(record.remark, "跨页端点存在多个候选，待人工复核")
        if not record.end_device and not record.end_terminal:
            record.external_source_required = True
            record.source_type = record.source_type or "mixed"
            record.remark = _mark(record.remark, "终点未在当前批次确认，待人工复核")
        merged.append(record)
    return merged


def _page_key(record: WireRecord) -> str:
    return ",".join(str(page) for page in sorted(set(record.source_pages)))


def _compatible(left: WireRecord, right: WireRecord) -> bool:
    if left.line_number and right.line_number and _text(left.line_number) != _text(right.line_number):
        return False
    for left_value, right_value in (
        (left.start_device, right.start_device),
        (left.start_terminal, right.start_terminal),
        (left.end_device, right.end_device),
        (left.end_terminal, right.end_terminal),
    ):
        if left_value not in (None, "") and right_value not in (None, "") and _text(left_value) != _text(right_value):
            return False
    same_start = all(value not in (None, "") for value in (left.start_device, left.start_terminal, right.start_device, right.start_terminal))
    same_start = same_start and _text(left.start_device) == _text(right.start_device) and _text(left.start_terminal) == _text(right.start_terminal)
    same_end = all(value not in (None, "") for value in (left.end_device, left.end_terminal, right.end_device, right.end_terminal))
    same_end = same_end and _text(left.end_device) == _text(right.end_device) and _text(left.end_terminal) == _text(right.end_terminal)
    return same_start or same_end


def _merge_into(target: WireRecord, source: WireRecord) -> None:
    for field in (
        "wire_number", "attribute", "model", "length", "line_number", "core_number", "color", "spec",
        "start_part", "start_location", "start_device", "start_name", "start_terminal",
        "end_part", "end_location", "end_device", "end_name", "end_terminal", "terminal_strip",
        "remark", "confidence", "source_note", "source_type",
    ):
        if getattr(target, field) in (None, "") and getattr(source, field) not in (None, ""):
            setattr(target, field, getattr(source, field))
    target.source_pages = sorted(set(target.source_pages) | set(source.source_pages))
    target.source_image = ", ".join(dict.fromkeys(filter(None, (target.source_image or "").split(", ") + (source.source_image or "").split(", ")))) or None
    target.external_source_required = target.external_source_required or source.external_source_required
    if target.external_source_required and target.source_type == "pdf":
        target.source_type = "mixed"


def _text(value: object) -> str:
    return str(value).strip().upper() if value is not None else ""


def _mark(current: str | None, message: str) -> str:
    return f"{current}; {message}" if current else message
