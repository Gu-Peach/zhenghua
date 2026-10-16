from __future__ import annotations

import inspect
import json
from collections.abc import Mapping, Sequence
from typing import Any

from src.agent.extraction_agent.application.document_extraction.runtime import (
    GraphRuntime,
)
from src.agent.extraction_agent.domain.models.wiring import (
    CrossPageCompletion,
    WireConnection,
    WireRecord,
    parse_wire_unit,
)
from src.agent.extraction_agent.domain.table_output import TABLE_HEADERS as TABLE_HEADERS
from src.agent.extraction_agent.graphs.document_extraction.helpers import (
    _find_connection,
    _is_fatal_model_request_error,
    _wire_record_from_connection,
)
from src.agent.extraction_agent.graphs.document_extraction.state import (
    GraphState,
    PageMeta,
)
from src.agent.extraction_agent.infrastructure.document.checkpoint import (
    _cross_page_checkpoint_path,
    _load_cross_page_checkpoint,
    _write_cross_page_checkpoint,
)


def _build_cross_page_tasks_node(state: GraphState, runtime: GraphRuntime) -> dict[str, Any]:
    """Plan scoped cross-page work inside the current Stage 2 page workflow."""

    page_by_number = {int(page["page_number"]): page for page in state.get("pages", [])}
    raw_units: dict[str, dict[str, Any]] = dict(state.get("wire_units") or {})
    records_by_unit = state.get("wiring_records") or {}
    tasks: list[dict[str, Any]] = []

    for unit_id, raw_unit in raw_units.items():
        unit = parse_wire_unit(raw_unit)
        record_lookup = {
            str(record.connection_id): record
            for record in records_by_unit.get(unit_id, [])
            if isinstance(record, WireRecord) and record.connection_id
        }
        for connection_index, raw_connection in enumerate(raw_unit.get("connections", []), start=1):
            connection = WireConnection.model_validate(raw_connection)
            source_pdf_page = int(
                connection.origin_pdf_page
                or (connection.source_pdf_pages[0] if connection.source_pdf_pages else 0)
                or (unit.source_pages[0] if unit.source_pages else 0)
            )
            source_page = page_by_number.get(source_pdf_page)
            if source_page is None:
                continue

            prepared_references = [
                runtime.policy.prepare_reference(
                    reference.model_dump(mode="json", exclude_none=False),
                    source_page=source_page,
                    drawing_index=state.get("drawing_index", {}),
                )
                for reference in connection.references
            ]
            raw_connection["references"] = prepared_references
            for reference in prepared_references:
                if reference.get("target_pdf_page") == source_pdf_page:
                    reference["external"] = True
                    reference["reason"] = "self-reference or unresolved same-page continuation"
            references_by_target: dict[int, list[dict[str, Any]]] = {}
            for reference in prepared_references:
                target_pdf_page = reference.get("target_pdf_page")
                if (
                    reference.get("external")
                    or target_pdf_page is None
                    or int(target_pdf_page) == source_pdf_page
                ):
                    continue
                references_by_target.setdefault(int(target_pdf_page), []).append(reference)
            has_end = bool(connection.end and connection.end.terminal not in (None, ""))
            connection_id = str(
                connection.connection_id
                or connection.local_connection_id
                or f"{unit_id}:p{source_pdf_page}:c{connection_index}"
            )
            raw_connection["connection_id"] = connection_id

            if has_end:
                # Preserve provenance for compatibility clients that already
                # returned a resolved endpoint, but do not call stage three.
                if references_by_target:
                    raw_connection["source_pdf_pages"] = sorted(
                        {
                            source_pdf_page,
                            *references_by_target,
                            *[int(value) for value in connection.source_pdf_pages],
                        }
                    )
                continue
            if not prepared_references:
                continue

            record = record_lookup.get(connection_id)
            source_record = (
                record.model_dump(mode="json", exclude_none=False)
                if record is not None
                else _wire_record_from_connection(
                    unit,
                    WireConnection.model_validate(raw_connection),
                    page_by_number=page_by_number,
                    terminal_strip_mapping=runtime.settings.terminal_strip_mapping,
                ).model_dump(mode="json", exclude_none=False)
            )
            if references_by_target:
                for target_pdf_page in sorted(references_by_target):
                    target_references = references_by_target[target_pdf_page]
                    target_record = dict(source_record)
                    target_record["references"] = target_references
                    tasks.append(
                        {
                            "task_id": f"{connection_id}:target-p{target_pdf_page}",
                            "unit_id": unit_id,
                            "connection_id": connection_id,
                            "source_pdf_page": source_pdf_page,
                            "target_pdf_page": target_pdf_page,
                            "references": target_references,
                            "wire_number": unit.wire_number,
                            "line_number": connection.line_number,
                            "core_number": connection.core_number,
                            "source_record": target_record,
                            "source_page_context": _page_context(source_page),
                            "target_page_context": _page_context(page_by_number.get(target_pdf_page)),
                            "needs_review": False,
                        }
                    )
            else:
                unresolved_record = dict(source_record)
                unresolved_record["references"] = prepared_references
                tasks.append(
                    {
                        "task_id": f"{connection_id}:target-unresolved",
                        "unit_id": unit_id,
                        "connection_id": connection_id,
                        "source_pdf_page": source_pdf_page,
                        "target_pdf_page": None,
                        "references": prepared_references,
                        "wire_number": unit.wire_number,
                        "line_number": connection.line_number,
                        "core_number": connection.core_number,
                        "source_record": unresolved_record,
                        "source_page_context": _page_context(source_page),
                        "needs_review": True,
                    }
                )
                runtime.validation_warnings.append(
                    f"cross-page task {connection_id} has no resolved target PDF page"
                )

    row_count = sum(len(rows) for rows in state.get("table_rows_by_unit", {}).values())
    runtime.log(f"build_cross_page_tasks: rows={row_count} terminal_tasks={len(tasks)}")
    return {"wire_units": raw_units, "cross_page_tasks": tasks}


