from __future__ import annotations

import json
from dataclasses import dataclass
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
    write_group_error,
    write_group_outputs,
    write_manifest,
    write_source_file,
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

    def progress(message: str) -> None:
        # Keep the frontend pollable while the graph is waiting on a remote VLM.
        write_manifest(
            job_dir,
            make_manifest(
                name=name,
                source_filename=source_filename,
                source_url=source_url,
                status="processing",
                pages=current_pages,
                groups=current_groups,
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
    current_groups.extend(
        WireTableGroup(
            group_id=f"wire-table-{index:03d}",
            title=f"线表 {index}",
            pages=page_numbers,
            reason=_segment_reason(state["merge_decisions"], page_numbers),
            status="failed" if f"wire-table-{index:03d}" in result.extraction_errors else "success",
            record_count=len(records_by_segment.get(f"wire-table-{index:03d}", [])),
            records=records_by_segment.get(f"wire-table-{index:03d}", []),
        )
        for index, page_numbers in enumerate(state["segments"], start=1)
    )

    for group in current_groups:
        segment_id = group.group_id
        group.json_url = f"/library/{job_dir.name}/groups/{segment_id}/records.json"
        group.xlsx_url = f"/library/{job_dir.name}/groups/{segment_id}/wiring-table.xlsx"
        if segment_id in result.extraction_errors:
            group.error = result.extraction_errors[segment_id]
            write_group_error(job_dir, group)

    status = _status_from_groups(current_groups)
    diagnostics = {
        "merge_decisions": state["merge_decisions"],
        "segments": state["segments"],
        "extraction_errors": result.extraction_errors,
        "validation_warnings": result.validation_warnings,
    }
    manifest = make_manifest(
        name=name,
        source_filename=source_filename,
        source_url=source_url,
        status=status,
        pages=output_pages,
        groups=current_groups,
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
        assets.append(
            PageAsset(
                page_id=f"page-{page_number}",
                page_number=page_number,
                filename=filename,
                url=f"/library/{job_dir.name}/pages/{filename}",
            )
        )
    return assets


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
    if any(group.status == "success" for group in groups):
        return "partial"
    return "failed"


def _final_status_message(status: str, groups: list[WireTableGroup]) -> str:
    success_count = sum(1 for group in groups if group.status == "success")
    failed_count = sum(1 for group in groups if group.status == "failed")
    if status == "success":
        return f"处理完成，共 {success_count} 个线表批次。"
    if status == "partial":
        return f"部分完成，成功 {success_count} 个，失败 {failed_count} 个。"
    return f"处理失败，失败 {failed_count} 个线表批次。"
