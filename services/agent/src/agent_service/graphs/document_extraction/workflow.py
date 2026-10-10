from __future__ import annotations

import asyncio
import inspect
import shutil
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, cast

from agent_service.application.document_extraction.ports import (
    DocumentStageClient as VLMClient,
)
from agent_service.application.document_extraction.runtime import (
    AgentRunResult,
    GraphRuntime,
)
from agent_service.application.document_extraction.settings import (
    Settings,
)
from agent_service.domain.models.image_payload import (
    ImagePayload,
)
from agent_service.graphs.document_extraction.cross_page import (
    _build_cross_page_tasks_node,
    _resolve_cross_page_node,
)
from agent_service.graphs.document_extraction.exports import (
    _assemble_table_node,
)
from agent_service.graphs.document_extraction.normalization import (
    _normalize_and_deduplicate_node,
)
from agent_service.graphs.document_extraction.pages import (
    _classify_pages_node,
    _page_scan_loop_node,
    _pdf_to_images_node,
)
from agent_service.graphs.document_extraction.state import (
    GraphState,
    PageMeta,
)
from agent_service.profiles.extraction_policy import (
    ExtractionPolicy,
)

ProgressCallback = Callable[[str], None]

TABLE_HEADERS = [
    "页码",
    "原理号",
    "电压等级",
    "起点代号",
    "起点描述",
    "起点端子",
    "终点代号",
    "终点描述",
    "终点端子",
    "电流",
    "备注",
]


class _FallbackCompiledGraph:
    """Small local runner used only when dependencies are not installed yet.

    Production uses LangGraph from the agent service environment. Keeping this
    runner makes local unit tests and source inspection possible before the
    environment has been provisioned.
    """

    def __init__(self, nodes: list[tuple[str, Callable[[GraphState], Any]]]):
        self._nodes = nodes

    async def ainvoke(self, state: GraphState) -> GraphState:
        current = state
        for _, node in self._nodes:
            update = node(current)
            if asyncio.iscoroutine(update):
                update = await update
            current = {**current, **update}
        return current


class _FallbackStateGraph:
    def __init__(self, _state_type: object):
        self._nodes: list[tuple[str, Callable[[GraphState], Any]]] = []

    def add_node(self, name: str, node: Callable[[GraphState], Any]) -> None:
        self._nodes.append((name, node))

    def add_edge(self, _source: object, _target: object) -> None:
        return None

    def compile(self) -> _FallbackCompiledGraph:
        return _FallbackCompiledGraph(self._nodes)


def build_document_graph(
    *,
    runtime: GraphRuntime,
) -> Any:
    """Build the V1 StateGraph without coupling nodes to FastAPI or storage."""

    try:
        from langgraph.graph import END, START
        from langgraph.graph import StateGraph as LangGraphStateGraph

        graph_type: Any = LangGraphStateGraph
    except ImportError:  # pragma: no cover - exercised only before install
        END, START = "__end__", "__start__"
        graph_type = _FallbackStateGraph

    async def page_scan_node(state: GraphState) -> dict[str, Any]:
        return await _page_scan_loop_node(state, runtime)

    async def build_cross_page_tasks_node(state: GraphState) -> dict[str, Any]:
        return _build_cross_page_tasks_node(state, runtime)

    async def resolve_cross_page_node(state: GraphState) -> dict[str, Any]:
        return await _resolve_cross_page_node(state, runtime)

    async def classify_pages_node(state: GraphState) -> dict[str, Any]:
        return await _classify_pages_node(state, runtime)

    async def assemble_table_node(state: GraphState) -> dict[str, Any]:
        return _assemble_table_node(state, runtime)

    graph = graph_type(GraphState)
    graph.add_node("pdf_to_images", lambda state: _pdf_to_images_node(state, runtime))

    graph.add_node("build_page_index", lambda _state: {})
    graph.add_node("classify_pages", classify_pages_node)
    graph.add_node("page_scan_loop", page_scan_node)
    graph.add_node("normalize_and_deduplicate", lambda state: _normalize_and_deduplicate_node(state, runtime))
    graph.add_node("build_cross_page_tasks", build_cross_page_tasks_node)
    graph.add_node("resolve_cross_page", resolve_cross_page_node)
    graph.add_node(
        "normalize_after_cross_page", lambda state: _normalize_and_deduplicate_node(state, runtime)
    )
    graph.add_node("assemble_table", assemble_table_node)
    sequence = [
        START,
        "pdf_to_images",
        "build_page_index",
        "classify_pages",
        "page_scan_loop",
        "normalize_and_deduplicate",
        "build_cross_page_tasks",
        "resolve_cross_page",
        "normalize_after_cross_page",
        "assemble_table",
        END,
    ]
    for source, target in zip(sequence, sequence[1:], strict=False):
        graph.add_edge(source, target)
    return graph.compile()


