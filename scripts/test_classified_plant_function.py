from __future__ import annotations

"""Run Agent stages two and three for one already-classified Plant Function."""

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.agents.state import PageMeta
from backend.app.agents.wiring_graph import run_wiring_agent_stages_2_3
from backend.app.core.config import ConfigError, load_settings
from backend.app.services.prompt_loader import load_prompt
from backend.app.services.vlm_client import VLMError


STAGE2_FILES = (
    "page-scan-checkpoint.json",
    "page-scan-results.json",
    "wire-units-checkpoint.json",
    "wire-units.json",
    "connection-records.json",
    "stage2-table.json",
)

STAGE3_FILES = (
    "cross-page-tasks.json",
    "cross-page-checkpoint.json",
    "cross-page-results.json",
    "table.json",
    "table.xlsx",
)


def main() -> int:
    args = _parse_args()
    source_job = _resolve_source_job(args.source_job)
    output_dir = args.output_dir.resolve()
    runtime_dir = output_dir / "_runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    drawing_index = _read_json(source_job / "agent" / "drawing_index.json")
    classifications = _read_json(source_job / "agent" / "page-classifications.json")
    pages = _load_classified_pages(source_job, drawing_index, classifications)
    plant_function = _normalize_function(args.plant_function)
    selected = [page for page in pages if _normalize_function(page.get("function")) == plant_function]
    if not selected:
        raise RuntimeError(f"No classified pages found for Plant Function {plant_function}")

    stage2_dir = output_dir / "02_page_scan"
    stage3_dir = output_dir / "03_cross_page_completion"
    stage2_dir.mkdir(parents=True, exist_ok=True)
    stage3_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        output_dir / "scope.json",
        {
            "source_job": str(source_job),
            "plant_function": plant_function,
            "source_pdf_pages": [int(page["page_number"]) for page in selected],
            "drawing_pages": [page.get("internal_page") for page in selected],
        },
    )
    _copy_selected_images(selected, stage2_dir / "pages")

    settings = load_settings()
    prompt_path = settings.page_scan_prompt_path or settings.prompt_path
    extraction_prompt = load_prompt(prompt_path)

    def progress(message: str) -> None:
        print(f"[agent] {message}", flush=True)
        _sync_outputs(runtime_dir, stage2_dir, stage3_dir)

    result = asyncio.run(
        run_wiring_agent_stages_2_3(
            pages=pages,
            source_page_numbers=[int(page["page_number"]) for page in selected],
            drawing_index=drawing_index,
            output_path=runtime_dir,
            settings=settings,
            extraction_prompt=extraction_prompt,
            progress=progress,
        )
    )
    _sync_outputs(runtime_dir, stage2_dir, stage3_dir)
    _copy_task_images(result.state, pages, stage3_dir / "task_images")
    _write_json(output_dir / "errors.json", result.extraction_errors)
    _write_json(output_dir / "validation-warnings.json", result.validation_warnings)
    _write_summaries(stage2_dir, stage3_dir, selected)

    print("\nCompleted", flush=True)
    print(f"  Plant Function: {plant_function}", flush=True)
    print(f"  source pages: {[int(page['page_number']) for page in selected]}", flush=True)
    print(f"  stage 2: {stage2_dir}", flush=True)
    print(f"  stage 3: {stage3_dir}", flush=True)
    print(f"  final table: {stage3_dir / 'table.json'}", flush=True)
    print(f"  final xlsx: {stage3_dir / 'table.xlsx'}", flush=True)
    return 1 if result.extraction_errors else 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run stages two and three from an existing classified backend job."
    )
    parser.add_argument(
        "--source-job",
        required=True,
        help="Existing job id or its frontend/public/library directory",
    )
    parser.add_argument("--plant-function", required=True, help="For example: 002.C")
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def _resolve_source_job(value: str) -> Path:
    direct = Path(value)
    if direct.is_dir():
        return direct.resolve()
    candidate = Path("frontend/public/library") / value
    if candidate.is_dir():
        return candidate.resolve()
    raise FileNotFoundError(f"Source job not found: {value}")


def _load_classified_pages(
    source_job: Path,
    drawing_index: dict[str, Any],
    classification_checkpoint: dict[str, Any],
) -> list[PageMeta]:
    classifications = classification_checkpoint.get("classifications") or {}
    pages: list[PageMeta] = []
    missing: list[int] = []
    for raw in drawing_index.get("pages") or []:
        pdf_page = int(raw.get("pdf_page") or 0)
        if pdf_page <= 0:
            continue
        classified = classifications.get(str(pdf_page)) or {}
        function = _normalize_function(raw.get("function") or classified.get("plant_function"))
        internal_page = raw.get("internal_page") or classified.get("page_number")
        image_path = _classified_image_path(
            source_job / "pages",
            pdf_page=pdf_page,
            function=function,
            internal_page=internal_page,
        )
        if image_path is None:
            missing.append(pdf_page)
            continue
        pages.append(
            {
                "page_number": pdf_page,
                "image_path": str(image_path.resolve()),
                "function": function,
                "internal_page": int(internal_page) if internal_page is not None else None,
                "object_loc": raw.get("object_loc"),
                "title": raw.get("title"),
                "is_stub": bool(raw.get("is_stub")),
                "is_non_wiring": bool(raw.get("is_non_wiring") or classified.get("non_wiring")),
                "blank": bool(classified.get("blank")),
                "project_no": raw.get("project_no"),
                "drawing_prefix": raw.get("drawing_prefix"),
                "page_label": str(internal_page) if internal_page is not None else f"pdf_{pdf_page:04d}",
                "function_folder": _safe_function_folder(function),
            }
        )
    if missing:
        print(f"[warning] skipped {len(missing)} page(s) without classified images", file=sys.stderr)
    return sorted(pages, key=lambda page: int(page["page_number"]))


