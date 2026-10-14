"""Stage 2 page workflow: discover, complete, validate, persist, then advance."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from src.agent.extraction_agent.application.document_extraction.runtime import GraphRuntime
from src.domain.enums import ErrorCode
from src.domain.errors import AgentServiceError
from src.domain.models.stage_persistence import digest
from src.agent.extraction_agent.infrastructure.document.checkpoint import (
    _diagnostics_dir,
    _read_json_object,
    _write_json_atomic,
)
from src.agent.extraction_agent.graphs.document_extraction.cross_page import (
    _build_cross_page_tasks_node,
    _resolve_cross_page_node,
)
from src.agent.extraction_agent.graphs.document_extraction.normalization import (
    _normalize_and_deduplicate_node,
)
from src.agent.extraction_agent.graphs.document_extraction.pages import _page_scan_loop_node
from src.agent.extraction_agent.graphs.document_extraction.state import GraphState


def build_page_extraction_graph(runtime: GraphRuntime, *, pdf_page_number: int) -> Any:
    """Build a standalone workflow for a source page, with a durable save boundary."""

    async def scan(state: GraphState) -> dict[str, Any]:
        previous = runtime.scan_page_numbers
        runtime.scan_page_numbers = {pdf_page_number}
        try:
            return await _page_scan_loop_node(state, runtime, use_checkpoint=False)
        finally:
            runtime.scan_page_numbers = previous

    def plan(state: GraphState) -> dict[str, Any]:
        update = _normalize_and_deduplicate_node(state, runtime)
        combined = cast(GraphState, {**state, **update})
        return {**update, **_build_cross_page_tasks_node(combined, runtime)}

    async def complete(state: GraphState) -> dict[str, Any]:
        return await _resolve_cross_page_node(state, runtime, use_checkpoint=False)

    def validate(state: GraphState) -> dict[str, Any]:
        for unit in state.get("wire_units", {}).values():
            for connection in unit.get("connections", []):
                if (connection.get("end") or {}).get("terminal") in (None, ""):
                    connection["status"] = "needs_review"
        update = _normalize_and_deduplicate_node(state, runtime)
        # A scan with no results is different from a successfully scanned empty page.
        scan_result = state.get("page_scan_results", {}).get(str(pdf_page_number), {})
        needs_review = bool(scan_result.get("needs_review")) or any(
            connection.get("status") not in {"complete", "resolved"}
            or (connection.get("end") or {}).get("terminal") in (None, "")
            for unit in update["wire_units"].values()
            for connection in unit.get("connections", [])
        )
        needs_review = needs_review or any(
            record.status == "needs_review"
            for records in update["wiring_records"].values()
            for record in records
        )
        results = dict(state.get("page_scan_results", {}))
        results[str(pdf_page_number)] = {**scan_result, "needs_review": needs_review}
        return {**update, "page_scan_results": results}

    async def save(state: GraphState) -> dict[str, Any]:
        check_cancelled = getattr(runtime.extraction_client, "check_cancelled", None)
        if check_cancelled:
            check_cancelled()
        if state.get("page_scan_results", {}).get(str(pdf_page_number), {}).get("scan_failed"):
            raise AgentServiceError(
                ErrorCode.MODEL_SCHEMA_INVALID, "Source page scan failed; retry this page."
            )
        result = page_result(state, pdf_page_number)
        if runtime.durable:
            await runtime.durable.commit_page(pdf_page_number, state)
        else:
            directory = _diagnostics_dir(Path(state["output_path"]), runtime.output_mode)
            # This is a required local persistence boundary, not optional diagnostics.
            await asyncio.to_thread(
                _write_json_atomic,
                directory / "completed-pages" / f"{pdf_page_number}.json",
                result,
            )
        runtime.log(f"page_extraction: persisted PDF page {pdf_page_number}")
        return {"processed_pages": [pdf_page_number]}

    graph = StateGraph(GraphState)
    graph.add_node("scan_source", scan)
    graph.add_node("plan_references", plan)
    graph.add_node("complete_connections", complete)
    graph.add_node("validate_page", validate)
    graph.add_node("persist_page", save)
    sequence = [
        START,
        "scan_source",
        "plan_references",
        "complete_connections",
        "validate_page",
        "persist_page",
        END,
    ]
    for source, target in zip(sequence, sequence[1:], strict=False):
        graph.add_edge(source, target)
    return graph.compile()


def page_result(state: GraphState, number: int) -> dict[str, Any]:
    """Store only the source page's completed facts; referenced pages stay evidence."""
    page = next(page for page in state["pages"] if int(page["page_number"]) == number)
    return {
        "workflow_fingerprint": state.get("page_workflow_fingerprint"),
        "page": {key: value for key, value in page.items() if key != "image_path"},
        "scan": state.get("page_scan_results", {}).get(str(number)),
        "wire_units": state.get("wire_units", {}),
        "cross_page_tasks": state.get("cross_page_tasks", []),
        "cross_page_results": state.get("cross_page_results", {}),
    }