async def run_document_extraction(
    *,
    pdf_path: Path,
    output_path: Path,
    settings: Settings,
    preloaded_images: list[ImagePayload] | None = None,
    progress: ProgressCallback | None = None,
    output_mode: str | None = None,
    extraction_client: VLMClient | None = None,
    policy: ExtractionPolicy,
) -> AgentRunResult:

    resolved_mode = (output_mode or settings.output_mode or "library").strip().lower()
    if resolved_mode == "library" and output_path.suffix.lower() == ".xlsx":
        resolved_mode = "single_xlsx"
    if resolved_mode not in {"library", "single_xlsx"}:
        raise ValueError("output_mode must be 'library' or 'single_xlsx'.")

    if extraction_client is None:
        raise ValueError("Document extraction requires a profile-bound stage adapter.")
    supports_page_agent = callable(getattr(extraction_client, "scan_page", None))
    if not supports_page_agent or not callable(getattr(extraction_client, "classify_page", None)):
        raise TypeError("The extraction client must implement all three page-agent stages.")
    runtime = GraphRuntime(
        settings=settings,
        extraction_client=extraction_client,
        output_mode=resolved_mode,
        policy=policy,
        preloaded_images=preloaded_images,
        progress=progress,
    )
    graph = build_document_graph(runtime=runtime)
    initial_state: GraphState = {
        "pdf_path": str(pdf_path),
        "pages": [],
        "segments": [],
        "wiring_records": {},
        "output_path": str(output_path),
        "drawing_index": {},
        "validation_warnings": [],
        "current_pdf_page": 1,
        "page_scan_results": {},
        "wire_units": {},
        "processed_pages": [],
        "connection_records": [],
        "page_classifications": {},
        "plant_function_groups": {},
        "table_headers": TABLE_HEADERS,
        "table_rows_by_unit": {},
        "cross_page_tasks": [],
        "cross_page_results": {},
    }
    try:
        state = await graph.ainvoke(initial_state)
        return AgentRunResult(
            state=state,
            extraction_errors=dict(runtime.extraction_errors or {}),
            validation_warnings=list(runtime.validation_warnings or []),
        )
    finally:
        if runtime.temp_page_dir and not settings.keep_temp_images:
            shutil.rmtree(runtime.temp_page_dir, ignore_errors=True)


async def run_document_stages_2_3(
    *,
    pages: list[PageMeta],
    source_page_numbers: Iterable[int],
    drawing_index: dict[str, Any],
    output_path: Path,
    settings: Settings,
    progress: ProgressCallback | None = None,
    extraction_client: VLMClient | None = None,
    policy: ExtractionPolicy,
) -> AgentRunResult:
    """Run page scanning and cross-page completion from classified page images."""

    selected = {int(value) for value in source_page_numbers}
    if not selected:
        raise ValueError("source_page_numbers must contain at least one page")
    if extraction_client is None:
        raise ValueError("Document extraction requires a profile-bound stage adapter.")
    if not callable(getattr(extraction_client, "scan_page", None)):
        raise TypeError("extraction_client must implement scan_page")

    runtime = GraphRuntime(
        settings=settings,
        extraction_client=extraction_client,
        output_mode="library",
        policy=policy,
        progress=progress,
        scan_page_numbers=selected,
    )
    for page in pages:
        image_path = str(page["image_path"])
        suffix = Path(image_path).suffix.lower()
        mime_type = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"
        payload = ImagePayload(
            name=Path(image_path).name,
            mime_type=mime_type,
            content=b"",
            blank=bool(page.get("blank")),
            page_number=int(page["page_number"]),
        )
        assert runtime.payload_by_path is not None
        resolved_path = await asyncio.to_thread(Path(image_path).resolve)
        runtime.payload_by_path[str(resolved_path)] = payload
        runtime.payload_by_path[image_path] = payload

    state: GraphState = {
        "pdf_path": str(drawing_index.get("pdf_path") or ""),
        "pages": pages,
        "segments": [],
        "wiring_records": {},
        "output_path": str(output_path),
        "drawing_index": drawing_index,
        "validation_warnings": [],
        "current_pdf_page": min(selected),
        "page_scan_results": {},
        "wire_units": {},
        "processed_pages": [],
        "connection_records": [],
        "page_classifications": {},
        "plant_function_groups": {},
        "table_headers": TABLE_HEADERS,
        "table_rows_by_unit": {},
        "cross_page_tasks": [],
        "cross_page_results": {},
    }
    runtime.log(f"stage2_scope: selected {len(selected)} source page(s): {sorted(selected)}")
    for node in (
        _page_scan_loop_node,
        _normalize_and_deduplicate_node,
        _build_cross_page_tasks_node,
        _resolve_cross_page_node,
        _normalize_and_deduplicate_node,
        _assemble_table_node,
    ):
        update = node(state, runtime)
        if inspect.isawaitable(update):
            update = await update
        state = cast(GraphState, {**state, **update})
    return AgentRunResult(
        state=state,
        extraction_errors=dict(runtime.extraction_errors or {}),
        validation_warnings=list(runtime.validation_warnings or []),
    )
