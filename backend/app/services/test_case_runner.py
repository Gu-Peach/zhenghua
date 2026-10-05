from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Callable

from ..core.config import Settings
from ..schemas.wire import WireRecord
from .excel_writer import records_to_xlsx_bytes
from .file_inputs import path_to_image_payloads
from .vlm_client import ImagePayload, VLMClient


SUPPORTED_SOURCE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".pdf"}


@dataclass(frozen=True)
class TestCaseResult:
    case_id: str
    case_dir: str
    status: str
    source_count: int
    image_count: int
    record_count: int
    json_path: str | None
    xlsx_path: str | None
    error_path: str | None = None
    error_message: str | None = None


async def run_test_cases(
    *,
    case_root: Path,
    settings: Settings,
    prompt: str,
    output_name: str = "result",
    sheet_title: str = "放线表",
    progress: Callable[[str], None] | None = None,
) -> list[TestCaseResult]:
    client = VLMClient(settings, prompt)
    results: list[TestCaseResult] = []
    case_dirs = discover_case_dirs(case_root)
    _emit(progress, f"Discovered {len(case_dirs)} test case(s) under {case_root}")

    for case_index, case_dir in enumerate(case_dirs, start=1):
        case_started_at = perf_counter()
        sources = discover_case_sources(case_dir)
        _emit(progress, f"[{case_index}/{len(case_dirs)}] Case {case_dir.name}: found {len(sources)} source file(s)")
        json_path = case_dir / f"{output_name}.json"
        xlsx_path = case_dir / f"{output_name}.xlsx"
        error_path = case_dir / f"{output_name}.error.json"
        _clear_case_outputs(json_path, xlsx_path, error_path)
        images: list[ImagePayload] = []
        try:
            for source in sources:
                images.extend(path_to_image_payloads(source, settings.max_pdf_pages))
            blank_count = sum(1 for image in images if image.blank)
            images = [image for image in images if not image.blank]
            suffix = f", skipped {blank_count} blank page(s)" if blank_count else ""
            _emit(progress, f"[{case_index}/{len(case_dirs)}] Case {case_dir.name}: prepared {len(images)} image payload(s){suffix}")

            records: list[WireRecord] = []
            batches = [images[index : index + settings.image_batch_size] for index in range(0, len(images), settings.image_batch_size)]
            for batch_index, batch in enumerate(batches, start=1):
                batch_started_at = perf_counter()
                names = ", ".join(image.name for image in batch)
                _emit(
                    progress,
                    (
                        f"[{case_index}/{len(case_dirs)}] Case {case_dir.name}: "
                        f"calling VLM batch {batch_index}/{len(batches)} "
                        f"({len(batch)} image(s), timeout {settings.timeout_seconds:g}s) -> {settings.chat_completions_url}; files: {names}"
                    ),
                )
                records.extend(await client.extract_images(batch))
                _emit(
                    progress,
                    f"[{case_index}/{len(case_dirs)}] Case {case_dir.name}: batch {batch_index}/{len(batches)} returned in {_format_seconds(perf_counter() - batch_started_at)}",
                )

            json_path.write_text(_records_to_json(records), encoding="utf-8")
            xlsx_path.write_bytes(records_to_xlsx_bytes(records, sheet_title=sheet_title))
            _emit(
                progress,
                (
                    f"[{case_index}/{len(case_dirs)}] Case {case_dir.name}: wrote {len(records)} record(s) "
                    f"to {json_path.name} and {xlsx_path.name} in {_format_seconds(perf_counter() - case_started_at)}"
                ),
            )

            results.append(
                TestCaseResult(
                    case_id=case_dir.name,
                    case_dir=str(case_dir),
                    status="success",
                    source_count=len(sources),
                    image_count=len(images),
                    record_count=len(records),
                    json_path=str(json_path),
                    xlsx_path=str(xlsx_path),
                )
            )
        except Exception as exc:
            error_payload = {
                "case_id": case_dir.name,
                "case_dir": str(case_dir),
                "sources": [str(source) for source in sources],
                "image_count": len(images),
                "error": str(exc),
            }
            error_path.write_text(json.dumps(error_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            _emit(
                progress,
                f"[{case_index}/{len(case_dirs)}] Case {case_dir.name}: failed after {_format_seconds(perf_counter() - case_started_at)}; wrote {error_path.name}: {exc}",
            )
            results.append(
                TestCaseResult(
                    case_id=case_dir.name,
                    case_dir=str(case_dir),
                    status="failed",
                    source_count=len(sources),
                    image_count=len(images),
                    record_count=0,
                    json_path=None,
                    xlsx_path=None,
                    error_path=str(error_path),
                    error_message=str(exc),
                )
            )

    return results


def _emit(progress: Callable[[str], None] | None, message: str) -> None:
    if progress:
        progress(message)


def _format_seconds(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)}m {remainder:.0f}s"


def discover_case_dirs(case_root: Path) -> list[Path]:
    if not case_root.exists():
        raise FileNotFoundError(f"Test case directory does not exist: {case_root}")
    if discover_case_sources(case_root):
        return [case_root]

    case_dirs = [path for path in case_root.iterdir() if path.is_dir() and discover_case_sources(path)]
    return sorted(case_dirs, key=lambda path: path.name)


def discover_case_sources(case_dir: Path) -> list[Path]:
    return sorted(
        [path for path in case_dir.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_SOURCE_EXTENSIONS],
        key=lambda path: path.name,
    )


def _clear_case_outputs(*paths: Path) -> None:
    for path in paths:
        if path.exists():
            path.unlink()


def _records_to_json(records: list[WireRecord]) -> str:
    return json.dumps([record.model_dump(exclude_none=False) for record in records], ensure_ascii=False, indent=2)


def results_to_json(results: list[TestCaseResult]) -> str:
    return json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2)
