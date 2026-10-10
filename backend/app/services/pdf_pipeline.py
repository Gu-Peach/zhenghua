from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile

from ..agents.wiring_graph import AgentRunResult, run_wiring_agent
from ..core.config import ConfigError, load_settings
from ..schemas.library import PageAsset, ProcessUploadResponse, WireTableGroup
from ..schemas.wire import WireRecord
from .excel_writer import records_to_xlsx_bytes
from .library_store import (
    create_job_dir,
    make_manifest,
    read_manifest,
    write_group_error,
    write_group_outputs,
    write_manifest,
    write_source_file,
    write_group_import_xls,
    manifest_to_job,
)
from .prompt_loader import load_prompt
from .supabase_store import SupabaseStoreError, sync_job_to_supabase
from .vlm_client import ImagePayload, VLMClient, VLMError, _extract_json_candidate


@dataclass(frozen=True)
class PageGroup:
    group_id: str
    title: str
    page_numbers: list[int]
    reason: str | None = None


async def process_pdf_upload(
    *,
    file: UploadFile,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    extraction_prompt: str | None = None,
    grouping_prompt: str | None = None,
    max_pdf_pages: int | None = None,
    background_tasks: Any | None = None,
) -> ProcessUploadResponse:
    try:
        settings = load_settings(api_key=api_key, base_url=base_url, model=model, max_pdf_pages=max_pdf_pages)
        extract_prompt = load_prompt(settings.prompt_path, override=extraction_prompt)
        segment_prompt_path = settings.segment_prompt_path or settings.grouping_prompt_path
        group_prompt = load_prompt(segment_prompt_path, override=grouping_prompt) if segment_prompt_path else ""
    except (ConfigError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    source_filename = file.filename or "uploaded.pdf"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded PDF is empty.")
    if not source_filename.lower().endswith(".pdf") and file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    job_dir = create_job_dir(settings.library_root or Path("frontend/public/library"), source_filename)
    source_path = write_source_file(job_dir, source_filename, content)
    pages: list[PageAsset] = []
    source_url = f"/library/{job_dir.name}/source/{source_path.name}"

    initial_manifest = make_manifest(
        name=Path(source_filename).stem,
        source_filename=source_filename,
        source_url=source_url,
        status="processing",
        pages=pages,
        groups=[],
        status_message="PDF 已接收，等待 Agent 拆页。",
    )
    write_manifest(job_dir, initial_manifest)

    if background_tasks is not None:
        background_tasks.add_task(
            run_pdf_extraction_job_agent,
            settings,
            extract_prompt,
            group_prompt,
            job_dir,
            source_filename,
            source_url,
            None,
            pages,
        )
        return ProcessUploadResponse(job=manifest_to_job(job_dir.name, initial_manifest))

    final_manifest = await run_pdf_extraction_job_agent(
        settings,
        extract_prompt,
        group_prompt,
        job_dir,
        source_filename,
        source_url,
        None,
        pages,
    )
    return ProcessUploadResponse(job=manifest_to_job(job_dir.name, final_manifest))


async def resume_pdf_extraction_job(
    *,
    job_id: str,
    background_tasks: Any | None = None,
    force: bool = False,
) -> ProcessUploadResponse:
    """Resume a completed/partial job using its per-batch extraction checkpoint."""
    try:
        settings = load_settings()
        extract_prompt = load_prompt(settings.prompt_path)
        segment_prompt_path = settings.segment_prompt_path or settings.grouping_prompt_path
        segment_prompt = load_prompt(segment_prompt_path) if segment_prompt_path else ""
    except (ConfigError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    library_root = (settings.library_root or Path("frontend/public/library")).resolve()
    job_dir = (library_root / job_id).resolve()
    if library_root not in job_dir.parents or not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        manifest = read_manifest(job_dir)
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=404, detail="Job manifest not found") from exc

    status = str(manifest.get("status") or "")
    if status == "processing" and not force:
        raise HTTPException(status_code=409, detail="Job is already processing")
    source_dir = job_dir / "source"
    source_files = sorted(path for path in source_dir.iterdir() if path.is_file()) if source_dir.is_dir() else []
    if not source_files:
        raise HTTPException(status_code=404, detail="Job source PDF not found")

    source_filename = str(manifest.get("source_filename") or source_files[0].name)
    source_url = str(manifest.get("source_url") or f"/library/{job_id}/source/{source_files[0].name}")
    pages = [PageAsset.model_validate(page) for page in manifest.get("pages", [])]
    processing_manifest = dict(manifest)
    processing_manifest.update(
        {
            "status": "processing",
            "groups": [],
            "status_message": "Force-resuming from checkpoints." if force else "Resuming from checkpoints.",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    write_manifest(job_dir, processing_manifest)

    task_args = (
        settings,
        extract_prompt,
        segment_prompt,
        job_dir,
        source_filename,
        source_url,
        None,
        pages,
    )
    if background_tasks is not None:
        background_tasks.add_task(run_pdf_extraction_job_agent, *task_args)
        return ProcessUploadResponse(job=manifest_to_job(job_id, processing_manifest))

    final_manifest = await run_pdf_extraction_job_agent(*task_args)
    return ProcessUploadResponse(job=manifest_to_job(job_id, final_manifest))


async def run_pdf_extraction_job_agent(
    settings: Any,
    extract_prompt: str,
    segment_prompt: str,
    job_dir: Path,
    source_filename: str,
    source_url: str,
    images: list[ImagePayload] | None,
    pages: list[PageAsset] | None,
) -> dict[str, Any]:
    """Run the LangGraph V1 pipeline and adapt its state to the library manifest."""
    name = Path(source_filename).stem
    current_groups: list[WireTableGroup] = []
    current_pages = list(pages or [])
    current_table_headers: list[str] = []
    current_table_rows: list[list[Any]] = []

    def progress(message: str) -> None:
        # Keep the frontend pollable while the graph is waiting on a remote VLM.
        progress_path = job_dir / "agent" / "progress.jsonl"
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        with progress_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": message,
            }, ensure_ascii=False) + "\n")
        live_pages = current_pages or _page_assets_from_directory(job_dir)
        write_manifest(
            job_dir,
            make_manifest(
                name=name,
                source_filename=source_filename,
                source_url=source_url,
                status="processing",
                pages=live_pages,
                groups=current_groups,
                table_headers=current_table_headers,
                table_rows=current_table_rows,
                grouping_raw=_live_agent_diagnostics(job_dir),
                status_message=message,
            ),
        )

    client = VLMClient(settings, extract_prompt)
    source_files = sorted((job_dir / "source").iterdir())
    source_path = source_files[0] if source_files else job_dir / "source" / source_filename
    try:
        result: AgentRunResult = await run_wiring_agent(
            pdf_path=source_path,
            output_path=job_dir,
            settings=settings,
            extraction_prompt=extract_prompt,
            segment_prompt=segment_prompt,
            preloaded_images=images,
            progress=progress,
            output_mode=settings.output_mode,
            extraction_client=client,
        )
    except Exception as exc:
        failed_manifest = make_manifest(
            name=name,
            source_filename=source_filename,
            source_url=source_url,
            status="failed",
            pages=current_pages,
            groups=[],
            status_message=f"Agent 处理失败：{exc}",
        )
        write_manifest(job_dir, failed_manifest)
        return failed_manifest
    state = result.state
    output_pages = current_pages or _page_assets_from_state(job_dir, state)
    records_by_segment = state["wiring_records"]
    segment_errors: dict[int, str] = {}
    new_page_agent_mode = bool(state.get("wire_units") or state.get("page_scan_results"))
    if new_page_agent_mode:
        # New flow: groups represent logical wire units, not page batches.
        for unit_id, raw_unit in state.get("wire_units", {}).items():
            unit_pages = sorted({int(page) for page in raw_unit.get("source_pages", [])})
            records = records_by_segment.get(unit_id, [])
            error_messages = [
                message
                for error_id, message in result.extraction_errors.items()
                if any(error_id == f"page-{page:04d}" for page in unit_pages)
            ]
            unresolved = any(record.status not in {"complete", "resolved"} for record in records)
            status = "failed" if error_messages and not records else "partial" if error_messages or unresolved else "success"
            wire_number = raw_unit.get("wire_number")
            title = f"线表 {wire_number}" if wire_number else f"线表 {unit_id}"
            current_groups.append(
                WireTableGroup(
                    group_id=unit_id,
                    title=title[:120],
                    pages=unit_pages,
                    reason="按 wire_number 聚合；每条 connection 独立输出",
                    status=status,
                    record_count=len(records),
                    records=records,
                    table_headers=list(state.get("table_headers") or []),
                    table_rows=list((state.get("table_rows_by_unit") or {}).get(unit_id, [])),
                    error="；".join(error_messages) if error_messages else None,
                )
            )
    else:
        # Compatibility for old custom clients that only implement extract_images.
        segment_errors = {
            index: ", ".join(
                message for batch_id, message in result.extraction_errors.items()
                if (next((item for item in state.get("extraction_batches", []) if item.get("batch_id") == batch_id), {}) or {}).get("source_page") in page_numbers
            )
            for index, page_numbers in enumerate(state["segments"], start=1)
        }
        current_groups.extend(
            WireTableGroup(
                group_id=f"wire-table-{index:03d}",
                title=f"线表 {index}",
                pages=page_numbers,
                reason=_segment_reason(state["merge_decisions"], page_numbers),
                status=("partial" if segment_errors.get(index) and records_by_segment.get(f"wire-table-{index:03d}")
                        else "failed" if segment_errors.get(index) else "success"),
                record_count=len(records_by_segment.get(f"wire-table-{index:03d}", [])),
                records=records_by_segment.get(f"wire-table-{index:03d}", []),
            )
            for index, page_numbers in enumerate(state["segments"], start=1)
        )

    current_table_headers = list(state.get("table_headers") or [])
    current_table_rows = [
        row
        for group in current_groups
        for row in group.table_rows
    ]
    for group_index, group in enumerate(current_groups, start=1):
        segment_id = group.group_id
        group.json_url = f"/library/{job_dir.name}/groups/{segment_id}/records.json"
        import_xls = job_dir / "groups" / segment_id / "wiring-table-import.xls"
        import_xlsx = job_dir / "groups" / segment_id / "wiring-table-import.xlsx"
        if import_xlsx.is_file():
            group.import_xlsx_url = f"/library/{job_dir.name}/groups/{segment_id}/wiring-table-import.xlsx"
        if import_xls.is_file():
            group.import_xls_url = f"/library/{job_dir.name}/groups/{segment_id}/wiring-table-import.xls"
        if group.error:
            write_group_error(job_dir, group)
        elif segment_errors.get(group_index):
            group.error = segment_errors[group_index]
            write_group_error(job_dir, group)

    status = _status_from_groups(current_groups)
    if not current_groups and result.extraction_errors:
        status = "failed"
    diagnostics = {
        "merge_decisions": state["merge_decisions"],
        "segments": state["segments"],
        "extraction_errors": result.extraction_errors,
        "validation_warnings": result.validation_warnings,
        "drawing_index": state.get("drawing_index", {}),
        "extraction_batches": state.get("extraction_batches", []),
        "page_scan_results": state.get("page_scan_results", {}),
        "wire_units": state.get("wire_units", {}),
        "processed_pages": state.get("processed_pages", []),
        "connection_records": state.get("connection_records", []),
        "cross_page_tasks": state.get("cross_page_tasks", []),
        "cross_page_results": state.get("cross_page_results", {}),
    }
    manifest = make_manifest(
        name=name,
        source_filename=source_filename,
        source_url=source_url,
        status=status,
        pages=output_pages,
        groups=current_groups,
        table_headers=current_table_headers,
        table_rows=current_table_rows,
        grouping_raw=diagnostics,
        status_message=_final_status_message(status, current_groups),
    )
    write_manifest(job_dir, manifest)
    try:
        supabase_sync = await sync_job_to_supabase(settings, job_dir, manifest)
        if supabase_sync is not None:
            manifest["supabase"] = supabase_sync
            write_manifest(job_dir, manifest)
    except (SupabaseStoreError, OSError) as exc:
        manifest["supabase_sync_error"] = str(exc)
        write_manifest(job_dir, manifest)
    return manifest


