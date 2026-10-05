from __future__ import annotations

import asyncio
import inspect
import json
import logging
import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from ..core.config import Settings
from ..schemas.wire import WireRecord
from ..services.excel_writer import records_by_segment_to_xlsx_bytes, records_to_xlsx_bytes
from ..services.file_inputs import InputFileError, path_to_image_payloads
from ..services.prompt_loader import load_segment_few_shot_examples
from ..services.vlm_client import (
    ImagePayload,
    VLMClient,
    build_segment_few_shot_messages,
    normalize_wire_record,
    attach_source_metadata,
)
from .segment_decider import SegmentDecider, VLMSegmentDecider, degraded_decision
from .state import GraphState, MergeDecision, PageMeta


logger = logging.getLogger(__name__)


ProgressCallback = Callable[[str], None]


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

    graph = StateGraph(GraphState)
    graph.add_node("pdf_to_images", lambda state: _pdf_to_images_node(state, runtime))
    graph.add_node("segment", segment_node)
    graph.add_node("extract_wiring", extract_node)
    graph.add_node("assemble_xlsx", lambda state: _assemble_xlsx_node(state, runtime))
    graph.add_edge(START, "pdf_to_images")
    graph.add_edge("pdf_to_images", "segment")
    graph.add_edge("segment", "extract_wiring")
    graph.add_edge("extract_wiring", "assemble_xlsx")
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
    segment_prefix_messages = _load_segment_prefix_messages(settings)
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


def _pdf_to_images_node(state: GraphState, runtime: GraphRuntime) -> dict[str, list[PageMeta]]:
    output_root = Path(state["output_path"])
    if runtime.output_mode == "library":
        page_dir = output_root / "pages"
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
        normalized_payload = replace(payload, name=path.name)
        runtime.payload_by_path[str(path.resolve())] = normalized_payload
        runtime.payload_by_path[str(path)] = normalized_payload
        pages.append({"page_number": index, "image_path": str(path.resolve())})

    blank_pages = [index + 1 for index, payload in enumerate(payloads) if payload.blank]
    runtime.log(
        f"pdf_to_images: rendered {len(pages)} page(s) at approximately "
        f"{runtime.settings.pdf_render_dpi} DPI; blank pages={blank_pages or 'none'}"
    )
    return {"pages": pages}


async def _segment_node(state: GraphState, runtime: GraphRuntime) -> dict[str, Any]:
    pages = state["pages"]
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
    segments = state["segments"]
    if not segments:
        runtime.log("extract_wiring: no non-blank segments to extract")
        return {"wiring_records": {}}

    semaphore = asyncio.Semaphore(max(1, runtime.settings.concurrency))

    async def extract_one(index: int, page_numbers: list[int]) -> tuple[str, list[WireRecord]]:
        segment_id = f"wire-table-{index:03d}"
        async with semaphore:
            try:
                page_by_number = {page["page_number"]: page for page in state["pages"]}
                images = [runtime.payload_for(page_by_number[number]["image_path"]) for number in page_numbers]
                records = await runtime.extraction_client.extract_images(images)
                attach_source_metadata(records, images)
                runtime.log(
                    f"extract_wiring: {segment_id} pages={page_numbers} records={len(records)}"
                )
                return segment_id, records
            except Exception as exc:
                assert runtime.extraction_errors is not None
                runtime.extraction_errors[segment_id] = str(exc)
                runtime.log(f"extract_wiring: {segment_id} failed: {exc}")
                return segment_id, []

    pairs = await asyncio.gather(
        *(extract_one(index, page_numbers) for index, page_numbers in enumerate(segments, start=1))
    )
    return {"wiring_records": {segment_id: records for segment_id, records in pairs}}


def _assemble_xlsx_node(state: GraphState, runtime: GraphRuntime) -> dict[str, Any]:
    normalized: dict[str, list[WireRecord]] = {}
    for segment_id, raw_records in state["wiring_records"].items():
        segment_records: list[WireRecord] = []
        for raw_record in raw_records:
            record = raw_record if isinstance(raw_record, WireRecord) else WireRecord.model_validate(raw_record)
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
        if runtime.output_mode == "single_xlsx":
            output_root.mkdir(parents=True, exist_ok=True)
            (output_root / "wiring-table.xlsx").write_bytes(
                records_by_segment_to_xlsx_bytes(
                    normalized,
                    terminal_strip_mapping=runtime.settings.terminal_strip_mapping,
                )
            )
    else:
        output_file = Path(state["output_path"])
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_bytes(
            records_by_segment_to_xlsx_bytes(
                normalized,
                terminal_strip_mapping=runtime.settings.terminal_strip_mapping,
            )
        )

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
    diagnostics_dir = (
        output_path / "agent"
        if runtime.output_mode == "library" or output_path.is_dir()
        else output_path.parent / f"{output_path.stem}.agent"
    )
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (diagnostics_dir / "merge_decisions.json").write_text(
        json.dumps(state["merge_decisions"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (diagnostics_dir / "segments.json").write_text(
        json.dumps(state["segments"], ensure_ascii=False, indent=2),
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


def _segment_pages(
    state: GraphState,
    segment_id: str,
    page_by_number: Mapping[int, PageMeta],
) -> list[tuple[int, PageMeta]]:
    try:
        segment_index = int(segment_id.rsplit("-", 1)[-1]) - 1
        page_numbers = state["segments"][segment_index]
    except (ValueError, IndexError):
        return []
    return [(number, page_by_number[number]) for number in page_numbers if number in page_by_number]


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
    device = (record.start_device or "").lstrip("-").upper()
    expected_strip = {str(key).lstrip("-").upper(): value for key, value in mapping.items()}.get(device)
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