async def run_page_extraction(
    *,
    state: GraphState,
    runtime: GraphRuntime,
    pdf_page_number: int,
) -> GraphState:
    """Run one page without scanning unrelated connections on reference pages."""
    return cast(
        GraphState,
        await build_page_extraction_graph(
            runtime,
            pdf_page_number=pdf_page_number,
        ).ainvoke(state),
    )


def _workflow_fingerprint(state: GraphState, runtime: GraphRuntime) -> str:
    return digest(
        {
            "workflow": "page_extraction_v2",
            "client": getattr(runtime.extraction_client, "workflow_fingerprint", None),
            "settings": asdict(runtime.settings),
            "pages": [
                {
                    "number": page["page_number"],
                    "function": page.get("function"),
                    "internal_page": page.get("internal_page"),
                    "image": hashlib.sha256(Path(page["image_path"]).read_bytes()).hexdigest(),
                }
                for page in state["pages"]
            ],
        }
    )


async def _page_extraction_loop_node(state: GraphState, runtime: GraphRuntime) -> dict[str, Any]:
    directory = _diagnostics_dir(Path(state["output_path"]), runtime.output_mode)
    fingerprint = await asyncio.to_thread(_workflow_fingerprint, state, runtime)
    identity = await asyncio.to_thread(_read_json_object, directory / "page-workflow.json")
    local_cache_valid = identity.get("fingerprint") == fingerprint
    if not runtime.durable:
        await asyncio.to_thread(
            _write_json_atomic, directory / "page-workflow.json", {"fingerprint": fingerprint}
        )
    units: dict[str, Any] = {}
    scans: dict[str, Any] = {}
    tasks: list[Any] = []
    completions: dict[str, Any] = {}
    processed: list[int] = []
    for page in state["pages"]:
        check_cancelled = getattr(runtime.extraction_client, "check_cancelled", None)
        if check_cancelled:
            check_cancelled()
        number = int(page["page_number"])
        if runtime.scan_page_numbers is not None and number not in runtime.scan_page_numbers:
            continue
        saved = (
            await runtime.durable.load_page(number)
            if runtime.durable
            else await asyncio.to_thread(_read_json_object, directory / "completed-pages" / f"{number}.json")
            if local_cache_valid
            else None
        )
        if saved:
            if not runtime.durable and saved.get("workflow_fingerprint") != fingerprint:
                saved = None
        if saved:
            runtime.log(f"page_extraction: restored PDF page {number}")
        else:
            initial = cast(
                GraphState,
                {
                    **state,
                    "wire_units": {},
                    "page_scan_results": {},
                    "processed_pages": [],
                    "wiring_records": {},
                    "cross_page_tasks": [],
                    "cross_page_results": {},
                    "page_workflow_fingerprint": fingerprint,
                },
            )
            result = await run_page_extraction(state=initial, runtime=runtime, pdf_page_number=number)
            saved = page_result(result, number)
        units.update(saved.get("wire_units", {}))
        scans[str(number)] = saved.get("scan")
        tasks.extend(saved.get("cross_page_tasks", []))
        completions.update(saved.get("cross_page_results", {}))
        processed.append(number)
    combined = cast(GraphState, {**state, "wire_units": units})
    return {
        **_normalize_and_deduplicate_node(combined, runtime),
        "pages": state["pages"],
        "page_scan_results": scans,
        "processed_pages": processed,
        "cross_page_tasks": tasks,
        "cross_page_results": completions,
        "current_pdf_page": max(processed, default=0) + 1,
        "segments": [[number] for number in processed],
    }
