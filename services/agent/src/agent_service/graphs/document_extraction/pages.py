from __future__ import annotations

import asyncio
import inspect
import json
import shutil
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from agent_service.application.document_extraction.runtime import (
    GraphRuntime,
)
from agent_service.domain.models.drawing_index import (
    DrawingPage,
    drawing_page_key,
)
from agent_service.domain.models.wiring import (
    PageClassification,
    PageScanResult,
    WireUnit,
)
from agent_service.graphs.document_extraction.helpers import (
    _drawing_index_from_dict,
    _find_or_create_unit_id,
    _is_fatal_model_request_error,
    _merge_scanned_unit,
    _normalize_plant_function,
    _page_scan_context,
    _safe_plant_function_folder,
)
from agent_service.graphs.document_extraction.state import (
    GraphState,
    PageMeta,
)
from agent_service.infrastructure.document.checkpoint import (
    _diagnostics_dir,
    _read_json_object,
    _write_json_atomic,
    _write_page_scan_checkpoint,
    _write_runtime_diagnostics,
    _write_wire_units_checkpoint,
)
from agent_service.infrastructure.document.classified_images import (
    relocate_classified_image,
)
from agent_service.infrastructure.document.drawing_index import (
    write_drawing_index,
)
from agent_service.infrastructure.document.images import (
    InputFileError,
    path_to_image_payloads,
)


def _pdf_to_images_node(state: GraphState, runtime: GraphRuntime) -> dict[str, Any]:

    output_root = Path(state["output_path"])
    if runtime.output_mode == "library":
        page_dir = output_root / "pages" / ".incoming"
        page_dir.mkdir(parents=True, exist_ok=True)
    else:
        page_dir = output_root.parent / f".{output_root.stem}-pages"
        page_dir.mkdir(parents=True, exist_ok=True)
        runtime.temp_page_dir = page_dir

    if runtime.preloaded_images is not None:
        payloads = list(runtime.preloaded_images)
    else:
        try:
            payloads = path_to_image_payloads(
                Path(state["pdf_path"]),
                runtime.settings.max_pdf_pages,
                pdf_render_scale=runtime.settings.pdf_render_scale,
            )
        except InputFileError:
            raise

    pages: list[PageMeta] = []
    assert runtime.payload_by_path is not None
    for index, payload in enumerate(payloads, start=1):
        path = page_dir / f"page_{index:03d}.png"
        path.write_bytes(payload.content)
        normalized_payload = replace(payload, name=path.name, content=b"", page_number=index)
        runtime.payload_by_path[str(path.resolve())] = normalized_payload
        runtime.payload_by_path[str(path)] = normalized_payload
        pages.append(
            {
                "page_number": index,
                "image_path": str(path.resolve()),
                "function": None,
                "internal_page": None,
                "object_loc": None,
                "title": None,
                "is_stub": False,
                "is_non_wiring": False,
                "blank": bool(payload.blank),
                "project_no": None,
                "drawing_prefix": None,
            }
        )

    pdf_source = Path(state["pdf_path"])
    drawing_index = None
    if pdf_source.is_file():
        try:
            drawing_index = runtime.policy.build_drawing_index(pdf_source)
        except Exception as exc:
            runtime.log(f"drawing_index: unavailable, page identity will be read by Stage 1: {exc}")
    if drawing_index is not None:
        page_meta_by_number = {page.pdf_page: page for page in drawing_index.pages}
        for page in pages:
            indexed = page_meta_by_number.get(page["page_number"])
            if indexed:
                page.update(
                    {
                        "function": indexed.function,
                        "internal_page": indexed.internal_page,
                        "object_loc": indexed.object_loc,
                        "title": indexed.title,
                        "is_stub": indexed.is_stub,
                        "is_non_wiring": indexed.is_non_wiring,
                    }
                )
                project_no, drawing_prefix = runtime.policy.project_identity(indexed.text)
                page.update({"project_no": project_no, "drawing_prefix": drawing_prefix})
        index_path = page_dir.parent / "agent" / "drawing_index.json"
        write_drawing_index(drawing_index, index_path)
    else:
        # The new graph does not require a precomputed batch plan. Page identity
        # is still useful when the embedded-text index is unavailable.
        for page in pages:
            payload = runtime.payload_for(page["image_path"])
            project_no, drawing_prefix = runtime.policy.project_identity(payload.page_text or "")
            page.update({"project_no": project_no, "drawing_prefix": drawing_prefix})

    blank_pages = [index + 1 for index, payload in enumerate(payloads) if payload.blank]
    runtime.log(
        f"pdf_to_images: rendered {len(pages)} page(s) at approximately "
        f"{runtime.settings.pdf_render_dpi} DPI; blank pages={blank_pages or 'none'}"
    )
    del payloads
    return {
        "pages": pages,
        "drawing_index": drawing_index.to_dict() if drawing_index else {},
    }