def _segment_reason(decisions: list[dict[str, Any]], page_numbers: list[int]) -> str:
    page_set = set(page_numbers)
    relevant = [
        decision["reason"]
        for decision in decisions
        if decision["a"] in page_set and decision["b"] in page_set
    ]
    return "；".join(dict.fromkeys(relevant)) or "单页内容段"


def _page_assets_from_state(job_dir: Path, state: dict[str, Any]) -> list[PageAsset]:
    assets: list[PageAsset] = []
    for page in state.get("pages", []):
        filename = Path(page["image_path"]).name
        page_number = int(page["page_number"])
        image_path = Path(page["image_path"])
        try:
            relative_path = image_path.resolve().relative_to(job_dir.resolve()).as_posix()
            url = f"/library/{job_dir.name}/{relative_path}"
        except ValueError:
            url = f"/library/{job_dir.name}/pages/{filename}"
        assets.append(
            PageAsset(
                page_id=f"page-{page_number}",
                page_number=page_number,
                filename=filename,
                url=url,
                drawing_function=page.get("function"),
                drawing_page_number=page.get("internal_page"),
                drawing_object_location=page.get("object_loc"),
                blank=bool(page.get("blank")),
            )
        )
    return assets


def _page_assets_from_directory(job_dir: Path) -> list[PageAsset]:
    page_dir = job_dir / "pages"
    if not page_dir.is_dir():
        return []
    assets: list[PageAsset] = []
    for path in sorted(page_dir.rglob("*.png")):
        match = re.search(r"(?:page_|^)(\d+)(?:__pdf_\d+)?\.png$", path.name, flags=re.IGNORECASE)
        if not match:
            continue
        page_number = int(match.group(1))
        assets.append(
            PageAsset(
                page_id=f"page-{page_number}",
                page_number=page_number,
                filename=path.name,
                url=f"/library/{job_dir.name}/{path.relative_to(job_dir).as_posix()}",
            )
        )
    return assets


