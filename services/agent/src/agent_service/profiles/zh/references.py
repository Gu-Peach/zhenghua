from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

ADDRESS_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?P<function>=?(?:\d{3}\.[A-Z]|\.[A-Z]|[A-Z]))?"
    r"(?P<object>\+[A-Za-z0-9][A-Za-z0-9_.-]*)?"
    r"/(?P<page>\d{1,3})\.(?P<column>\d{1,2})(?!\d)",
    re.IGNORECASE,
)
LOCAL_ADDRESS_RE = re.compile(r"^\s*(?P<page>\d{1,3})\.(?P<column>\d{1,2})(?=\s*(?:/|$))")


def _raw_address(raw: str, source_function: str | None) -> dict[str, Any] | None:
    """Parse one wire address; a cabinet code never supplies the function number."""
    matches = list(ADDRESS_RE.finditer(raw))
    local = LOCAL_ADDRESS_RE.search(raw)
    if local:
        matches.insert(0, local)
    if len(matches) != 1:
        return None
    match = matches[0]
    groups = match.groupdict()
    function = (groups.get("function") or "").lstrip("=").upper()
    if not function:
        function = source_function or ""
    elif re.fullmatch(r"\.?[A-Z]", function):
        function = f"{source_function.split('.', 1)[0]}.{function.lstrip('.')}" if source_function else ""
    return {
        "target_function": function or None,
        "target_drawing_page": int(groups["page"]),
        "target_internal_page": int(groups["page"]),
        "target_column": int(groups["column"]),
        "target_object": groups.get("object"),
    }


def prepare_reference(
    raw_reference: Mapping[str, Any],
    *,
    source_page: Mapping[str, Any],
    drawing_index: Mapping[str, Any],
) -> dict[str, Any]:
    """Resolve literal address evidence before model-derived function/page fields."""
    reference = dict(raw_reference)
    raw = str(reference.get("raw") or "")
    if len(list(ADDRESS_RE.finditer(raw))) + bool(LOCAL_ADDRESS_RE.search(raw)) > 1:
        # Multiple literal arrows are ambiguous unless the scanner has split their branches.
        reference.update(
            target_function=None,
            target_drawing_page=None,
            target_internal_page=None,
            target_pdf_page=None,
            target_column=None,
            external=True,
            reason="multiple wire addresses in one reference; split visible branches or review",
        )
        return reference
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
    parsed = _raw_address(raw, source_page.get("function")) if raw else None
    if parsed:
        reference.update(parsed)
        # A model's physical page must not survive correction of its logical address.
        reference["target_pdf_page"] = None
    elif matching:
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
        reference["reason"] = reference.get("reason") or "target page not found in deterministic page index"
    elif parsed:
        reference["external"] = False
        reference["reason"] = None
    return reference