async def _classify_pages_node(state: GraphState, runtime: GraphRuntime) -> dict[str, Any]:
    """Resolve page identity, group images by Plant Function, and rename by Page Number."""

    output_root = Path(state["output_path"])
    if runtime.output_mode == "library":
        page_root = output_root / "pages"
    else:
        page_root = output_root.parent / f".{output_root.stem}-pages"
    page_root.mkdir(parents=True, exist_ok=True)
    diagnostics_dir = _diagnostics_dir(output_root, runtime.output_mode)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = diagnostics_dir / "page-classifications.json"
    checkpoint = _read_json_object(checkpoint_path)
    classifications = dict(checkpoint.get("classifications") or {})
    ordered_pages = sorted(state.get("pages", []), key=lambda page: int(page["page_number"]))
    classified_pages: list[PageMeta] = []
    function_groups: dict[str, list[int]] = {}
    classifier = getattr(runtime.extraction_client, "classify_page", None)

    for page in ordered_pages:
        physical_page = int(page["page_number"])
        saved = classifications.get(str(physical_page)) or {}
        function = _normalize_plant_function(page.get("function") or saved.get("plant_function"))
        internal_page = page.get("internal_page") or saved.get("page_number")
        blank = bool(page.get("blank"))
        non_wiring = bool(page.get("is_non_wiring"))
        needs_review = False

        has_saved_classification = str(physical_page) in classifications
        if callable(classifier) and not blank and not has_saved_classification:
            try:
                image = runtime.payload_for(page["image_path"])
                pending = classifier(
                    image,
                    context_text=json.dumps(
                        {
                            "pdf_page_number": physical_page,
                            "known_plant_function": function,
                            "known_page_number": internal_page,
                        },
                        ensure_ascii=False,
                    ),
                )
                if inspect.isawaitable(pending):
                    pending = await pending
                classification = (
                    pending
                    if isinstance(pending, PageClassification)
                    else PageClassification.model_validate(pending)
                )
                function = _normalize_plant_function(function or classification.plant_function)
                internal_page = internal_page or classification.page_number
                blank = blank or classification.blank
                non_wiring = non_wiring or classification.non_wiring
                needs_review = classification.needs_review or not function or internal_page is None
                classifications[str(physical_page)] = classification.model_dump(mode="json")
            except Exception as exc:
                if _is_fatal_model_request_error(exc):
                    raise
                needs_review = True
                assert runtime.extraction_errors is not None
                runtime.extraction_errors[f"classification-page-{physical_page:04d}"] = str(exc)
                runtime.validation_warnings.append(f"page {physical_page} classification failed: {exc}")
                runtime.log(f"classify_pages: PDF page {physical_page} failed: {exc}")

        function_folder = function or "UNKNOWN"
        safe_folder = _safe_plant_function_folder(function_folder)
        page_label = str(int(internal_page)) if internal_page is not None else f"pdf_{physical_page:04d}"
        destination = page_root / safe_folder / f"{page_label}.png"
        source = Path(page["image_path"])
        destination, source_key, collision = await asyncio.to_thread(
            relocate_classified_image,
            source,
            destination,
            restored=has_saved_classification,
            page_label=page_label,
            pdf_page=physical_page,
        )
        if collision:
            needs_review = True
            runtime.validation_warnings.append(
                f"duplicate Plant Function/Page Number {function_folder}/{page_label}; "
                f"kept PDF page {physical_page} separately"
            )

        page.update(
            {
                "function": function,
                "internal_page": int(internal_page) if internal_page is not None else None,
                "page_label": page_label,
                "function_folder": safe_folder,
                "is_non_wiring": non_wiring,
                "blank": blank,
                "needs_review": needs_review,
                "image_path": str(destination.resolve()),
            }
        )
        page_by_number = int(page["page_number"])
        if function and internal_page is not None:
            function_groups.setdefault(function, []).append(page_by_number)

        if runtime.payload_by_path is not None:
            old_payload = runtime.payload_by_path.pop(source_key, None) or runtime.payload_by_path.pop(
                str(source), None
            )
            if old_payload is not None:
                updated_payload = replace(
                    old_payload,
                    name=destination.name,
                    blank=blank,
                    page_number=page_by_number,
                )
                runtime.payload_by_path[str(destination.resolve())] = updated_payload
                runtime.payload_by_path[str(destination)] = updated_payload
        classified_pages.append(page)

    for function, pdf_pages in function_groups.items():
        function_groups[function] = sorted(
            set(pdf_pages),
            key=lambda number: (
                next(
                    (
                        int(page["internal_page"] or 0)
                        for page in classified_pages
                        if int(page["page_number"]) == number and page.get("internal_page") is not None
                    ),
                    10**9,
                ),
                number,
            ),
        )

    drawing_index = dict(state.get("drawing_index") or {})
    indexed_by_pdf = {
        int(page.get("pdf_page")): page
        for page in drawing_index.get("pages", [])
        if page.get("pdf_page") is not None
    }
    page_lookup: dict[str, int] = {}
    updated_index_pages: list[dict[str, Any]] = []
    for page in classified_pages:
        indexed = dict(indexed_by_pdf.get(int(page["page_number"]), {}))
        indexed.update(
            {
                "pdf_page": int(page["page_number"]),
                "function": page.get("function"),
                "internal_page": page.get("internal_page"),
                "object_loc": page.get("object_loc"),
                "title": page.get("title"),
                "is_stub": bool(page.get("is_stub")),
                "is_non_wiring": bool(page.get("is_non_wiring")),
            }
        )
        if indexed.get("function") and indexed.get("internal_page") is not None:
            key = drawing_page_key(indexed["function"], indexed["internal_page"])
            assert key is not None
            if key in page_lookup and page_lookup[key] != indexed["pdf_page"]:
                runtime.validation_warnings.append(
                    f"drawing index identity collision for {key}: "
                    f"PDF pages {page_lookup[key]} and {indexed['pdf_page']}"
                )
            else:
                page_lookup[key] = int(indexed["pdf_page"])
        updated_index_pages.append(indexed)

    drawing_index["pages"] = updated_index_pages
    drawing_index["page_lookup"] = page_lookup
    references: list[dict[str, Any]] = []
    for indexed in updated_index_pages:
        if not indexed.get("text"):
            continue
        references.extend(
            asdict(reference) for reference in runtime.policy.parse_references(DrawingPage(**indexed))
        )
    drawing_index["references"] = references
    drawing_index.setdefault("pdf_path", str(state.get("pdf_path") or ""))
    write_drawing_index(
        _drawing_index_from_dict(drawing_index),
        diagnostics_dir / "drawing_index.json",
    )

    _write_json_atomic(
        checkpoint_path,
        {
            "version": 1,
            "classifications": classifications,
            "plant_function_groups": function_groups,
        },
    )
    incoming_dir = page_root / ".incoming"
    if incoming_dir.is_dir():
        shutil.rmtree(incoming_dir, ignore_errors=True)
    ordered_classified_pages = sorted(
        classified_pages,
        key=lambda page: (
            str(page.get("function") or "~"),
            int(page["internal_page"] or 0) if page.get("internal_page") is not None else 10**9,
            int(page["page_number"]),
        ),
    )
    runtime.log(
        "classify_pages: "
        + ", ".join(f"{function}={len(numbers)}" for function, numbers in sorted(function_groups.items()))
    )
    return {
        "pages": ordered_classified_pages,
        "page_classifications": classifications,
        "plant_function_groups": function_groups,
        "drawing_index": drawing_index,
    }