def _page_context(page: PageMeta | None) -> dict[str, Any]:
    """Keep business addresses separate from physical image-page identifiers."""
    if page is None:
        return {}
    return {
        "pdf_page_number": page.get("page_number"),
        "drawing_function": page.get("function"),
        "drawing_page_number": page.get("internal_page"),
        "object_location": page.get("object_loc"),
    }


def _apply_cross_page_completion(
    wire_units: dict[str, dict[str, Any]],
    task: Mapping[str, Any],
    result: Mapping[str, Any],
) -> None:

    raw_unit = wire_units.get(str(task.get("unit_id")))
    if raw_unit is None:
        return
    raw_connection = _find_connection(raw_unit, str(task.get("connection_id")))
    if raw_connection is None:
        return
    raw_connection["references"] = list(task.get("references") or [])
    end = result.get("end")
    if isinstance(end, dict) and end.get("terminal") not in (None, ""):
        raw_connection["end"] = end
        raw_connection["intermediate_points"] = list(result.get("intermediate_points") or [])
        raw_connection["status"] = result.get("status") or "resolved"
        raw_connection["external_source_required"] = False
        raw_connection["source_pdf_pages"] = sorted(
            {
                int(task.get("source_pdf_page") or 0),
                *[int(value) for value in raw_connection.get("source_pdf_pages", [])],
                int(task["target_pdf_page"]),
            }
        )
    else:
        raw_connection["end"] = None
        raw_connection["status"] = "needs_review"
        raw_connection["external_source_required"] = True
        reasons = list(result.get("warnings") or []) + [
            str(reference["reason"]) for reference in task.get("references", []) if reference.get("reason")
        ]
        if reasons:
            raw_connection["source_note"] = "; ".join(dict.fromkeys(reasons))
    for field in ("current", "current_basis", "current_source_text", "confidence", "source_note"):
        if result.get(field) not in (None, ""):
            raw_connection[field] = result[field]
    source_component = result.get("source_component")
    start = raw_connection.get("start")
    if (
        isinstance(source_component, dict)
        and isinstance(start, dict)
        and str(source_component.get("device") or "").strip()
        and str(source_component.get("basis") or "").strip()
    ):
        # The source terminal, circuit number and direction stay frozen.
        start["device"] = source_component["device"]
        if source_component.get("location") not in (None, ""):
            start["location"] = source_component["location"]
        raw_connection["source_note"] = "; ".join(
            filter(None, [raw_connection.get("source_note"), source_component["basis"]])
        )