def _live_agent_diagnostics(job_dir: Path) -> dict[str, Any]:
    agent_dir = job_dir / "agent"

    def read_json(name: str, fallback: Any) -> Any:
        path = agent_dir / name
        if not path.is_file():
            return fallback
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return fallback

    page_checkpoint = read_json("page-scan-checkpoint.json", {})
    unit_checkpoint = read_json("wire-units-checkpoint.json", {})
    return {
        "processed_pages": page_checkpoint.get("processed_pages", []),
        "page_scan_results": page_checkpoint.get("page_scan_results", {}),
        "wire_units": unit_checkpoint.get("wire_units", {}),
        "page_classifications": read_json("page-classifications.json", {}),
        "plant_function_groups": read_json("plant-function-groups.json", {}),
        "cross_page_tasks": read_json("cross-page-tasks.json", []),
        "cross_page_results": read_json("cross-page-results.json", {}),
        "stage2_table": read_json("stage2-table.json", {}),
        "extraction_errors": read_json("errors.json", {}),
        "validation_warnings": read_json("validation-warnings.json", []),
        "merge_decisions": [],
        "segments": [],
        "extraction_batches": [],
    }


# Kept only for compatibility with callers that imported the pre-Agent helper.
# The API and CLI use run_pdf_extraction_job_agent above.
async def _legacy_run_pdf_extraction_job(
    settings: Any,
    extract_prompt: str,
    group_prompt: str,
    job_dir: Path,
    source_filename: str,
    source_url: str,
    images: list[ImagePayload],
    pages: list[PageAsset],
) -> dict[str, Any]:
    name = Path(source_filename).stem

    client = VLMClient(settings, extract_prompt)
    grouping_raw: Any | None = None
    blank_pages = [index + 1 for index, image in enumerate(images) if getattr(image, "blank", False)]
    blank_note = f"已跳过空白页 {blank_pages}。" if blank_pages else ""
    try:
        write_manifest(
            job_dir,
            make_manifest(
                name=name,
                source_filename=source_filename,
                source_url=source_url,
                status="processing",
                pages=pages,
                groups=[],
                status_message=f"{blank_note}正在进行页面归类。",
            ),
        )
        groups, grouping_raw = await _legacy_classify_pages(client, images, pages, group_prompt, settings.grouping_image_batch_size)
    except Exception as exc:
        # If classification fails, keep the pipeline usable: every content page becomes one batch.
        groups = [
            PageGroup(group_id=f"wire-table-{page.page_number:03d}", title=f"线表 {page.page_number}", page_numbers=[page.page_number], reason=f"fallback: grouping failed: {exc}")
            for page in pages
            if page.page_number not in blank_pages
        ]

    output_groups: list[WireTableGroup] = [
        WireTableGroup(
            group_id=page_group.group_id,
            title=page_group.title,
            pages=page_group.page_numbers,
            reason=page_group.reason,
            status="pending",
        )
        for page_group in groups
    ]
    write_manifest(
        job_dir,
        make_manifest(
            name=name,
            source_filename=source_filename,
            source_url=source_url,
            status="processing",
            pages=pages,
            groups=output_groups,
            grouping_raw=grouping_raw,
            status_message=f"{blank_note}页面归类完成，共 {len(output_groups)} 个线表批次，开始提取。",
        ),
    )

    for index, wire_group in enumerate(output_groups, start=1):
        wire_group.status = "processing"
        write_manifest(
            job_dir,
            make_manifest(
                name=name,
                source_filename=source_filename,
                source_url=source_url,
                status="processing",
                pages=pages,
                groups=output_groups,
                grouping_raw=grouping_raw,
                status_message=f"正在提取 {wire_group.title}（{index}/{len(output_groups)}）。",
            ),
        )
        selected_images = [images[number - 1] for number in wire_group.pages if 1 <= number <= len(images)]
        try:
            records = await client.extract_images(selected_images)
            wire_group.records = records
            wire_group.record_count = len(records)
            wire_group.status = "success"
            write_group_outputs(job_dir, wire_group, records_to_xlsx_bytes(records, sheet_title=wire_group.title[:31] or "放线表"))
        except VLMError as exc:
            wire_group.status = "failed"
            wire_group.error = str(exc)
            write_group_error(job_dir, wire_group)
        except Exception as exc:
            wire_group.status = "failed"
            wire_group.error = str(exc)
            write_group_error(job_dir, wire_group)
        write_manifest(
            job_dir,
            make_manifest(
                name=name,
                source_filename=source_filename,
                source_url=source_url,
                status="processing",
                pages=pages,
                groups=output_groups,
                grouping_raw=grouping_raw,
                status_message=f"{wire_group.title} 已完成，继续处理剩余批次。",
            ),
        )

    status = _status_from_groups(output_groups)
    manifest = make_manifest(
        name=name,
        source_filename=source_filename,
        source_url=source_url,
        status=status,
        pages=output_pages,
        groups=output_groups,
        grouping_raw=grouping_raw,
        status_message=_final_status_message(status, output_groups),
    )
    write_manifest(job_dir, manifest)
    return manifest


