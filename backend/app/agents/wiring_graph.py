from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import re
import shutil
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from ..core.config import Settings
from ..core.terminal_strips import (
    ALLOWED_TERMINAL_CODES,
    ALLOWED_TERMINAL_STRIPS,
    allowed_start_terminal_code,
    normalize_terminal_strip,
    terminal_strip_for_device,
)
from ..schemas.wire import (
    CrossPageCompletion,
    Endpoint,
    PageClassification,
    PageScanResult,
    ReferenceEvidence,
    WireConnection,
    WireRecord,
    WireUnit,
)
from ..services.excel_writer import (
    records_by_segment_to_xlsx_bytes,
    records_to_xlsx_bytes,
    table_to_xlsx_bytes,
)
from ..services.xls_template_writer import records_to_template_xls_bytes, records_to_template_xlsx_bytes
from ..services.cross_page_merge import merge_cross_page_records
from ..services.file_inputs import InputFileError, path_to_image_payloads
from ..services.drawing_index import (
    DrawingPage,
    build_drawing_index,
    drawing_page_key,
    parse_references,
    write_drawing_index,
)
from ..services.prompt_loader import load_segment_few_shot_examples
from ..services.vlm_client import (
    ImagePayload,
    VLMClient,
    build_segment_few_shot_messages,
    parse_page_scan_result,
    normalize_wire_record,
    attach_source_metadata,
)
from .segment_decider import SegmentDecider, VLMSegmentDecider, degraded_decision
from .state import GraphState, MergeDecision, PageMeta


logger = logging.getLogger(__name__)


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

    Production uses LangGraph from backend/requirements.txt. Keeping this
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


@dataclass
class AgentRunResult:
    state: GraphState
    extraction_errors: dict[str, str]
    validation_warnings: list[str]


@dataclass
class GraphRuntime:
    settings: Settings
    extraction_client: VLMClient
    segment_decider: SegmentDecider
    segment_prompt: str
    output_mode: str
    preloaded_images: list[ImagePayload] | None = None
    progress: ProgressCallback | None = None
    payload_by_path: dict[str, ImagePayload] | None = None
    temp_page_dir: Path | None = None
    extraction_errors: dict[str, str] | None = None
    validation_warnings: list[str] | None = None
    scan_page_numbers: set[int] | None = None

    def __post_init__(self) -> None:
        self.payload_by_path = {}
        self.extraction_errors = {}
        self.validation_warnings = []

    def log(self, message: str) -> None:
        logger.info(message)
        if self.progress:
            self.progress(message)

    def payload_for(self, image_path: str) -> ImagePayload:
        assert self.payload_by_path is not None
        key = str(Path(image_path).resolve())
        payload = self.payload_by_path.get(key) or self.payload_by_path.get(image_path)
        if payload is None:
            raise FileNotFoundError(f"Rendered page is not registered: {image_path}")
        if not payload.content:
            path = Path(image_path)
            if path.is_file():
                payload = replace(payload, content=path.read_bytes())
                self.payload_by_path[key] = payload
                self.payload_by_path[image_path] = payload
        return payload


def build_wiring_graph(
    *,
    runtime: GraphRuntime,
    segment_decider: SegmentDecider | None = None,
) -> Any:
    """Build the V1 StateGraph without coupling nodes to FastAPI or storage."""
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:  # pragma: no cover - exercised only before install
        END, START, StateGraph = object(), object(), _FallbackStateGraph

    if segment_decider is not None:
        runtime.segment_decider = segment_decider

    async def segment_node(state: GraphState) -> dict[str, Any]:
        return await _segment_node(state, runtime)

    async def extract_node(state: GraphState) -> dict[str, Any]:
        return await _extract_wiring_node(state, runtime)

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

    graph = StateGraph(GraphState)
    graph.add_node("pdf_to_images", lambda state: _pdf_to_images_node(state, runtime))

    # Custom test doubles written for the old API only expose extract_images.
    # Keep that path available while the real VLMClient uses the new graph.
    supports_page_agent = callable(getattr(runtime.extraction_client, "scan_page", None))
    if supports_page_agent:
        graph.add_node("build_page_index", lambda _state: {})
        graph.add_node("classify_pages", classify_pages_node)
        graph.add_node("page_scan_loop", page_scan_node)
        graph.add_node("normalize_and_deduplicate", lambda state: _normalize_and_deduplicate_node(state, runtime))
        graph.add_node("build_cross_page_tasks", build_cross_page_tasks_node)
        graph.add_node("resolve_cross_page", resolve_cross_page_node)
        graph.add_node(
            "normalize_after_cross_page",
            lambda state: _normalize_and_deduplicate_node(state, runtime),
        )
        graph.add_node("assemble_table", assemble_table_node)
        graph.add_edge(START, "pdf_to_images")
        graph.add_edge("pdf_to_images", "build_page_index")
        graph.add_edge("build_page_index", "classify_pages")
        graph.add_edge("classify_pages", "page_scan_loop")
        graph.add_edge("page_scan_loop", "normalize_and_deduplicate")
        graph.add_edge("normalize_and_deduplicate", "build_cross_page_tasks")
        graph.add_edge("build_cross_page_tasks", "resolve_cross_page")
        graph.add_edge("resolve_cross_page", "normalize_after_cross_page")
        graph.add_edge("normalize_after_cross_page", "assemble_table")
    else:
        graph.add_node("segment", segment_node)
        graph.add_node("extract_wiring", extract_node)
        graph.add_node("assemble_xlsx", lambda state: _assemble_xlsx_node(state, runtime))
        graph.add_edge(START, "pdf_to_images")
        graph.add_edge("pdf_to_images", "segment")
        graph.add_edge("segment", "extract_wiring")
        graph.add_edge("extract_wiring", "assemble_xlsx")
    if supports_page_agent:
        graph.add_edge("assemble_table", END)
    else:
        graph.add_edge("assemble_xlsx", END)
    return graph.compile()