def _classified_image_path(
    page_root: Path,
    *,
    pdf_page: int,
    function: str | None,
    internal_page: Any,
) -> Path | None:
    folder = page_root / _safe_function_folder(function)
    label = str(int(internal_page)) if internal_page is not None else f"pdf_{pdf_page:04d}"
    duplicate = folder / f"{label}__pdf_{pdf_page:04d}.png"
    primary = folder / f"{label}.png"
    if duplicate.is_file():
        return duplicate
    if primary.is_file():
        return primary
    matches = sorted(folder.glob(f"{label}*.png")) if folder.is_dir() else []
    return matches[0] if matches else None


def _sync_outputs(runtime_dir: Path, stage2_dir: Path, stage3_dir: Path) -> None:
    agent_dir = runtime_dir / "agent"
    for filename in STAGE2_FILES:
        _copy_if_present(agent_dir / filename, stage2_dir / filename)
    for filename in STAGE3_FILES:
        _copy_if_present(agent_dir / filename, stage3_dir / filename)
    _copy_if_present(runtime_dir / "table.json", stage3_dir / "table.json")
    _copy_if_present(runtime_dir / "table.xlsx", stage3_dir / "table.xlsx")
    groups = runtime_dir / "groups"
    if groups.is_dir():
        destination = stage3_dir / "wire_units"
        destination.mkdir(parents=True, exist_ok=True)
        for group_dir in groups.iterdir():
            if not group_dir.is_dir():
                continue
            for filename in ("records.json", "table.json"):
                _copy_if_present(group_dir / filename, destination / group_dir.name / filename)


def _copy_selected_images(pages: list[PageMeta], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for page in pages:
        source = Path(page["image_path"])
        name = f"pdf_{int(page['page_number']):04d}__{source.name}"
        shutil.copy2(source, destination / name)


def _copy_task_images(state: dict[str, Any], pages: list[PageMeta], destination: Path) -> None:
    page_lookup = {int(page["page_number"]): page for page in pages}
    for task in state.get("cross_page_tasks") or []:
        task_id = _safe_component(str(task.get("task_id") or "task"))
        task_dir = destination / task_id
        involved = [task.get("source_pdf_page"), *(task.get("target_pdf_pages") or [])]
        for page_number in involved:
            if page_number is None or int(page_number) not in page_lookup:
                continue
            source = Path(page_lookup[int(page_number)]["image_path"])
            task_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, task_dir / f"pdf_{int(page_number):04d}__{source.name}")


def _write_summaries(stage2_dir: Path, stage3_dir: Path, selected: list[PageMeta]) -> None:
    page_results = _read_json_optional(stage2_dir / "page-scan-results.json", {})
    units = _read_json_optional(stage2_dir / "wire-units.json", {})
    tasks = _read_json_optional(stage3_dir / "cross-page-tasks.json", [])
    results = _read_json_optional(stage3_dir / "cross-page-results.json", {})
    table = _read_json_optional(stage3_dir / "table.json", {})
    _write_json(
        stage2_dir / "summary.json",
        {
            "selected_pages": len(selected),
            "scanned_pages": len(page_results) if isinstance(page_results, dict) else 0,
            "wire_units": len(units) if isinstance(units, dict) else 0,
        },
    )
    _write_json(
        stage3_dir / "summary.json",
        {
            "cross_page_tasks": len(tasks) if isinstance(tasks, list) else 0,
            "cross_page_results": len(results) if isinstance(results, dict) else 0,
            "table_rows": len(table.get("rows") or []) if isinstance(table, dict) else 0,
        },
    )


def _copy_if_present(source: Path, destination: Path) -> None:
    if not source.is_file():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _read_json_optional(path: Path, fallback: Any) -> Any:
    if not path.is_file():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_function(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper().lstrip("=")
    return normalized or None


def _safe_function_folder(value: str | None) -> str:
    normalized = _normalize_function(value) or "UNKNOWN"
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in normalized).strip("._") or "UNKNOWN"


def _safe_component(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in value)[:120] or "task"


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ConfigError, FileNotFoundError, OSError, ValueError, RuntimeError, VLMError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