async def _page_scan_loop_node(state: GraphState, runtime: GraphRuntime) -> dict[str, Any]:
    """Scan each physical page once and build logical wire units incrementally."""

    diagnostics_dir = _diagnostics_dir(Path(state["output_path"]), runtime.output_mode)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    page_checkpoint = diagnostics_dir / "page-scan-checkpoint.json"
    unit_checkpoint = diagnostics_dir / "wire-units-checkpoint.json"

    saved_pages = _read_json_object(page_checkpoint)
    if saved_pages.get("version") != 3:
        saved_pages = {}
    page_scan_results: dict[str, dict[str, Any]] = dict(state.get("page_scan_results") or {})
    page_scan_results.update(saved_pages.get("page_scan_results") or {})
    processed_pages = {int(value) for value in saved_pages.get("processed_pages", []) if str(value).isdigit()}
    processed_pages.update(int(value) for value in state.get("processed_pages", []) if str(value).isdigit())

    saved_units = _read_json_object(unit_checkpoint)
    if saved_units.get("version") != 3:
        saved_units = {}
    wire_units: dict[str, dict[str, Any]] = dict(state.get("wire_units") or {})
    wire_units.update(saved_units.get("wire_units") or {})
    all_pages = list(state.get("pages", []))
    scan_pages = all_pages
    if runtime.scan_page_numbers is not None:
        scan_pages = [page for page in all_pages if int(page["page_number"]) in runtime.scan_page_numbers]
    for page in scan_pages:
        page_number = int(page["page_number"])
        saved_result = page_scan_results.get(str(page_number)) or {}
        if (
            page_number in processed_pages
            and str(page_number) in page_scan_results
            and not saved_result.get("scan_failed")
        ):
            runtime.log(f"page_scan: restored PDF page {page_number}")
            continue

        scan_failed = False
        try:
            image = runtime.payload_for(page["image_path"])
            if page.get("blank") or image.blank or page.get("is_non_wiring"):
                result = PageScanResult(
                    pdf_page_number=page_number,
                    drawing_function=page.get("function"),
                    drawing_page_number=page.get("internal_page"),
                    drawing_object_location=page.get("object_loc"),
                    blank=True,
                    units=[],
                )
            else:
                scanner = runtime.extraction_client.scan_page
                page_context = _page_scan_context(
                    page,
                    state.get("drawing_index", {}),
                    related_pages=[],
                )
                try:
                    pending = scanner(
                        image,
                        page_context=page_context,
                    )
                except TypeError as exc:
                    if "page_context" not in str(exc):
                        raise
                    pending = scanner(image)
                if inspect.isawaitable(pending):
                    pending = await pending
                if isinstance(pending, PageScanResult):
                    result = pending
                else:
                    result = PageScanResult.model_validate_json(
                        json.dumps(pending, ensure_ascii=False, default=str),
                    )
                # Embedded PDF text is a deterministic source for page identity;
                # it takes precedence over a VLM transcription when available.
                result.pdf_page_number = page_number
                result.drawing_function = page.get("function") or result.drawing_function
                result.drawing_page_number = page.get("internal_page") or result.drawing_page_number
                result.drawing_object_location = page.get("object_loc") or result.drawing_object_location
                if result.blank:
                    result.units = []
                page.update(
                    {
                        "function": page.get("function") or result.drawing_function,
                        "internal_page": page.get("internal_page") or result.drawing_page_number,
                        "object_loc": page.get("object_loc") or result.drawing_object_location,
                    }
                )
        except Exception as exc:
            if _is_fatal_model_request_error(exc):
                raise
            message = f"page {page_number} scan failed: {exc}"
            assert runtime.extraction_errors is not None
            runtime.extraction_errors[f"page-{page_number:04d}"] = str(exc)
            runtime.validation_warnings.append(message)
            result = PageScanResult(
                pdf_page_number=page_number,
                drawing_function=page.get("function"),
                drawing_page_number=page.get("internal_page"),
                drawing_object_location=page.get("object_loc"),
                needs_review=True,
                units=[],
                warnings=[str(exc)],
            )
            scan_failed = True
            _write_runtime_diagnostics(diagnostics_dir, runtime)
            runtime.log(message)
        result_dict = result.model_dump(mode="json", exclude_none=False)
        if scan_failed:
            result_dict["scan_failed"] = True
        page_scan_results[str(page_number)] = result_dict

        if result.units:
            for unit_index, raw_unit in enumerate(result.units, start=1):
                unit = raw_unit if isinstance(raw_unit, WireUnit) else WireUnit.model_validate(raw_unit)
                unit_id = _find_or_create_unit_id(
                    wire_units,
                    unit,
                    page,
                    page_number,
                    unit_index,
                )
                _merge_scanned_unit(
                    wire_units,
                    unit,
                    unit_id=unit_id,
                    page=page,
                    page_number=page_number,
                    unit_index=unit_index,
                )
                _write_wire_units_checkpoint(unit_checkpoint, wire_units)

        processed_pages.add(page_number)
        _write_page_scan_checkpoint(
            page_checkpoint,
            processed_pages=sorted(processed_pages),
            page_scan_results=page_scan_results,
        )
        _write_wire_units_checkpoint(unit_checkpoint, wire_units)
        reference_count = sum(
            len(connection.references) for unit in result.units for connection in unit.connections
        )
        runtime.log(
            f"page_scan: PDF page {page_number} units={len(result.units)} references={reference_count}"
        )

    return {
        "pages": state.get("pages", []),
        "page_scan_results": page_scan_results,
        "wire_units": wire_units,
        "processed_pages": sorted(processed_pages),
        "current_pdf_page": (max(processed_pages) + 1) if processed_pages else 1,
        "segments": [
            [int(page["page_number"])]
            for page in scan_pages
            if not page.get("blank") and not page.get("is_non_wiring")
        ],
    }