def _apply_terminal_task_results(
    wire_units: dict[str, dict[str, Any]],
    tasks: Sequence[Mapping[str, Any]],
    results: Mapping[str, Mapping[str, Any]],
) -> None:

    grouped: dict[tuple[str, str], list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = {}
    for task in tasks:
        result = results.get(str(task.get("task_id")))
        if result is None:
            continue
        key = (str(task.get("unit_id")), str(task.get("connection_id")))
        grouped.setdefault(key, []).append((task, result))

    for (unit_id, connection_id), candidates in grouped.items():
        resolved = [
            (task, result)
            for task, result in candidates
            if isinstance(result.get("end"), dict) and result["end"].get("terminal") not in (None, "")
        ]
        signatures = {
            json.dumps(
                {key: value for key, value in result["end"].items() if key != "terminal_coordinates"},
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
            for _, result in resolved
        }
        if len(signatures) == 1:
            selected = max(
                resolved,
                key=lambda item: float(item[1].get("confidence") or 0.0),
            )
            _apply_cross_page_completion(wire_units, *selected)
            continue
        if not resolved:
            task, result = candidates[0]
            unresolved_task = dict(task)
            unresolved_task["references"] = _unique_task_references(candidates)
            _apply_cross_page_completion(wire_units, unresolved_task, result)
            continue

        raw_unit = wire_units.get(unit_id)
        raw_connection = _find_connection(raw_unit, connection_id) if raw_unit is not None else None
        if raw_connection is None:
            continue
        raw_connection["end"] = None
        raw_connection["references"] = _unique_task_references(candidates)
        raw_connection["status"] = "needs_review"
        raw_connection["external_source_required"] = True
        raw_connection["source_note"] = (
            "Multiple target pages produced conflicting endpoints; manual review is required."
        )


def _unique_task_references(
    candidates: list[tuple[Mapping[str, Any], Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    seen: set[str] = set()
    for task, _ in candidates:
        for reference in task.get("references") or []:
            value = dict(reference)
            key = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
            if key not in seen:
                seen.add(key)
                references.append(value)
    return references


async def _resolve_cross_page_node(
    state: GraphState,
    runtime: GraphRuntime,
    *,
    use_checkpoint: bool = True,
) -> dict[str, Any]:
    """Complete current-page connections, never scan target pages in full."""

    tasks = list(state.get("cross_page_tasks") or [])
    if not tasks:
        runtime.log("resolve_cross_page: no unresolved cross-page rows")
        runtime.log("resolve_cross_page: completed tasks=0")
        return {"cross_page_results": {}, "wire_units": state.get("wire_units", {})}

    page_by_number = {int(page["page_number"]): page for page in state.get("pages", [])}
    checkpoint_path = _cross_page_checkpoint_path(state, runtime)
    # Durable input comes exclusively from the model/item repository.
    completed = (
        {} if runtime.durable or not use_checkpoint else _load_cross_page_checkpoint(checkpoint_path, tasks)
    )
    resolver = getattr(runtime.extraction_client, "resolve_cross_page", None)

    async def resolve_one(task: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        task_id = str(task.get("task_id"))
        if task_id in completed:
            runtime.log(f"resolve_cross_page: restored {task_id}")
            return task_id, dict(completed[task_id])
        target_pdf_page = task.get("target_pdf_page")
        if target_pdf_page is None or not callable(resolver):
            result = {
                "task_id": task_id,
                "status": "needs_review",
                "needs_review": True,
                "end": None,
                "warnings": ["target page unavailable or cross-page resolver is not configured"],
            }
            completed[task_id] = result
            return task_id, result
        target_page = page_by_number.get(int(target_pdf_page))
        if target_page is None:
            result = {
                "task_id": task_id,
                "status": "needs_review",
                "needs_review": True,
                "end": None,
                "warnings": ["one or more indexed target images are unavailable"],
            }
            completed[task_id] = result
            return task_id, result
        target_image = runtime.payload_for(target_page["image_path"])
        source_image = None
        if getattr(runtime.extraction_client, "completion_uses_source_image", True):
            source_page = page_by_number[int(task["source_pdf_page"])]
            source_image = runtime.payload_for(source_page["image_path"])
        try:
            pending = resolver(
                target_image,
                source_image=source_image,
                task_context=json.dumps(dict(task), ensure_ascii=False, default=str),
            )
            if inspect.isawaitable(pending):
                pending = await pending
            completion = (
                pending
                if isinstance(pending, CrossPageCompletion)
                else CrossPageCompletion.model_validate(pending)
            )
            result = completion.model_dump(mode="json", exclude_none=False)
            result["task_id"] = task_id
            runtime.log(
                f"resolve_cross_page: {task_id} target={target_pdf_page} "
                f"status={result.get('status')} end={bool(result.get('end'))}"
            )
        except Exception as exc:
            if _is_fatal_model_request_error(exc):
                raise
            result = {
                "task_id": task_id,
                "status": "needs_review",
                "needs_review": True,
                "end": None,
                "warnings": [str(exc)],
            }
            # Unclear model endpoints are empty facts, not a barrier for later pages.
            runtime.validation_warnings.append(f"cross-page task {task_id} failed: {exc}")
        completed[task_id] = result
        if use_checkpoint and not runtime.durable:
            _write_cross_page_checkpoint(checkpoint_path, tasks, completed, runtime.extraction_errors or {})
        return task_id, result

    pairs = []
    for task in tasks:
        pairs.append(await resolve_one(task))
    results = {task_id: result for task_id, result in pairs}
    wire_units = dict(state.get("wire_units") or {})
    _apply_terminal_task_results(wire_units, tasks, results)
    if use_checkpoint and not runtime.durable:
        _write_cross_page_checkpoint(checkpoint_path, tasks, results, runtime.extraction_errors or {})
    runtime.log(f"resolve_cross_page: completed tasks={len(tasks)}")
    return {"cross_page_results": results, "wire_units": wire_units}
