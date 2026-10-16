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


def _function_identity(value: Any, source_function: str | None) -> str:
    text = str(value or "").strip().lstrip("=").upper()
    if re.fullmatch(r"\d{3}[A-Z]", text):
        return f"{text[:3]}.{text[3:]}"
    if source_function and re.fullmatch(r"\.?[A-Z]", text):
        return f"{source_function.split('.', 1)[0]}.{text.lstrip('.')}"
    return text


def _unique_indexed_address(
    reference: Mapping[str, Any], source_page: Mapping[str, Any], drawing_index: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Recover only an unavailable address with unique evidence on this source PDF page."""
    function = _function_identity(reference.get("target_function"), source_page.get("function"))
    target_object = str(reference.get("target_object") or "").strip().upper()
    if not function or not target_object:
        return None
    candidates: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in drawing_index.get("references", []):
        if str(item.get("source_pdf_page")) != str(source_page["page_number"]):
            continue
        raw = str(item.get("raw") or "")
        parsed = _raw_address(raw, source_page.get("function")) if raw else None
        if not parsed or parsed["target_function"] != function:
            continue
        if str(parsed.get("target_object") or "").strip().upper() != target_object:
            continue
        if reference.get("target_column") not in (None, parsed["target_column"]):
            continue
        physical = drawing_index.get("page_lookup", {}).get(f"{function}:{parsed['target_drawing_page']}")
        identity = (function, parsed["target_drawing_page"], parsed["target_column"], target_object)
        candidates[identity] = {
            **parsed, "target_pdf_page": int(physical) if physical is not None else None,
            "source_index_raw": raw,
        }
    if len(candidates) != 1:
        return None
    selected = next(iter(candidates.values()))
    return selected if selected["target_pdf_page"] is not None else None


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
    # Only the local PDF index can establish this evidence, never a model claim.
    reference["source_index_raw"] = None
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
        verified = _unique_indexed_address(reference, source_page, drawing_index)
        if verified is not None:
            reference.update(verified)
            reference["external"] = False
            reference["reason"] = "address verified by a unique reference on the same source PDF page"
            return reference
    if reference["target_pdf_page"] is None:
        reference["external"] = True
        reference["reason"] = reference.get("reason") or "target page not found in deterministic page index"
    elif parsed:
        reference["external"] = False
        reference["reason"] = None
    return reference
