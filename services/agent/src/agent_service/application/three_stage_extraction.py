from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..agents.cross_page_resolver import CrossPageResolverAgent
from ..agents.page_classifier import PageClassifierAgent
from ..agents.page_scanner import PageScannerAgent
from ..config import AgentSettings
from ..domain.models.extraction import ExtractionExecutionResult
from ..domain.models.extraction_stages import (
    CrossPageCompletionRequest,
    DrawingPageInput,
    PageClassificationRequest,
    PageScanRequest,
)
from ..domain.models.profiles import ProfileBinding
from ..domain.models.wiring import (
    CrossPageCompletion,
    PageClassification,
    PageScanResult,
)
from ..graphs.document_extraction.workflow import run_document_extraction
from ..graphs.extraction import (
    run_cross_page_completion,
    run_page_classification,
    run_page_scan,
)
from ..harness.stores import CancellationToken
from ..profiles.extraction_policy import default_extraction_policies
from .document_extraction.settings import Settings as DocumentExtractionSettings
from .extraction_stage_factory import build_extraction_stage_dispatcher

ProgressCallback = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class ThreeStageRunResult:
    """Filesystem result of one test run; no database side effects are performed."""

    execution: ExtractionExecutionResult
    output_dir: Path
    stage_1_dir: Path
    stage_2_dir: Path
    stage_3_dir: Path
    final_xlsx: Path


_STAGE_FILES: dict[str, tuple[str, ...]] = {
    "01_page_classification": (
        "page-classifications.json",
        "drawing_index.json",
        "plant-function-groups.json",
    ),
    "02_page_scan": (
        "page-scan-results.json",
        "wire-units.json",
        "stage2-table.json",
        "page-scan-checkpoint.json",
        "wire-units-checkpoint.json",
    ),
    "03_cross_page_completion": (
        "cross-page-tasks.json",
        "cross-page-results.json",
        "cross-page-checkpoint.json",
        "table.json",
    ),
}


