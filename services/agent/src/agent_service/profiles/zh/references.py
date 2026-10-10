from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from agent_service.domain.models.drawing_index import DrawingPage

from .drawing_index import parse_references


def prepare_reference(
    raw_reference: Mapping[str, Any],
    *,
    source_page: Mapping[str, Any],
    drawing_index: Mapping[str, Any],
) -> dict[str, Any]:
    reference = dict(raw_reference)
    raw = str(reference.get("raw") or "")
    matching = next(
        (
            item
            for item in drawing_index.get("references", [])
            if int(item.get("source_pdf_page", -1)) == int(source_page["page_number"])
            and raw
            and (
                str(item.get("raw") or "") == raw
                or str(item.get("raw") or "") in raw
                or raw in str(item.get("raw") or "")
            )
        ),
        None,
    )
    if raw and (
        matching is None
        or reference.get("target_function") in (None, "")
        or reference.get("target_drawing_page") is None
        or reference.get("target_column") is None
    ):
        parsed = parse_references(
            DrawingPage(
                pdf_page=int(source_page["page_number"]),
                function=source_page.get("function"),
                text=raw,
            )
        )
        if parsed:
            parsed_reference = asdict(parsed[0])
            for key, value in parsed_reference.items():
                if reference.get(key) in (None, ""):
                    reference[key] = value
    if matching:
        for key, value in matching.items():
            if reference.get(key) in (None, ""):
                reference[key] = value
    if reference.get("target_drawing_page") is None:
        reference["target_drawing_page"] = reference.get("target_internal_page") or reference.get(
            "target_page"
        )
    target_function = reference.get("target_function")
    target_drawing_page = reference.get("target_drawing_page")
    target_pdf_page = reference.get("target_pdf_page")
    if target_pdf_page is None and target_function and target_drawing_page is not None:
        lookup = drawing_index.get("page_lookup", {})
        candidates = [str(target_function)]
        if str(target_function).startswith(".") and source_page.get("function"):
            candidates.append(f"{str(source_page['function']).split('.', 1)[0]}{target_function}")
        for candidate in candidates:
            value = lookup.get(f"{candidate}:{int(target_drawing_page)}")
            if value is not None:
                target_pdf_page = int(value)
                break
    reference["target_pdf_page"] = int(target_pdf_page) if target_pdf_page is not None else None
    if reference["target_pdf_page"] is None:
        reference["external"] = True
        reference.setdefault("reason", "target page not found in deterministic page index")
    return reference