# Legacy batch classifier retained for old helper-level integrations. It is
# intentionally not used by the LangGraph V1 upload path.
async def _legacy_classify_pages(
    client: VLMClient,
    images: list[ImagePayload],
    pages: list[PageAsset],
    grouping_prompt: str,
    grouping_batch_size: int,
) -> tuple[list[PageGroup], Any]:
    # Only content pages take part in grouping; blank pages never reach the VLM.
    candidates = [
        (index + 1, image)
        for index, image in enumerate(images)
        if not getattr(image, "blank", False)
    ]
    content_pages = [number for number, _ in candidates]
    if not candidates:
        return [], None
    if len(candidates) == 1:
        only = content_pages[0]
        return [PageGroup(group_id="wire-table-001", title="线表 1", page_numbers=[only], reason="single content page")], None

    batches = [candidates[index : index + grouping_batch_size] for index in range(0, len(candidates), grouping_batch_size)]
    raw_results: list[Any] = []
    groups: list[PageGroup] = []
    for batch in batches:
        page_numbers = [number for number, _ in batch]
        batch_images = [image for _, image in batch]
        page_list = "；".join(f"第 {number} 张图片 = PDF 第 {number} 页" for number in page_numbers)
        response = await client.complete(
            images=batch_images,
            system_prompt=grouping_prompt,
            user_text=(
                "请判断这些 PDF 页面分别属于哪些线表/电路图组。"
                "图片按下列顺序给出，pages 必须使用下列 PDF 页码（空白页已被预先剔除）。"
                f"{page_list}。只返回 JSON。"
            ),
        )
        parsed = _loads_grouping_json(response)
        raw_results.append(parsed)
        groups.extend(_parse_page_groups(parsed, default_page_numbers=page_numbers, group_offset=len(groups)))

    groups = _normalize_groups(groups, page_count=len(pages), allowed_pages=content_pages)
    groups = _merge_cross_page_groups(groups, images)
    return groups, raw_results