class ExtractionStageGraphClient:
    """Bridge the migrated document workflow to the three Agent stage subgraphs."""

    def __init__(
        self,
        *,
        run_id: str,
        project_id: str,
        profile: ProfileBinding,
        stages: Any,
        output_dir: Path,
        cancellation: CancellationToken | None = None,
    ) -> None:
        self._run_id = run_id
        self._project_id = project_id
        self._profile = profile
        self._output_dir = output_dir
        self._cancellation = cancellation
        self._classified_page_paths: dict[int, Path] = {}
        self._classifier = PageClassifierAgent(stages=stages)
        self._scanner = PageScannerAgent(stages=stages)
        self._resolver = CrossPageResolverAgent(stages=stages)

    async def classify_page(self, image: Any, *, context_text: str = "") -> Any:
        self._raise_if_cancelled()
        result = await run_page_classification(
            agent=self._classifier,
            request=PageClassificationRequest(
                run_id=self._run_id,
                project_id=self._project_id,
                profile=self._profile,
                page=self._page(image),
                known_context=context_text,
            ),
        )
        return PageClassification(
            plant_function=result.plant_function,
            page_number=result.drawing_page_number,
            blank=result.blank,
            non_wiring=result.non_wiring,
            confidence=result.confidence,
            needs_review=result.needs_review,
            reason=result.reason,
        )

    async def scan_page(self, image: Any, *, page_context: str = "") -> Any:
        self._raise_if_cancelled()
        result = await run_page_scan(
            agent=self._scanner,
            request=PageScanRequest(
                run_id=self._run_id,
                project_id=self._project_id,
                profile=self._profile,
                page=self._page(image),
                page_context=page_context,
            ),
        )
        return PageScanResult.model_validate(
            result.model_dump(mode="python", exclude={"run_id", "project_id", "profile"})
        )

    async def resolve_cross_page(
        self,
        target_image: Any,
        *,
        task_context: str = "",
    ) -> Any:
        self._raise_if_cancelled()
        result = await run_cross_page_completion(
            agent=self._resolver,
            request=CrossPageCompletionRequest(
                run_id=self._run_id,
                project_id=self._project_id,
                profile=self._profile,
                task_id=_task_id(task_context),
                target_page=self._page(target_image),
                task_context=task_context or "indexed cross-page reference",
            ),
        )
        return CrossPageCompletion.model_validate(
            result.model_dump(mode="python", exclude={"run_id", "project_id", "profile"})
        )

    def _page(self, image: Any) -> DrawingPageInput:
        name = Path(str(getattr(image, "name", ""))).name
        page_number = int(getattr(image, "page_number", 0) or 0)
        if page_number < 1:
            raise ValueError(f"Image {name!r} has no valid physical PDF page number.")
        cached_path = self._classified_page_paths.get(page_number)
        if cached_path is not None and cached_path.is_file():
            return DrawingPageInput(
                pdf_page_number=page_number,
                image_path=cached_path,
                blank=bool(getattr(image, "blank", False)),
            )
        candidates = (
            self._output_dir / "pages" / ".incoming" / name,
            self._output_dir / "pages" / name,
        )
        image_path = next((path for path in candidates if path.is_file()), None)
        if image_path is None:
            image_path = self._classified_page_path(page_number)
        if image_path is None:
            content = getattr(image, "content", b"")
            if not name or not content:
                raise FileNotFoundError(
                    f"Rendered image {name!r} is unavailable in {self._output_dir / 'pages'}"
                )
            image_path = candidates[0]
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(content)
        if ".incoming" not in image_path.parts:
            self._classified_page_paths[page_number] = image_path
        return DrawingPageInput(
            pdf_page_number=page_number,
            image_path=image_path,
            blank=bool(getattr(image, "blank", False)),
        )

    def _raise_if_cancelled(self) -> None:
        if self._cancellation is not None:
            self._cancellation.raise_if_cancelled()

    def _classified_page_path(self, page_number: int) -> Path | None:
        index_path = self._output_dir / "agent" / "drawing_index.json"
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        page = next(
            (item for item in index.get("pages", []) if int(item.get("pdf_page", -1)) == page_number),
            None,
        )
        if page is None:
            return None
        function = str(page.get("function") or "UNKNOWN").upper().lstrip("=")
        function = "".join(char if char.isalnum() or char in ".-_" else "_" for char in function)
        internal_page = page.get("internal_page")
        label = str(int(internal_page)) if internal_page is not None else f"pdf_{page_number:04d}"
        folder = self._output_dir / "pages" / (function or "UNKNOWN")
        matches = (
            folder / f"{label}.png",
            folder / f"{label}__pdf_{page_number:04d}.png",
        )
        return next((path for path in matches if path.is_file()), None)


def _task_id(task_context: str) -> str:
    try:
        payload = json.loads(task_context)
    except (json.JSONDecodeError, TypeError):
        payload = {}
    if isinstance(payload, dict) and payload.get("task_id"):
        return str(payload["task_id"])
    return "cross-page-task"