async def run_wiring_agent(
    *,
    pdf_path: Path,
    output_path: Path,
    settings: Settings,
    extraction_prompt: str,
    segment_prompt: str,
    preloaded_images: list[ImagePayload] | None = None,
    progress: ProgressCallback | None = None,
    output_mode: str | None = None,
    segment_decider: SegmentDecider | None = None,
    extraction_client: VLMClient | None = None,
) -> AgentRunResult:
    resolved_mode = (output_mode or settings.output_mode or "library").strip().lower()
    if resolved_mode == "library" and output_path.suffix.lower() == ".xlsx":
        resolved_mode = "single_xlsx"
    if resolved_mode not in {"library", "single_xlsx"}:
        raise ValueError("output_mode must be 'library' or 'single_xlsx'.")

    extraction_client = extraction_client or VLMClient(settings, extraction_prompt)
    supports_page_agent = callable(getattr(extraction_client, "scan_page", None))
    segment_prefix_messages = [] if supports_page_agent else _load_segment_prefix_messages(settings)
    runtime = GraphRuntime(
        settings=settings,
        extraction_client=extraction_client,
        segment_decider=segment_decider or _make_segment_decider(
            client=extraction_client,
            prompt=segment_prompt,
            runtime=None,
            retry_count=settings.segment_retry_count,
            prefix_messages=segment_prefix_messages,
        ),
        segment_prompt=segment_prompt,
        output_mode=resolved_mode,
        preloaded_images=preloaded_images,
        progress=progress,
    )
    # The loader is intentionally late-bound: pdf_to_images populates this map.
    if segment_decider is None:
        runtime.segment_decider = _make_segment_decider(
            client=extraction_client,
            prompt=segment_prompt,
            runtime=runtime,
            retry_count=settings.segment_retry_count,
            prefix_messages=segment_prefix_messages,
        )

    graph = build_wiring_graph(runtime=runtime)
    initial_state: GraphState = {
        "pdf_path": str(pdf_path),
        "pages": [],
        "merge_decisions": [],
        "segments": [],
        "wiring_records": {},
        "output_path": str(output_path),
        "drawing_index": {},
        "extraction_batches": [],
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


async def run_wiring_agent_stages_2_3(
    *,
    pages: list[PageMeta],
    source_page_numbers: Iterable[int],
    drawing_index: dict[str, Any],
    output_path: Path,
    settings: Settings,
    extraction_prompt: str,
    progress: ProgressCallback | None = None,
    extraction_client: VLMClient | None = None,
) -> AgentRunResult:
    """Run page scanning and cross-page completion from classified page images."""
    selected = {int(value) for value in source_page_numbers}
    if not selected:
        raise ValueError("source_page_numbers must contain at least one page")
    extraction_client = extraction_client or VLMClient(settings, extraction_prompt)
    if not callable(getattr(extraction_client, "scan_page", None)):
        raise TypeError("extraction_client must implement scan_page")

    runtime = GraphRuntime(
        settings=settings,
        extraction_client=extraction_client,
        segment_decider=_make_segment_decider(
            client=extraction_client,
            prompt="",
            runtime=None,
            retry_count=0,
            prefix_messages=[],
        ),
        segment_prompt="",
        output_mode="library",
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
        runtime.payload_by_path[str(Path(image_path).resolve())] = payload
        runtime.payload_by_path[image_path] = payload

    state: GraphState = {
        "pdf_path": str(drawing_index.get("pdf_path") or ""),
        "pages": pages,
        "merge_decisions": [],
        "segments": [],
        "wiring_records": {},
        "output_path": str(output_path),
        "drawing_index": drawing_index,
        "extraction_batches": [],
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
    runtime.log(
        f"stage2_scope: selected {len(selected)} source page(s): {sorted(selected)}"
    )
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
        state = {**state, **update}
    return AgentRunResult(
        state=state,
        extraction_errors=dict(runtime.extraction_errors or {}),
        validation_warnings=list(runtime.validation_warnings or []),
    )


def _make_segment_decider(
    *,
    client: VLMClient,
    prompt: str,
    runtime: GraphRuntime | None,
    retry_count: int,
    prefix_messages: list[dict[str, Any]],
) -> VLMSegmentDecider:
    def load_image(image_path: str) -> ImagePayload:
        if runtime is None:
            raise RuntimeError("Segment image loader was used before graph runtime initialization.")
        return runtime.payload_for(image_path)

    return VLMSegmentDecider(
        client=client,
        prompt=prompt,
        image_loader=load_image,
        retry_count=retry_count,
        prefix_messages=prefix_messages,
    )


def _diagnostics_dir(output_path: Path, output_mode: str) -> Path:
    if output_mode == "library" or output_path.is_dir():
        return output_path / "agent"
    return output_path.parent / f"{output_path.stem}.agent"


def _extraction_checkpoint_path(state: GraphState, runtime: GraphRuntime) -> Path:
    diagnostics_dir = _diagnostics_dir(Path(state["output_path"]), runtime.output_mode)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    return diagnostics_dir / "extraction-checkpoint.json"


def _load_extraction_checkpoint(
    path: Path,
    batches: list[Mapping[str, Any]],
) -> dict[str, list[WireRecord]]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        expected_ids = [str(batch.get("batch_id")) for batch in batches]
        if payload.get("batch_ids") != expected_ids:
            return {}
        completed = payload.get("completed") or {}
        if not isinstance(completed, dict):
            return {}
        restored: dict[str, list[WireRecord]] = {}
        for batch_id, raw_records in completed.items():
            if not isinstance(raw_records, list) or batch_id not in expected_ids:
                continue
            restored[str(batch_id)] = [WireRecord.model_validate(record) for record in raw_records]
        return restored
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("Ignoring invalid extraction checkpoint %s: %s", path, exc)
        return {}


def _write_extraction_checkpoint(
    path: Path,
    batches: list[Mapping[str, Any]],
    completed: Mapping[str, list[WireRecord]],
    errors: Mapping[str, str],
) -> None:
    payload = {
        "version": 1,
        "batch_ids": [str(batch.get("batch_id")) for batch in batches],
        "completed": {
            batch_id: [record.model_dump(mode="json", exclude_none=False) for record in records]
            for batch_id, records in completed.items()
        },
        "errors": dict(errors),
    }
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _load_segment_prefix_messages(settings: Settings) -> list[dict[str, Any]]:
    if not settings.segment_few_shot_images:
        return []
    try:
        examples = load_segment_few_shot_examples(settings.segment_few_shot_examples_dir)
        messages = build_segment_few_shot_messages(examples)
        logger.info("segment few-shot: loaded %s example(s)", len(examples))
        return messages
    except Exception as exc:
        logger.warning("segment few-shot examples could not be loaded: %s", exc)
        return []


def _pdf_to_images_node(state: GraphState, runtime: GraphRuntime) -> dict[str, Any]:
    output_root = Path(state["output_path"])
    supports_page_agent = callable(getattr(runtime.extraction_client, "scan_page", None))
    if runtime.output_mode == "library":
        page_dir = output_root / "pages" / ".incoming" if supports_page_agent else output_root / "pages"
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
        pages.append({"page_number": index, "image_path": str(path.resolve()),
                      "function": None, "internal_page": None, "object_loc": None,
                      "title": None, "is_stub": False, "is_non_wiring": False,
                      "blank": bool(payload.blank), "project_no": None, "drawing_prefix": None})

    pdf_source = Path(state["pdf_path"])
    index = None
    if pdf_source.is_file():
        try:
            index = build_drawing_index(pdf_source)
        except Exception as exc:
            runtime.log(f"drawing_index: unavailable, falling back to VLM adjacent segmentation: {exc}")
    if index is not None:
        page_meta_by_number = {page.pdf_page: page for page in index.pages}
        for page in pages:
            indexed = page_meta_by_number.get(page["page_number"])
            if indexed:
                page.update({"function": indexed.function, "internal_page": indexed.internal_page,
                             "object_loc": indexed.object_loc, "title": indexed.title,
                             "is_stub": indexed.is_stub, "is_non_wiring": indexed.is_non_wiring})
                project_no, drawing_prefix = _project_and_prefix(indexed.text)
                page.update({"project_no": project_no, "drawing_prefix": drawing_prefix})
        index_path = page_dir.parent / "agent" / "drawing_index.json"
        write_drawing_index(index, index_path)
    else:
        # The new graph does not require a precomputed batch plan. Page identity
        # is still useful when the embedded-text index is unavailable.
        for page in pages:
            payload = runtime.payload_for(page["image_path"])
            project_no, drawing_prefix = _project_and_prefix(payload.page_text or "")
            page.update({"project_no": project_no, "drawing_prefix": drawing_prefix})

    blank_pages = [index + 1 for index, payload in enumerate(payloads) if payload.blank]
    runtime.log(
        f"pdf_to_images: rendered {len(pages)} page(s) at approximately "
        f"{runtime.settings.pdf_render_dpi} DPI; blank pages={blank_pages or 'none'}"
    )
    del payloads
    return {"pages": pages, "drawing_index": index.to_dict() if index else {}, "extraction_batches": []}


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
                needs_review = True
                assert runtime.extraction_errors is not None
                runtime.extraction_errors[f"classification-page-{physical_page:04d}"] = str(exc)
                runtime.validation_warnings.append(
                    f"page {physical_page} classification failed: {exc}"
                )
                runtime.log(f"classify_pages: PDF page {physical_page} failed: {exc}")

        function_folder = function or "UNKNOWN"
        safe_folder = _safe_plant_function_folder(function_folder)
        page_label = str(int(internal_page)) if internal_page is not None else f"pdf_{physical_page:04d}"
        destination = page_root / safe_folder / f"{page_label}.png"
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = Path(page["image_path"])
        if destination.exists() and source.resolve() != destination.resolve():
            if has_saved_classification:
                # A resumed run renders into .incoming again. Reuse the already
                # classified image instead of manufacturing a duplicate page.
                source.unlink(missing_ok=True)
            else:
                destination = destination.with_name(f"{page_label}__pdf_{physical_page:04d}.png")
                needs_review = True
                runtime.validation_warnings.append(
                    f"duplicate Plant Function/Page Number {function_folder}/{page_label}; kept PDF page {physical_page} separately"
                )
        if source.is_file() and source.resolve() != destination.resolve():
            shutil.move(str(source), str(destination))

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
            old_payload = runtime.payload_by_path.pop(str(source.resolve()), None) or runtime.payload_by_path.pop(str(source), None)
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
                    (int(page["internal_page"]) for page in classified_pages
                     if int(page["page_number"]) == number and page.get("internal_page") is not None),
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
            if key in page_lookup and page_lookup[key] != indexed["pdf_page"]:
                runtime.validation_warnings.append(
                    f"drawing index identity collision for {key}: PDF pages {page_lookup[key]} and {indexed['pdf_page']}"
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
            asdict(reference)
            for reference in parse_references(DrawingPage(**indexed))
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
            int(page["internal_page"]) if page.get("internal_page") is not None else 10**9,
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


def _normalize_plant_function(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper().lstrip("=")
    return normalized or None


def _safe_plant_function_folder(value: str) -> str:
    normalized = _normalize_plant_function(value) or "UNKNOWN"
    return re.sub(r"[^0-9A-Z._-]+", "_", normalized).strip("._") or "UNKNOWN"


def _drawing_index_from_dict(value: Mapping[str, Any]) -> Any:
    from ..services.drawing_index import DrawingIndex, DrawingReference

    pages = [DrawingPage(**page) for page in value.get("pages", [])]
    references = [DrawingReference(**reference) for reference in value.get("references", [])]
    return DrawingIndex(
        pdf_path=str(value.get("pdf_path") or ""),
        pages=pages,
        references=references,
        page_lookup=dict(value.get("page_lookup") or {}),
    )


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
        scan_pages = [
            page for page in all_pages
            if int(page["page_number"]) in runtime.scan_page_numbers
        ]
    page_by_number = {int(page["page_number"]): page for page in all_pages}
    for page in scan_pages:
        page_number = int(page["page_number"])
        saved_result = page_scan_results.get(str(page_number)) or {}
        if page_number in processed_pages and str(page_number) in page_scan_results and not saved_result.get("scan_failed"):
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
                scanner = getattr(runtime.extraction_client, "scan_page")
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
                    result = parse_page_scan_result(
                        json.dumps(pending, ensure_ascii=False, default=str),
                        default_pdf_page=page_number,
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
                connection_ids = _merge_scanned_unit(
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
        runtime.log(
            f"page_scan: PDF page {page_number} units={len(result.units)} "
            f"references={sum(len(connection.references) for unit in result.units for connection in unit.connections)}"
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
        "merge_decisions": [],
    }


def _normalize_and_deduplicate_node(state: GraphState, runtime: GraphRuntime) -> dict[str, Any]:
    """Flatten logical units into one XLSX/API row per concrete connection."""
    page_by_number = {int(page["page_number"]): page for page in state.get("pages", [])}
    normalized_units: dict[str, dict[str, Any]] = {}
    records_by_unit: dict[str, list[WireRecord]] = {}
    connection_records: list[dict[str, Any]] = []
    rejected_connections = 0
    reversed_connections = 0
    for unit_id, raw_unit in (state.get("wire_units") or {}).items():
        unit = WireUnit.model_validate(raw_unit)
        unique_connections: list[WireConnection] = []
        seen: dict[str, WireConnection] = {}
        for raw_connection in unit.connections:
            connection = raw_connection if isinstance(raw_connection, WireConnection) else WireConnection.model_validate(raw_connection)
            connection, reversed_direction = _orient_allowed_start_terminal(connection)
            if connection is None:
                rejected_connections += 1
                continue
            if reversed_direction:
                reversed_connections += 1
            connection.current = _validated_breaker_current(
                connection.current,
                connection.current_basis,
                connection.current_source_text,
            )
            key = _connection_identity(unit_id, connection)
            if key in seen:
                _merge_connection_data(seen[key], connection)
            else:
                seen[key] = connection
                unique_connections.append(connection)
        unit.connections = unique_connections
        if not unique_connections:
            continue
        unit.source_pages = sorted({int(page) for page in unit.source_pages})
        unit.source_drawing_pages = _unique_strings(unit.source_drawing_pages)
        if any(connection.status not in {"complete", "resolved"} for connection in unique_connections):
            unit.status = "needs_review"
        normalized_units[unit_id] = unit.model_dump(mode="json", exclude_none=False)

        records: list[WireRecord] = []
        for connection in unique_connections:
            record = _wire_record_from_connection(
                unit,
                connection,
                page_by_number=page_by_number,
                terminal_strip_mapping=runtime.settings.terminal_strip_mapping,
            )
            record = normalize_wire_record(record, runtime.settings.terminal_strip_mapping)
            # X0-X5 is a downstream terminal-strip category. It is not part of
            # the current extraction contract, so the table column stays empty.
            record.terminal_strip = None
            _collect_consistency_warnings(record, runtime.settings.terminal_strip_mapping, runtime)
            records.append(record)
            connection_records.append(record.model_dump(mode="json", exclude_none=False))
        records_by_unit[unit_id] = records

    runtime.log(
        f"terminal_filter: rejected={rejected_connections} reversed={reversed_connections} "
        f"kept={sum(len(records) for records in records_by_unit.values())}"
    )

    table_rows_by_unit = {
        unit_id: [_record_to_table_row(record) for record in records]
        for unit_id, records in records_by_unit.items()
    }
    return {
        "wire_units": normalized_units,
        "wiring_records": records_by_unit,
        "connection_records": connection_records,
        "table_rows_by_unit": table_rows_by_unit,
    }


def _build_cross_page_tasks_node(state: GraphState, runtime: GraphRuntime) -> dict[str, Any]:
    """Resolve row-level references after stage two and create stage-three tasks."""
    page_by_number = {int(page["page_number"]): page for page in state.get("pages", [])}
    raw_units: dict[str, dict[str, Any]] = dict(state.get("wire_units") or {})
    records_by_unit = state.get("wiring_records") or {}
    tasks: list[dict[str, Any]] = []

    for unit_id, raw_unit in raw_units.items():
        unit = WireUnit.model_validate(raw_unit)
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
                _prepare_reference(
                    reference.model_dump(mode="json", exclude_none=False),
                    source_page=source_page,
                    drawing_index=state.get("drawing_index", {}),
                )
                for reference in connection.references
            ]
            raw_connection["references"] = prepared_references
            target_pages = list(
                dict.fromkeys(
                    int(reference["target_pdf_page"])
                    for reference in prepared_references
                    if reference.get("target_pdf_page") is not None
                    and int(reference["target_pdf_page"]) != source_pdf_page
                )
            )
            target_pages = target_pages[: max(0, int(runtime.settings.reference_target_limit))]
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
                if target_pages:
                    raw_connection["source_pdf_pages"] = sorted(
                        {source_pdf_page, *target_pages, *[int(value) for value in connection.source_pdf_pages]}
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
            source_record["references"] = prepared_references
            tasks.append(
                {
                    "task_id": connection_id,
                    "unit_id": unit_id,
                    "connection_id": connection_id,
                    "source_pdf_page": source_pdf_page,
                    "target_pdf_pages": target_pages,
                    "references": prepared_references,
                    "wire_number": unit.wire_number,
                    "line_number": connection.line_number,
                    "core_number": connection.core_number,
                    "source_record": source_record,
                    "needs_review": not bool(target_pages),
                }
            )
            if not target_pages:
                runtime.validation_warnings.append(
                    f"cross-page task {connection_id} has no resolved target PDF page"
                )

    diagnostics_dir = _diagnostics_dir(Path(state["output_path"]), runtime.output_mode)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (diagnostics_dir / "cross-page-tasks.json").write_text(
        json.dumps(tasks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (diagnostics_dir / "stage2-table.json").write_text(
        json.dumps(
            {"headers": TABLE_HEADERS, "rows_by_unit": state.get("table_rows_by_unit", {})},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    runtime.log(
        f"build_cross_page_tasks: rows={sum(len(rows) for rows in state.get('table_rows_by_unit', {}).values())} "
        f"cross_page_tasks={len(tasks)}"
    )
    return {"wire_units": raw_units, "cross_page_tasks": tasks}


def _cross_page_checkpoint_path(state: GraphState, runtime: GraphRuntime) -> Path:
    diagnostics_dir = _diagnostics_dir(Path(state["output_path"]), runtime.output_mode)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    return diagnostics_dir / "cross-page-checkpoint.json"


def _load_cross_page_checkpoint(path: Path, tasks: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        expected_ids = [str(task.get("task_id")) for task in tasks]
        if payload.get("task_ids") != expected_ids:
            return {}
        completed = payload.get("completed") or {}
        return completed if isinstance(completed, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("Ignoring invalid cross-page checkpoint %s: %s", path, exc)
        return {}


def _write_cross_page_checkpoint(
    path: Path,
    tasks: list[Mapping[str, Any]],
    completed: Mapping[str, Any],
    errors: Mapping[str, str],
) -> None:
    _write_json_atomic(
        path,
        {
            "version": 1,
            "task_ids": [str(task.get("task_id")) for task in tasks],
            "completed": dict(completed),
            "errors": dict(errors),
        },
    )


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
                int(task.get("source_pdf_page")),
                *[int(value) for value in raw_connection.get("source_pdf_pages", [])],
                *[int(value) for value in task.get("target_pdf_pages", [])],
            }
        )
    else:
        raw_connection["status"] = "needs_review"
        raw_connection["external_source_required"] = True
    for field in ("current", "current_basis", "current_source_text", "confidence", "source_note"):
        if result.get(field) not in (None, ""):
            raw_connection[field] = result[field]


async def _resolve_cross_page_node(state: GraphState, runtime: GraphRuntime) -> dict[str, Any]:
    """Run stage three for each row whose endpoint is still unresolved."""
    tasks = list(state.get("cross_page_tasks") or [])
    if not tasks:
        runtime.log("resolve_cross_page: no unresolved cross-page rows")
        return {"cross_page_results": {}, "wire_units": state.get("wire_units", {})}

    page_by_number = {int(page["page_number"]): page for page in state.get("pages", [])}
    checkpoint_path = _cross_page_checkpoint_path(state, runtime)
    completed = _load_cross_page_checkpoint(checkpoint_path, tasks)
    semaphore = asyncio.Semaphore(max(1, runtime.settings.concurrency))
    checkpoint_lock = asyncio.Lock()
    resolver = getattr(runtime.extraction_client, "resolve_cross_page", None)

    async def resolve_one(task: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        task_id = str(task.get("task_id"))
        if task_id in completed:
            runtime.log(f"resolve_cross_page: restored {task_id}")
            return task_id, dict(completed[task_id])
        target_pages = [int(value) for value in task.get("target_pdf_pages", [])]
        if not target_pages or not callable(resolver):
            result = {
                "task_id": task_id,
                "status": "needs_review",
                "needs_review": True,
                "end": None,
                "warnings": ["target page unavailable or cross-page resolver is not configured"],
            }
            completed[task_id] = result
            return task_id, result
        source_page = page_by_number.get(int(task["source_pdf_page"]))
        if source_page is None:
            result = {
                "task_id": task_id,
                "status": "needs_review",
                "needs_review": True,
                "end": None,
                "warnings": ["source page unavailable"],
            }
            completed[task_id] = result
            return task_id, result
        source_image = runtime.payload_for(source_page["image_path"])
        target_images = [
            runtime.payload_for(page_by_number[number]["image_path"])
            for number in target_pages
            if number in page_by_number
        ]
        if len(target_images) != len(target_pages):
            result = {
                "task_id": task_id,
                "status": "needs_review",
                "needs_review": True,
                "end": None,
                "warnings": ["one or more indexed target images are unavailable"],
            }
            completed[task_id] = result
            return task_id, result
        async with semaphore:
            try:
                pending = resolver(
                    source_image,
                    target_images,
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
                    f"resolve_cross_page: {task_id} targets={target_pages} "
                    f"status={result.get('status')} end={bool(result.get('end'))}"
                )
            except Exception as exc:
                result = {
                    "task_id": task_id,
                    "status": "needs_review",
                    "needs_review": True,
                    "end": None,
                    "warnings": [str(exc)],
                }
                assert runtime.extraction_errors is not None
                runtime.extraction_errors[task_id] = str(exc)
                runtime.validation_warnings.append(f"cross-page task {task_id} failed: {exc}")
            async with checkpoint_lock:
                completed[task_id] = result
                _write_cross_page_checkpoint(
                    checkpoint_path,
                    tasks,
                    completed,
                    runtime.extraction_errors or {},
                )
            return task_id, result

    pairs = await asyncio.gather(*(resolve_one(task) for task in tasks))
    results = {task_id: result for task_id, result in pairs}
    wire_units = dict(state.get("wire_units") or {})
    for task in tasks:
        result = results.get(str(task.get("task_id")))
        if result is not None:
            _apply_cross_page_completion(wire_units, task, result)
    _write_cross_page_checkpoint(checkpoint_path, tasks, results, runtime.extraction_errors or {})
    return {"cross_page_results": results, "wire_units": wire_units}


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("Ignoring invalid checkpoint %s: %s", path, exc)
        return {}


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _write_runtime_diagnostics(diagnostics_dir: Path, runtime: GraphRuntime) -> None:
    _write_json_atomic(diagnostics_dir / "errors.json", runtime.extraction_errors or {})
    _write_json_atomic(diagnostics_dir / "validation-warnings.json", runtime.validation_warnings or [])


def _write_page_scan_checkpoint(
    path: Path,
    *,
    processed_pages: list[int],
    page_scan_results: Mapping[str, Any],
) -> None:
    _write_json_atomic(
        path,
        {
            "version": 3,
            "processed_pages": processed_pages,
            "page_scan_results": dict(page_scan_results),
        },
    )


def _write_wire_units_checkpoint(path: Path, wire_units: Mapping[str, Any]) -> None:
    _write_json_atomic(path, {"version": 3, "wire_units": dict(wire_units)})


def _related_target_pages(
    source_pdf_page: int,
    drawing_index: Mapping[str, Any],
    *,
    limit: int,
) -> list[int]:
    """Resolve indexed cross-page targets that should accompany one scan call."""
    targets: list[int] = []
    page_lookup = drawing_index.get("page_lookup", {})
    for reference in drawing_index.get("references", []):
        if int(reference.get("source_pdf_page", -1)) != int(source_pdf_page):
            continue
        target_pdf_page = reference.get("target_pdf_page")
        if target_pdf_page is None:
            function = reference.get("target_function")
            page = reference.get("target_drawing_page") or reference.get("target_internal_page")
            if function and page is not None:
                target_pdf_page = page_lookup.get(f"{function}:{int(page)}")
        if target_pdf_page is not None and int(target_pdf_page) != int(source_pdf_page):
            targets.append(int(target_pdf_page))
    return list(dict.fromkeys(targets))[: max(0, int(limit))]


def _page_scan_context(
    page: PageMeta,
    drawing_index: Mapping[str, Any],
    *,
    related_pages: list[ImagePayload] | None = None,
) -> str:
    return json.dumps(
        {
            "pdf_page_number": page["page_number"],
            "drawing_function": page.get("function"),
            "drawing_page_number": page.get("internal_page"),
            "drawing_object_location": page.get("object_loc"),
            "known_references": [],
            "related_target_images": [],
        },
        ensure_ascii=False,
    )


def _find_or_create_unit_id(
    wire_units: Mapping[str, Mapping[str, Any]],
    unit: WireUnit,
    page: PageMeta,
    page_number: int,
    local_unit_index: int,
) -> str:
    wire_number = _text_value(unit.wire_number)
    project = _text_value(page.get("project_no")) or "unknown-project"
    prefix = _text_value(page.get("drawing_prefix")) or _text_value(page.get("function")) or "unknown-prefix"
    context = _unit_cable_context(unit)
    if wire_number:
        for existing_id, existing in wire_units.items():
            if existing.get("wire_number") != wire_number:
                continue
            return existing_id
    raw_key = (
        f"{project}|{wire_number or 'missing'}|{context or 'none'}"
        if wire_number
        else f"{project}|{prefix}|page:{page_number}|local:{local_unit_index}"
    )
    digest = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:8]
    slug = re.sub(r"[^0-9A-Za-z_-]+", "-", raw_key).strip("-").lower()[:70]
    return f"unit-{slug}-{digest}" if slug else f"unit-{digest}"


def _merge_scanned_unit(
    wire_units: dict[str, dict[str, Any]],
    unit: WireUnit,
    *,
    unit_id: str,
    page: PageMeta,
    page_number: int,
    unit_index: int,
) -> list[str]:
    context = _unit_cable_context(unit)
    existing = wire_units.setdefault(
        unit_id,
        {
            "unit_id": unit_id,
            "wire_number": unit.wire_number,
            "project_no": page.get("project_no"),
            "drawing_prefix": page.get("drawing_prefix") or page.get("function"),
            "attribute": unit.attribute,
            "model": unit.model,
            "spec": unit.spec,
            "length": unit.length,
            "cable_context": context,
            "unit_identity_confidence": "high" if unit.wire_number else "low",
            "connections": [],
            "source_pages": [],
            "source_drawing_pages": [],
            "status": unit.status,
            "confidence": unit.confidence,
            "_identity_project": page.get("project_no") or "unknown-project",
            "_identity_prefix": page.get("drawing_prefix") or page.get("function") or "unknown-prefix",
        },
    )
    for field in ("wire_number", "project_no", "drawing_prefix", "attribute", "model", "spec", "length", "confidence"):
        if existing.get(field) in (None, "") and getattr(unit, field) not in (None, ""):
            existing[field] = getattr(unit, field)
    if existing.get("current") in (None, "") and unit.current not in (None, ""):
        existing["current"] = unit.current
    existing["source_pages"] = sorted({int(value) for value in existing.get("source_pages", [])} | {page_number})
    label = _drawing_page_label(page)
    if label:
        existing["source_drawing_pages"] = _unique_strings([*existing.get("source_drawing_pages", []), label])
    connection_ids: list[str] = []
    for connection_index, raw_connection in enumerate(unit.connections, start=1):
        connection = raw_connection if isinstance(raw_connection, WireConnection) else WireConnection.model_validate(raw_connection)
        connection_id = f"{unit_id}:p{page_number}:c{connection_index}"
        connection_dict = connection.model_dump(mode="json", exclude_none=False)
        connection_dict["connection_id"] = connection_id
        connection_dict["unit_id"] = unit_id
        connection_dict["origin_pdf_page"] = page_number
        connection_dict["source_pdf_pages"] = sorted({page_number, *[int(value) for value in connection.source_pdf_pages]})
        connection_dict["source_drawing_pages"] = _unique_strings([
            *connection.source_drawing_pages,
            label,
        ])
        existing["connections"].append(connection_dict)
        connection_ids.append(connection_id)
        if connection.status not in {"complete", "resolved"}:
            existing["status"] = "needs_review"
    return connection_ids


def _prepare_reference(
    raw_reference: Mapping[str, Any],
    *,
    source_page: PageMeta,
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
        reference["target_drawing_page"] = reference.get("target_internal_page") or reference.get("target_page")
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


def _find_connection(unit: Mapping[str, Any], connection_id: str) -> dict[str, Any] | None:
    for connection in unit.get("connections", []):
        if str(connection.get("connection_id")) == connection_id:
            return connection
    return None


def _wire_record_from_connection(
    unit: WireUnit,
    connection: WireConnection,
    *,
    page_by_number: Mapping[int, PageMeta],
    terminal_strip_mapping: Mapping[str, str],
) -> WireRecord:
    start = connection.start or Endpoint()
    end = connection.end or Endpoint()
    source_pages = sorted({int(value) for value in (*unit.source_pages, *connection.source_pdf_pages)})
    source_drawing_pages = _unique_strings([*unit.source_drawing_pages, *connection.source_drawing_pages])
    source_images = [
        Path(page_by_number[page]["image_path"]).name
        for page in source_pages
        if page in page_by_number
    ]
    primary_page_number = connection.origin_pdf_page or (source_pages[0] if source_pages else None)
    primary_page = page_by_number.get(primary_page_number) if primary_page_number else None
    status = connection.status or unit.status
    external = bool(connection.external_source_required or status in {"external", "needs_review"} and end.terminal is None)
    source_type = "external" if external else "pdf"
    source_note = connection.source_note
    page_note = f"PDF第{','.join(str(page) for page in source_pages)}页"
    if source_drawing_pages:
        page_note += f"；图纸页{','.join(source_drawing_pages)}"
    source_note = f"{source_note}；{page_note}" if source_note else page_note
    return WireRecord(
        wire_number=unit.wire_number,
        attribute=unit.attribute,
        model=unit.model,
        spec=unit.spec,
        length=unit.length,
        current=connection.current,
        current_basis=connection.current_basis,
        current_source_text=connection.current_source_text,
        line_number=connection.line_number,
        core_number=connection.core_number,
        color=connection.color,
        start_part=start.part,
        start_location=start.location,
        start_device=start.device,
        start_name=start.name,
        start_terminal_board=start.terminal_board,
        start_terminal_code=start.terminal_code,
        start_terminal=start.terminal,
        end_part=end.part,
        end_location=end.location,
        end_device=end.device,
        end_name=end.name,
        end_terminal_board=end.terminal_board,
        end_terminal_code=end.terminal_code,
        end_terminal=end.terminal,
        terminal_strip=start.terminal_strip,
        start_terminal_strip=start.terminal_strip,
        end_terminal_strip=end.terminal_strip,
        remark=connection.remark,
        confidence=connection.confidence or unit.confidence,
        source_note=source_note,
        source_image=", ".join(source_images) or None,
        source_pages=source_pages,
        source_type=source_type,
        external_source_required=external,
        unit_id=unit.unit_id,
        connection_id=connection.connection_id,
        intermediate_points=[point.model_dump(mode="json", exclude_none=False) for point in connection.intermediate_points],
        references=[reference.model_dump(mode="json", exclude_none=False) for reference in connection.references],
        drawing_function=primary_page.get("function") if primary_page else None,
        drawing_page_number=primary_page.get("internal_page") if primary_page else None,
        pdf_page_number=primary_page_number,
        drawing_source_pages=source_drawing_pages,
        drawing_page=_drawing_page_label(primary_page) if primary_page else None,
        status=status,
        unit_identity_confidence=unit.unit_identity_confidence,
    )


def _connection_identity(unit_id: str, connection: WireConnection) -> str:
    start = _endpoint_signature(connection.start)
    end = _endpoint_signature(connection.end)
    points = tuple(_endpoint_signature(point) for point in connection.intermediate_points)
    if connection.line_number or connection.core_number or start != "" or end != "":
        return json.dumps([unit_id, connection.core_number, connection.line_number, start, end, points], ensure_ascii=False, sort_keys=True)
    return f"{unit_id}:{connection.connection_id or connection.local_connection_id or id(connection)}"


def _merge_connection_data(target: WireConnection, source: WireConnection) -> None:
    for field in (
        "core_number",
        "color",
        "line_number",
        "current",
        "current_basis",
        "current_source_text",
        "confidence",
        "remark",
        "source_note",
    ):
        if getattr(target, field) in (None, "") and getattr(source, field) not in (None, ""):
            setattr(target, field, getattr(source, field))
    if target.start is None:
        target.start = source.start
    elif source.start:
        target.start = _merge_endpoint(target.start, source.start)
    if target.end is None:
        target.end = source.end
    elif source.end:
        target.end = _merge_endpoint(target.end, source.end)
    target.source_pdf_pages = sorted({*target.source_pdf_pages, *source.source_pdf_pages})
    target.source_drawing_pages = _unique_strings([*target.source_drawing_pages, *source.source_drawing_pages])
    target.references.extend(
        reference
        for reference in source.references
        if reference.raw not in {item.raw for item in target.references}
    )
    target.external_source_required = target.external_source_required or source.external_source_required
    if target.status in {"complete", "resolved"} and source.status not in {"complete", "resolved"}:
        target.status = source.status


def _merge_endpoint(left: Endpoint, right: Endpoint) -> Endpoint:
    values = left.model_dump(mode="python", exclude_none=False)
    for key, value in right.model_dump(mode="python", exclude_none=False).items():
        if values.get(key) in (None, "") and value not in (None, ""):
            values[key] = value
    return Endpoint.model_validate(values)


def _endpoint_signature(endpoint: Endpoint | None) -> str:
    if endpoint is None:
        return ""
    return json.dumps(endpoint.model_dump(mode="json", exclude_none=False), ensure_ascii=False, sort_keys=True)


def _unit_cable_context(unit: WireUnit) -> str:
    return "|".join(
        str(value).strip()
        for value in (unit.attribute, unit.model, unit.spec, unit.length)
        if value not in (None, "")
    )


def _contexts_compatible(left: str, right: str) -> bool:
    if not left or not right:
        return True
    return left == right


def _drawing_page_label(page: Mapping[str, Any] | None) -> str | None:
    if not page:
        return None
    function = page.get("function")
    internal_page = page.get("internal_page")
    if function and internal_page is not None:
        return f"{function}/{internal_page}"
    if function:
        return str(function)
    return None


def _unique_strings(values: Iterable[Any]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value not in (None, "")))


def _text_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _project_and_prefix(text: str) -> tuple[str | None, str | None]:
    compact = " ".join(text.split())
    project_match = re.search(r"Project\.?\s*NR\s*[:.]?\s*([A-Z0-9_-]+)", compact, flags=re.IGNORECASE)
    prefix_match = re.search(r"\b(DQ[A-Z0-9_-]+)\b", compact, flags=re.IGNORECASE)
    return (
        project_match.group(1) if project_match else None,
        prefix_match.group(1).upper() if prefix_match else None,
    )


async def _segment_node(state: GraphState, runtime: GraphRuntime) -> dict[str, Any]:
    pages = state["pages"]
    if state.get("drawing_index") and state.get("extraction_batches"):
        indexed_segments = _segments_from_drawing_index(pages, state["drawing_index"], runtime)
        runtime.log(f"segment: deterministic drawing-index segments={indexed_segments}")
        return {"merge_decisions": [], "segments": indexed_segments}
    if len(pages) < 2:
        segments = _nonblank_segments(pages, [], runtime)
        runtime.log(f"segment: {len(pages)} page(s), no adjacent pair; segments={segments}")
        return {"merge_decisions": [], "segments": segments}

    semaphore = asyncio.Semaphore(max(1, runtime.settings.segment_concurrency))

    async def decide_pair(page_a: PageMeta, page_b: PageMeta) -> MergeDecision:
        try:
            async with semaphore:
                pending = runtime.segment_decider.decide(page_a, page_b)
                if inspect.isawaitable(pending):
                    pending = await pending
                decision = dict(pending)
        except Exception as exc:
            decision = degraded_decision(page_a["page_number"], page_b["page_number"], exc)
        if _is_blank_page(page_a, runtime) or _is_blank_page(page_b, runtime):
            decision["merge"] = False
            decision["needs_review"] = True
            decision["reason"] = f"{decision['reason']}；相邻页包含空白页，强制不合并"
        elif decision["merge"] and not _has_matching_project_and_prefix(decision):
            decision["merge"] = False
            decision["needs_review"] = True
            decision["reason"] = (
                f"{decision['reason']}；项目号或图号前缀不完整/不一致，强制不合并"
            )
        typed_decision: MergeDecision = decision  # type: ignore[assignment]
        runtime.log(
            "segment decision: "
            f"{typed_decision['a']}->{typed_decision['b']} "
            f"merge={typed_decision['merge']} "
            f"project=({typed_decision['project_no_a']},{typed_decision['project_no_b']}) "
            f"prefix=({typed_decision['drawing_prefix_a']},{typed_decision['drawing_prefix_b']}) "
            f"confidence={typed_decision['confidence']:.2f} "
            f"needs_review={typed_decision['needs_review']} "
            f"reason={typed_decision['reason']}"
        )
        return typed_decision

    decisions = list(
        await asyncio.gather(
            *(decide_pair(pages[index], pages[index + 1]) for index in range(len(pages) - 1))
        )
    )
    segments = _segments_from_decisions(pages, decisions, runtime)
    _mark_long_segments(decisions, segments, runtime.settings.max_segment_pages)
    for segment in segments:
        if len(segment) > runtime.settings.max_segment_pages:
            runtime.log(
                f"segment needs_review: pages={segment} exceeds max_segment_pages="
                f"{runtime.settings.max_segment_pages}"
            )
    runtime.log(f"segment: aggregated {len(decisions)} adjacent decision(s) into segments={segments}")
    return {"merge_decisions": decisions, "segments": segments}


async def _extract_wiring_node(state: GraphState, runtime: GraphRuntime) -> dict[str, dict[str, list[WireRecord]]]:
    batches = state.get("extraction_batches") or []
    if not batches:
        batches = [
            {"batch_id": f"wire-table-{index:03d}", "source_page": page_numbers[0],
             "target_pages": page_numbers[1:], "references": [], "needs_review": False}
            for index, page_numbers in enumerate(state.get("segments", []), start=1)
            if page_numbers
        ]
    if not batches:
        runtime.log("extract_wiring: no non-blank segments to extract")
        return {"wiring_records": {}}

    checkpoint_path = _extraction_checkpoint_path(state, runtime)
    completed = _load_extraction_checkpoint(checkpoint_path, batches)
    if completed:
        runtime.log(
            f"extract_wiring: restored {len(completed)}/{len(batches)} completed batch(es) from checkpoint"
        )
    assert runtime.extraction_errors is not None
    _write_extraction_checkpoint(checkpoint_path, batches, completed, runtime.extraction_errors)

    semaphore = asyncio.Semaphore(max(1, runtime.settings.concurrency))
    checkpoint_lock = asyncio.Lock()

    async def extract_one(index: int, batch: Mapping[str, Any]) -> tuple[str, list[WireRecord]]:
        segment_id = str(batch.get("batch_id") or f"wire-table-{index:03d}")
        if segment_id in completed:
            records = completed[segment_id]
            runtime.log(
                f"extract_wiring: {segment_id} restored from checkpoint records={len(records)}"
            )
            return segment_id, records
        async with semaphore:
            try:
                page_by_number = {page["page_number"]: page for page in state["pages"]}
                page_numbers = [int(batch["source_page"]), *[int(number) for number in batch.get("target_pages", [])]]
                page_numbers = list(dict.fromkeys(page_numbers))
                images = [runtime.payload_for(page_by_number[number]["image_path"]) for number in page_numbers]
                context_text = _batch_context(batch)
                try:
                    records = await runtime.extraction_client.extract_images(images, context_text=context_text)
                except TypeError as exc:
                    if "context_text" not in str(exc):
                        raise
                    records = await runtime.extraction_client.extract_images(images)
                attach_source_metadata(records, images)
                for record in records:
                    if batch.get("needs_review"):
                        record.external_source_required = True
                        record.source_type = "external" if not record.source_type else "mixed"
                        record.remark = _append_remark(record.remark, "cross-page reference needs review")
                async with checkpoint_lock:
                    completed[segment_id] = list(records)
                    runtime.extraction_errors.pop(segment_id, None)
                    _write_extraction_checkpoint(
                        checkpoint_path,
                        batches,
                        completed,
                        runtime.extraction_errors,
                    )
                runtime.log(
                    f"extract_wiring: {segment_id} pages={page_numbers} records={len(records)}"
                )
                return segment_id, records
            except Exception as exc:
                assert runtime.extraction_errors is not None
                async with checkpoint_lock:
                    runtime.extraction_errors[segment_id] = str(exc)
                    _write_extraction_checkpoint(
                        checkpoint_path,
                        batches,
                        completed,
                        runtime.extraction_errors,
                    )
                runtime.log(f"extract_wiring: {segment_id} failed: {exc}")
                return segment_id, []

    pairs = await asyncio.gather(*(extract_one(index, batch) for index, batch in enumerate(batches, start=1)))
    records_by_segment: dict[str, list[WireRecord]] = {
        f"wire-table-{index:03d}": [] for index, _ in enumerate(state.get("segments", []), start=1)
    }
    for batch, (batch_id, records) in zip(batches, pairs):
        source_page = int(batch.get("source_page", 0))
        segment_index = next(
            (index for index, pages in enumerate(state.get("segments", []), start=1) if source_page in pages),
            None,
        )
        if segment_index is None:
            segment_index = len(records_by_segment) + 1
        records_by_segment.setdefault(f"wire-table-{segment_index:03d}", []).extend(records)
    return {"wiring_records": records_by_segment}


def _assemble_table_node(state: GraphState, runtime: GraphRuntime) -> dict[str, Any]:
    """Build page-ordered frontend JSON and XLSX table outputs."""
    normalized: dict[str, list[WireRecord]] = {}
    rows_by_unit: dict[str, list[list[Any]]] = {}
    ordered_rows: list[tuple[tuple[str, int, int], int, list[Any]]] = []
    row_sequence = 0
    for unit_id, raw_records in state.get("wiring_records", {}).items():
        records: list[WireRecord] = []
        for raw_record in raw_records:
            record = raw_record if isinstance(raw_record, WireRecord) else WireRecord.model_validate(raw_record)
            _attach_drawing_page(record, state.get("drawing_index", {}))
            record = normalize_wire_record(record, runtime.settings.terminal_strip_mapping)
            record.terminal_strip = None
            _collect_consistency_warnings(record, runtime.settings.terminal_strip_mapping, runtime)
            records.append(record)
        normalized[unit_id] = records
        rows = [_record_to_table_row(record) for record in records]
        rows_by_unit[unit_id] = rows
        for record, row in zip(records, rows):
            ordered_rows.append((_table_record_page_sort_key(record), row_sequence, row))
            row_sequence += 1

    all_rows = [
        row
        for _, _, row in sorted(ordered_rows, key=lambda item: (item[0], item[1]))
    ]

    output_root = Path(state["output_path"])
    if runtime.output_mode == "library" or output_root.is_dir():
        output_root.mkdir(parents=True, exist_ok=True)
        table_payload = {"headers": TABLE_HEADERS, "rows": all_rows}
        (output_root / "table.json").write_text(
            json.dumps(table_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_root / "table.xlsx").write_bytes(
            table_to_xlsx_bytes(TABLE_HEADERS, all_rows)
        )
        groups_root = output_root / "groups"
        groups_root.mkdir(parents=True, exist_ok=True)
        for unit_id, records in normalized.items():
            group_dir = groups_root / unit_id
            group_dir.mkdir(parents=True, exist_ok=True)
            (group_dir / "records.json").write_text(
                json.dumps(
                    [record.model_dump(mode="json", exclude_none=False) for record in records],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (group_dir / "table.json").write_text(
                json.dumps(
                    {"headers": TABLE_HEADERS, "rows": rows_by_unit[unit_id]},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

    _write_agent_diagnostics(state, runtime)
    runtime.log(
        f"assemble_table: units={len(normalized)}, records={sum(len(items) for items in normalized.values())}"
    )
    return {
        "wiring_records": normalized,
        "table_headers": TABLE_HEADERS,
        "table_rows_by_unit": rows_by_unit,
    }


def _record_to_table_row(record: WireRecord) -> list[Any]:
    """Map one concrete connection to the exact 11-column frontend table."""
    drawing_page = _table_page_label(record)
    start_terminal = _table_terminal(record.start_device, record.start_terminal)
    end_terminal = _table_terminal(record.end_device, record.end_terminal)
    remark = record.remark or record.source_note
    return [
        drawing_page,
        record.line_number or record.wire_number,
        None,
        record.start_location or record.start_device,
        record.start_name or record.start_part,
        start_terminal,
        record.end_location or record.end_device,
        record.end_name or record.end_part,
        end_terminal,
        record.current,
        remark,
    ]


def _orient_allowed_start_terminal(
    connection: WireConnection,
) -> tuple[WireConnection | None, bool]:
    start_code = _endpoint_allowed_start_code(connection.start)
    end_code = _endpoint_allowed_start_code(connection.end)
    if start_code:
        return connection, False
    if end_code and connection.end is not None:
        connection.start, connection.end = connection.end, connection.start
        return connection, True
    return None, False


def _endpoint_allowed_start_code(endpoint: Endpoint | None) -> str | None:
    if endpoint is None:
        return None
    return allowed_start_terminal_code(
        endpoint.terminal_board,
        endpoint.device,
        endpoint.terminal,
    )


def _validated_breaker_current(
    value: Any,
    basis: str | None,
    source_text: str | None,
) -> str | None:
    if value in (None, "") or not basis or not source_text:
        return None
    normalized_basis = re.sub(r"[^A-Z]", "", str(basis).upper())
    if normalized_basis not in {"IR", "IN", "IE"}:
        return None
    evidence = str(source_text).strip()
    if not re.search(rf"(?i)\b{normalized_basis}\b\s*[:=]", evidence):
        return None
    current = str(value).strip().replace(" ", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(mA|A|kA)", current, flags=re.IGNORECASE)
    if not match:
        return None
    unit = match.group(2)
    canonical_unit = "mA" if unit.lower() == "ma" else "kA" if unit.lower() == "ka" else "A"
    return f"{match.group(1)}{canonical_unit}"


def _table_record_page_sort_key(record: WireRecord) -> tuple[str, int, int]:
    function = str(record.drawing_function or "~").strip().upper()
    drawing_page = int(record.drawing_page_number) if record.drawing_page_number is not None else 10**9
    source_page = min((int(value) for value in record.source_pages), default=10**9)
    return function, drawing_page, source_page


def _table_page_label(record: WireRecord) -> str | None:
    if record.drawing_function and record.drawing_page_number is not None:
        function = str(record.drawing_function).replace(".", "")
        return f"{function}{int(record.drawing_page_number):02d}"
    if record.drawing_page:
        return str(record.drawing_page).replace("/", "")
    return None


def _table_terminal(device: str | None, terminal: Any) -> Any:
    if terminal in (None, ""):
        return None
    value = str(terminal).strip()
    if value in {"*", "PE"} or ":" in value:
        return value
    return f"{device.lstrip('-')}:{value}" if device else value


def _assemble_xlsx_node(state: GraphState, runtime: GraphRuntime) -> dict[str, Any]:
    normalized: dict[str, list[WireRecord]] = {}
    for segment_id, raw_records in state["wiring_records"].items():
        segment_records: list[WireRecord] = []
        prepared_records: list[WireRecord] = []
        for raw_record in raw_records:
            record = raw_record if isinstance(raw_record, WireRecord) else WireRecord.model_validate(raw_record)
            _attach_drawing_page(record, state.get("drawing_index", {}))
            prepared_records.append(record)
        records_to_write = prepared_records if state.get("wire_units") else merge_cross_page_records(prepared_records)
        for record in records_to_write:
            _collect_consistency_warnings(record, runtime.settings.terminal_strip_mapping, runtime)
            segment_records.append(normalize_wire_record(record, runtime.settings.terminal_strip_mapping))
        normalized[segment_id] = segment_records

    output_path = Path(state["output_path"])
    directory_output = runtime.output_mode == "library" or output_path.is_dir()
    if directory_output:
        output_root = Path(state["output_path"])
        groups_root = output_root / "groups"
        groups_root.mkdir(parents=True, exist_ok=True)
        page_by_number = {page["page_number"]: page for page in state["pages"]}
        for segment_id, records in normalized.items():
            group_dir = groups_root / segment_id
            group_dir.mkdir(parents=True, exist_ok=True)
            (group_dir / "records.json").write_text(
                json.dumps([record.model_dump(mode="json", exclude_none=False) for record in records], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (group_dir / "wiring-table.xlsx").write_bytes(
                records_to_xlsx_bytes(
                    records,
                    sheet_title=segment_id,
                    terminal_strip_mapping=runtime.settings.terminal_strip_mapping,
                )
            )
            try:
                template_path = _template_path(runtime.settings)
                (group_dir / "wiring-table-import.xls").write_bytes(
                    records_to_template_xls_bytes(
                        records,
                        template_path=template_path,
                        terminal_strip_mapping=runtime.settings.terminal_strip_mapping,
                    )
                )
                (group_dir / "wiring-table-import.xlsx").write_bytes(
                    records_to_template_xlsx_bytes(
                        records,
                        template_path=template_path,
                        terminal_strip_mapping=runtime.settings.terminal_strip_mapping,
                    )
                )
            except (FileNotFoundError, RuntimeError) as exc:
                _warning(runtime, f"{segment_id}: strict XLS export unavailable: {exc}")
            segment_pages_dir = group_dir / "pages"
            segment_pages_dir.mkdir(parents=True, exist_ok=True)
            segment_pages = _segment_pages(state, segment_id, page_by_number)
            for page_number, source_page in segment_pages:
                source_path = Path(source_page["image_path"])
                if source_path.is_file():
                    shutil.copy2(source_path, segment_pages_dir / source_path.name)
            (group_dir / "source-pages.json").write_text(
                json.dumps(
                    [
                        {"page_number": page_number, "filename": Path(source_page["image_path"]).name}
                        for page_number, source_page in segment_pages
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        if runtime.output_mode in {"library", "single_xlsx"}:
            output_root.mkdir(parents=True, exist_ok=True)
            (output_root / "wiring-table.xlsx").write_bytes(
                records_by_segment_to_xlsx_bytes(
                    normalized,
                    terminal_strip_mapping=runtime.settings.terminal_strip_mapping,
                )
            )
            try:
                template_path = _template_path(runtime.settings)
                all_records = [record for records in normalized.values() for record in records]
                (output_root / "wiring-table-import.xls").write_bytes(
                    records_to_template_xls_bytes(
                        all_records,
                        template_path=template_path,
                        terminal_strip_mapping=runtime.settings.terminal_strip_mapping,
                    )
                )
                (output_root / "wiring-table-import.xlsx").write_bytes(
                    records_to_template_xlsx_bytes(
                        all_records,
                        template_path=template_path,
                        terminal_strip_mapping=runtime.settings.terminal_strip_mapping,
                    )
                )
            except (FileNotFoundError, RuntimeError) as exc:
                _warning(runtime, f"strict XLS export unavailable: {exc}")
    else:
        output_file = Path(state["output_path"])
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_bytes(
            records_by_segment_to_xlsx_bytes(
                normalized,
                terminal_strip_mapping=runtime.settings.terminal_strip_mapping,
            )
        )
        try:
            template_path = _template_path(runtime.settings)
            all_records = [record for records in normalized.values() for record in records]
            output_file.with_name(f"{output_file.stem}-import.xls").write_bytes(
                records_to_template_xls_bytes(
                    all_records,
                    template_path=template_path,
                    terminal_strip_mapping=runtime.settings.terminal_strip_mapping,
                )
            )
            output_file.with_name(f"{output_file.stem}-import.xlsx").write_bytes(
                records_to_template_xlsx_bytes(
                    all_records,
                    template_path=template_path,
                    terminal_strip_mapping=runtime.settings.terminal_strip_mapping,
                )
            )
        except (FileNotFoundError, RuntimeError) as exc:
            _warning(runtime, f"strict XLS export unavailable: {exc}")

    _write_agent_diagnostics(state, runtime)
    runtime.log(
        f"assemble_xlsx: mode={runtime.output_mode}, segments={len(normalized)}, "
        f"records={sum(len(records) for records in normalized.values())}"
    )
    return {"wiring_records": normalized}


def _write_agent_diagnostics(
    state: GraphState,
    runtime: GraphRuntime,
) -> None:
    output_path = Path(state["output_path"])
    diagnostics_dir = _diagnostics_dir(output_path, runtime.output_mode)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (diagnostics_dir / "merge_decisions.json").write_text(
        json.dumps(state["merge_decisions"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (diagnostics_dir / "segments.json").write_text(
        json.dumps(state["segments"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (diagnostics_dir / "extraction_batches.json").write_text(
        json.dumps(state.get("extraction_batches", []), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (diagnostics_dir / "drawing_index.json").write_text(
        json.dumps(state.get("drawing_index", {}), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (diagnostics_dir / "errors.json").write_text(
        json.dumps(runtime.extraction_errors or {}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (diagnostics_dir / "validation-warnings.json").write_text(
        json.dumps(runtime.validation_warnings or [], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (diagnostics_dir / "page-scan-results.json").write_text(
        json.dumps(state.get("page_scan_results", {}), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (diagnostics_dir / "wire-units.json").write_text(
        json.dumps(state.get("wire_units", {}), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (diagnostics_dir / "connection-records.json").write_text(
        json.dumps(state.get("connection_records", []), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (diagnostics_dir / "cross-page-tasks.json").write_text(
        json.dumps(state.get("cross_page_tasks", []), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (diagnostics_dir / "cross-page-results.json").write_text(
        json.dumps(state.get("cross_page_results", {}), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    stage2_table_path = diagnostics_dir / "stage2-table.json"
    if not stage2_table_path.is_file():
        stage2_table_path.write_text(
            json.dumps(
                {
                    "headers": state.get("table_headers", TABLE_HEADERS),
                    "rows_by_unit": state.get("table_rows_by_unit", {}),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    (diagnostics_dir / "plant-function-groups.json").write_text(
        json.dumps(state.get("plant_function_groups", {}), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (diagnostics_dir / "table.json").write_text(
        json.dumps(
            {
                "headers": state.get("table_headers", TABLE_HEADERS),
                "rows_by_unit": state.get("table_rows_by_unit", {}),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _segment_pages(
    state: GraphState,
    segment_id: str,
    page_by_number: Mapping[int, PageMeta],
) -> list[tuple[int, PageMeta]]:
    unit = (state.get("wire_units") or {}).get(segment_id)
    if unit is not None:
        page_numbers = [int(number) for number in unit.get("source_pages", [])]
        return [(number, page_by_number[number]) for number in page_numbers if number in page_by_number]
    try:
        segment_index = int(segment_id.rsplit("-", 1)[-1]) - 1
        page_numbers = state["segments"][segment_index]
    except (ValueError, IndexError):
        return []
    return [(number, page_by_number[number]) for number in page_numbers if number in page_by_number]


def _segments_from_drawing_index(
    pages: list[PageMeta], drawing_index: Mapping[str, Any], runtime: GraphRuntime
) -> list[list[int]]:
    """Group contiguous nonblank pages by Plant Function and split large groups."""
    groups: list[list[int]] = []
    current_function: str | None = None
    current_pages: list[int] = []
    for page in pages:
        if _is_blank_page(page, runtime):
            if current_pages:
                groups.append(current_pages)
                current_pages = []
                current_function = None
            continue
        if page.get("is_non_wiring"):
            if current_pages:
                groups.append(current_pages)
                current_pages = []
                current_function = None
            continue
        function = page.get("function") or "unknown"
        number = int(page["page_number"])
        if current_pages and function != current_function:
            groups.append(current_pages)
            current_pages = []
        current_function = function
        current_pages.append(number)
    if current_pages:
        groups.append(current_pages)
    result: list[list[int]] = []
    limit = max(1, runtime.settings.max_segment_pages)
    for numbers in groups:
        numbers = sorted(numbers)
        result.extend(numbers[offset:offset + limit] for offset in range(0, len(numbers), limit))
    return sorted(result, key=lambda values: values[0])


def _append_remark(current: str | None, message: str) -> str:
    return f"{current}; {message}" if current else message


def _attach_drawing_page(record: WireRecord, drawing_index: Mapping[str, Any]) -> None:
    if record.drawing_page or not record.source_pages:
        return
    pages = {int(page.get("pdf_page")): page for page in drawing_index.get("pages", [])}
    for pdf_page in sorted(record.source_pages):
        page = pages.get(int(pdf_page))
        if page and page.get("function") and page.get("internal_page") is not None:
            function = str(page["function"]).replace(".", "")
            record.drawing_page = f"{function}{int(page['internal_page']):02d}"
            return


def _batch_context(batch: Mapping[str, Any]) -> str:
    references = batch.get("references") or []
    if not references:
        return "无已解析的跨页引用；只依据输入图像输出可确认端点。"
    lines = []
    for reference in references:
        lines.append(
            f"source_pdf_page={reference.get('source_pdf_page')}; raw={reference.get('raw')}; "
            f"target_function={reference.get('target_function')}; target_internal_page={reference.get('target_internal_page')}; "
            f"target_pdf_page={reference.get('target_pdf_page', 'see target image')}; external={reference.get('external', False)}"
        )
    return "\n".join(lines)


def _segments_from_decisions(
    pages: list[PageMeta],
    decisions: Iterable[MergeDecision],
    runtime: GraphRuntime,
) -> list[list[int]]:
    parent = {page["page_number"]: page["page_number"] for page in pages}

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for decision in decisions:
        if decision["merge"] and decision["a"] in parent and decision["b"] in parent:
            union(decision["a"], decision["b"])

    components: dict[int, list[int]] = {}
    for page in pages:
        number = page["page_number"]
        if _is_blank_page(page, runtime):
            continue
        components.setdefault(find(number), []).append(number)
    return [sorted(numbers) for numbers in sorted(components.values(), key=lambda values: values[0])]


def _nonblank_segments(
    pages: list[PageMeta],
    decisions: list[MergeDecision],
    runtime: GraphRuntime,
) -> list[list[int]]:
    if not pages:
        return []
    if decisions:
        return _segments_from_decisions(pages, decisions, runtime)
    return [
        [page["page_number"]]
        for page in pages
        if not _is_blank_page(page, runtime)
    ]


def _is_blank_page(page: PageMeta, runtime: GraphRuntime) -> bool:
    try:
        return runtime.payload_for(page["image_path"]).blank
    except FileNotFoundError:
        return False


def _has_matching_project_and_prefix(decision: MergeDecision) -> bool:
    return bool(
        decision["project_no_a"]
        and decision["project_no_b"]
        and decision["drawing_prefix_a"]
        and decision["drawing_prefix_b"]
        and decision["project_no_a"] == decision["project_no_b"]
        and decision["drawing_prefix_a"] == decision["drawing_prefix_b"]
    )


def _mark_long_segments(
    decisions: list[MergeDecision],
    segments: list[list[int]],
    max_segment_pages: int,
) -> None:
    for segment in segments:
        if len(segment) <= max_segment_pages:
            continue
        page_set = set(segment)
        for decision in decisions:
            if decision["a"] in page_set and decision["b"] in page_set:
                decision["needs_review"] = True
                decision["reason"] = (
                    f"{decision['reason']}；连续段共 {len(segment)} 页，"
                    f"超过配置上限 {max_segment_pages} 页"
                )


def _collect_consistency_warnings(
    record: WireRecord,
    mapping: Mapping[str, str],
    runtime: GraphRuntime,
) -> None:
    line_number = (record.line_number or "").strip().upper()
    if line_number == "SPARE":
        if record.start_terminal not in (None, "*") or record.end_terminal not in (None, "*"):
            _warning(runtime, "SPARE record has a non-* terminal")
        return
    if line_number == "PE":
        if record.start_terminal not in (None, "PE") or record.end_terminal not in (None, "PE"):
            _warning(runtime, "PE record has a non-PE terminal")
        return
    for field_name in ("terminal_strip", "start_terminal_strip", "end_terminal_strip"):
        value = getattr(record, field_name)
        if value not in (None, "") and normalize_terminal_strip(value, mapping) is None:
            _warning(
                runtime,
                f"{record.source_image or 'record'} {field_name}={value!r} is outside the allowed "
                f"terminal strips: {', '.join(ALLOWED_TERMINAL_STRIPS)}",
            )

    expected_strip = terminal_strip_for_device(record.start_device, mapping)
    if expected_strip and record.terminal_strip not in (None, expected_strip):
        _warning(
            runtime,
            f"{record.source_image or 'record'} start device {record.start_device} "
            f"maps to {expected_strip}, got {record.terminal_strip}",
        )
    if record.start_device and record.start_terminal is None:
        _warning(runtime, f"{record.source_image or 'record'} has a start device but no start terminal")


def _warning(runtime: GraphRuntime, message: str) -> None:
    assert runtime.validation_warnings is not None
    runtime.validation_warnings.append(message)
    logger.warning("assemble_xlsx validation: %s", message)


def _template_path(settings: Settings) -> Path:
    root = Path(__file__).resolve().parents[3]
    if settings.import_template_path:
        configured = settings.import_template_path
        configured_candidates = [configured]
        if not configured.is_absolute():
            configured_candidates.extend(
                [root / configured, root / "backend" / configured]
            )
        for candidate in configured_candidates:
            if candidate.is_file():
                return candidate
    candidates = [
        root / "case" / "放线表导入格式(1).xls",
        root / "test_case" / "放线表导入格式(1).xls",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("未找到放线表导入格式(1).xls")