def _loads_grouping_json(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return json.loads(_extract_json_candidate(content))


def _parse_page_groups(parsed: Any, *, default_page_numbers: list[int], group_offset: int) -> list[PageGroup]:
    if isinstance(parsed, dict):
        for key in ("groups", "items", "data", "wire_tables", "result"):
            if isinstance(parsed.get(key), list):
                parsed = parsed[key]
                break
    if not isinstance(parsed, list):
        return [PageGroup(group_id=f"wire-table-{group_offset + 1:03d}", title="线表 1", page_numbers=default_page_numbers, reason="fallback: invalid grouping JSON")]

    groups: list[PageGroup] = []
    for index, item in enumerate(parsed, start=1):
        if not isinstance(item, dict):
            continue
        pages = item.get("pages") or item.get("page_numbers") or item.get("page") or []
        if isinstance(pages, int):
            page_numbers = [pages]
        elif isinstance(pages, list):
            page_numbers = [int(page) for page in pages if isinstance(page, (int, str)) and str(page).isdigit()]
        else:
            page_numbers = []
        if not page_numbers:
            continue
        group_number = group_offset + index
        groups.append(
            PageGroup(
                group_id=_safe_group_id(item.get("group_id") or item.get("id") or f"wire-table-{group_number:03d}", group_number),
                title=str(item.get("title") or item.get("name") or f"线表 {group_number}"),
                page_numbers=page_numbers,
                reason=str(item.get("reason")) if item.get("reason") else None,
            )
        )
    if not groups:
        return [PageGroup(group_id=f"wire-table-{group_offset + 1:03d}", title="线表 1", page_numbers=default_page_numbers, reason="fallback: empty groups")]
    return groups


def _normalize_groups(
    groups: list[PageGroup],
    *,
    page_count: int,
    allowed_pages: list[int] | None = None,
) -> list[PageGroup]:
    allowed = set(allowed_pages) if allowed_pages is not None else set(range(1, page_count + 1))
    covered: set[int] = set()
    normalized: list[PageGroup] = []
    for index, group in enumerate(groups, start=1):
        page_numbers = []
        for page in group.page_numbers:
            if page in allowed and page not in page_numbers and page not in covered:
                page_numbers.append(page)
                covered.add(page)
        if page_numbers:
            normalized.append(PageGroup(group.group_id or f"wire-table-{index:03d}", group.title or f"线表 {index}", sorted(page_numbers), group.reason))
    for page in sorted(allowed):
        if page not in covered:
            normalized.append(PageGroup(group_id=f"wire-table-{len(normalized) + 1:03d}", title=f"线表 {len(normalized) + 1}", page_numbers=[page], reason="fallback: ungrouped page"))
    return normalized


def _merge_cross_page_groups(groups: list[PageGroup], images: list[ImagePayload]) -> list[PageGroup]:
    """Merge groups whose PDF pages share a strong location or line-number signal."""
    if len(groups) < 2:
        return groups

    signatures = {
        index + 1: _page_signatures(image.page_text)
        for index, image in enumerate(images)
        if not getattr(image, "blank", False)
    }
    merged = list(groups)
    changed = True
    while changed:
        changed = False
        for left_index in range(len(merged)):
            left = merged[left_index]
            left_signature = set().union(*(signatures.get(page, set()) for page in left.page_numbers))
            for right_index in range(left_index + 1, len(merged)):
                right = merged[right_index]
                if not _groups_are_adjacent(left, right):
                    continue
                right_signature = set().union(*(signatures.get(page, set()) for page in right.page_numbers))
                shared = sorted(left_signature & right_signature)
                if not shared:
                    continue
                left_pages = sorted(set(left.page_numbers + right.page_numbers))
                reason = "; ".join(part for part in (left.reason, right.reason) if part)
                merge_note = f"本地跨页校验合并：共享位置代号/线号 {', '.join(shared[:6])}"
                merged[left_index] = PageGroup(
                    group_id=left.group_id,
                    title=left.title,
                    page_numbers=left_pages,
                    reason=f"{reason}; {merge_note}" if reason else merge_note,
                )
                del merged[right_index]
                changed = True
                break
            if changed:
                break
    return merged


def _groups_are_adjacent(left: PageGroup, right: PageGroup) -> bool:
    left_last = max(left.page_numbers)
    right_first = min(right.page_numbers)
    return right_first - left_last == 1


def _page_signatures(page_text: str | None) -> set[str]:
    if not page_text:
        return set()
    import re

    locations = {
        token.upper()
        for token in re.findall(r"\+\d{2}[A-Z]\d{2}(?:\.\d+)?", page_text, flags=re.IGNORECASE)
    }
    line_numbers = {
        token.upper()
        for token in re.findall(r"\b\d{3}[A-Z]\d{4}\b", page_text, flags=re.IGNORECASE)
    }
    return locations | line_numbers


def _safe_group_id(value: Any, fallback_number: int) -> str:
    import re

    text = re.sub(r"[^0-9A-Za-z_-]+", "-", str(value)).strip("-").lower()
    return text[:48] or f"wire-table-{fallback_number:03d}"


def _status_from_groups(groups: list[WireTableGroup]) -> str:
    if not groups:
        return "empty"
    if all(group.status == "success" for group in groups):
        return "success"
    if any(group.status in {"success", "partial"} for group in groups):
        return "partial"
    return "failed"


def _final_status_message(status: str, groups: list[WireTableGroup]) -> str:
    success_count = sum(1 for group in groups if group.status == "success")
    failed_count = sum(1 for group in groups if group.status == "failed")
    if status == "success":
        return f"处理完成，共 {success_count} 个线表批次。"
    if status == "partial":
        return f"部分完成，成功 {success_count} 个，失败 {failed_count} 个。"
    if not groups:
        return "处理失败，页面扫描或跨页解析未完成，请查看 agent 诊断文件。"
    return f"处理失败，失败 {failed_count} 个线表批次。"