async def run_three_stage_extraction(
    *,
    pdf_path: Path,
    output_dir: Path,
    profile: ProfileBinding,
    settings: AgentSettings,
    run_id: str,
    project_id: str,
    max_pdf_pages: int = 0,
    progress: ProgressCallback | None = None,
    cancellation: CancellationToken | None = None,
) -> ThreeStageRunResult:
    """Run the document workflow through the Agent's three extraction subgraphs.

    PDF rendering, drawing indexing, task construction, deterministic validation,
    and workbook assembly live in the document Graph and infrastructure. Every VLM call
    is routed through the Agent subgraphs and the bound ZH Profile adapter.
    """

    pdf_path, output_dir = await asyncio.gather(
        asyncio.to_thread(pdf_path.resolve),
        asyncio.to_thread(output_dir.resolve),
    )
    if not await asyncio.to_thread(pdf_path.is_file):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    output_dir.mkdir(parents=True, exist_ok=True)

    if cancellation is not None:
        cancellation.raise_if_cancelled()

    def report(message: str) -> None:
        if progress is not None:
            progress(message)

    workflow_settings = DocumentExtractionSettings.from_agent(settings, max_pdf_pages=max_pdf_pages)
    policy = default_extraction_policies().resolve(profile.adapter)
    stage_dispatcher = build_extraction_stage_dispatcher(settings)
    graph_client = ExtractionStageGraphClient(
        run_id=run_id,
        project_id=project_id,
        profile=profile,
        stages=stage_dispatcher,
        output_dir=output_dir,
        cancellation=cancellation,
    )

    report("starting PDF rendering and three-stage LangGraph extraction")
    graph_result = await run_document_extraction(
        pdf_path=pdf_path,
        output_path=output_dir,
        settings=workflow_settings,
        progress=report,
        output_mode=workflow_settings.output_mode,
        extraction_client=graph_client,
        policy=policy,
    )
    execution = ExtractionExecutionResult(
        run_id=run_id,
        state=dict(graph_result.state),
        extraction_errors=dict(graph_result.extraction_errors),
        validation_warnings=list(graph_result.validation_warnings),
        adapter="langgraph_three_stage",
    )

    agent_dir = output_dir / "agent"
    stage_1_dir = output_dir / "01_page_classification"
    stage_2_dir = output_dir / "02_page_scan"
    stage_3_dir = output_dir / "03_cross_page_completion"
    for directory in (stage_1_dir, stage_2_dir, stage_3_dir):
        directory.mkdir(parents=True, exist_ok=True)

    _copy_stage_files(agent_dir, stage_1_dir, _STAGE_FILES["01_page_classification"])
    _copy_stage_files(agent_dir, stage_2_dir, _STAGE_FILES["02_page_scan"])
    _copy_stage_files(agent_dir, stage_3_dir, _STAGE_FILES["03_cross_page_completion"])

    # Keep one final standard OOXML workbook at a predictable location. The
    # page-agent graph writes table.xlsx; the fallback name supports older runs.
    generated_xlsx = _first_existing(
        output_dir / "table.xlsx",
        output_dir / "wiring-table-import.xlsx",
        output_dir / "wiring-table.xlsx",
        stage_3_dir / "table.xlsx",
    )
    if generated_xlsx is None:
        raise RuntimeError(
            "The extraction graph completed without generating table.xlsx. "
            f"Inspect diagnostics under {agent_dir}."
        )
    final_xlsx = stage_3_dir / "table.xlsx"
    if generated_xlsx.resolve() != final_xlsx.resolve():
        shutil.copy2(generated_xlsx, final_xlsx)
    root_xlsx = output_dir / "table.xlsx"
    if final_xlsx.resolve() != root_xlsx.resolve():
        shutil.copy2(final_xlsx, root_xlsx)

    summary = {
        "run_id": run_id,
        "project_id": project_id,
        "profile": profile.profile.model_dump(mode="json"),
        "pdf_path": str(pdf_path),
        "output_dir": str(output_dir),
        "stage_1": str(stage_1_dir),
        "stage_2": str(stage_2_dir),
        "stage_3": str(stage_3_dir),
        "final_xlsx": str(final_xlsx),
        "extraction_errors": execution.extraction_errors,
        "validation_warnings": execution.validation_warnings,
    }
    (output_dir / "run-result.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _copy_stage_files(
        output_dir,
        stage_3_dir,
        ("wiring-table-import.xlsx", "wiring-table-import.xls"),
    )
    report(f"completed; final xlsx={final_xlsx}")
    return ThreeStageRunResult(
        execution=execution,
        output_dir=output_dir,
        stage_1_dir=stage_1_dir,
        stage_2_dir=stage_2_dir,
        stage_3_dir=stage_3_dir,
        final_xlsx=final_xlsx,
    )


def _copy_stage_files(source_dir: Path, target_dir: Path, names: tuple[str, ...]) -> None:
    for name in names:
        source = source_dir / name
        if source.is_file():
            shutil.copy2(source, target_dir / name)


def _first_existing(*paths: Path) -> Path | None:
    return next((path for path in paths if path.is_file()), None)
