from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from ..schemas.library import JobDetail, JobSummary, PageAsset, WireTableGroup
from ..schemas.wire import WireRecord


MANIFEST_NAME = "manifest.json"
PUBLIC_LIBRARY_URL_PREFIX = "/library"


def create_job_dir(library_root: Path, source_filename: str) -> Path:
    library_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = _safe_name(Path(source_filename).stem or "drawing")
    return library_root / f"{timestamp}-{stem}-{uuid4().hex[:8]}"


def write_source_file(job_dir: Path, filename: str, content: bytes) -> Path:
    source_dir = job_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    path = source_dir / _safe_filename(filename or "upload.pdf")
    path.write_bytes(content)
    return path


def write_page_images(job_dir: Path, pages: Iterable[tuple[int, bytes]]) -> list[PageAsset]:
    page_dir = job_dir / "pages"
    page_dir.mkdir(parents=True, exist_ok=True)
    assets: list[PageAsset] = []
    for page_number, content in pages:
        filename = f"page_{page_number:03d}.png"
        path = page_dir / filename
        path.write_bytes(content)
        assets.append(
            PageAsset(
                page_id=f"page-{page_number}",
                page_number=page_number,
                filename=filename,
                url=f"{PUBLIC_LIBRARY_URL_PREFIX}/{job_dir.name}/pages/{filename}",
            )
        )
    return assets


def write_group_outputs(job_dir: Path, group: WireTableGroup, xlsx_content: bytes | None = None) -> None:
    group_dir = job_dir / "groups" / group.group_id
    group_dir.mkdir(parents=True, exist_ok=True)
    (group_dir / "records.json").write_text(_records_json(group.records), encoding="utf-8")
    group.json_url = f"{PUBLIC_LIBRARY_URL_PREFIX}/{job_dir.name}/groups/{group.group_id}/records.json"
    if xlsx_content is not None:
        (group_dir / "wiring-table.xlsx").write_bytes(xlsx_content)
        group.xlsx_url = f"{PUBLIC_LIBRARY_URL_PREFIX}/{job_dir.name}/groups/{group.group_id}/wiring-table.xlsx"


def write_group_error(job_dir: Path, group: WireTableGroup) -> None:
    group_dir = job_dir / "groups" / group.group_id
    group_dir.mkdir(parents=True, exist_ok=True)
    (group_dir / "error.json").write_text(json.dumps(group.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")


def write_manifest(job_dir: Path, manifest: dict[str, Any]) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def read_manifest(job_dir: Path) -> dict[str, Any]:
    return json.loads((job_dir / MANIFEST_NAME).read_text(encoding="utf-8"))


def list_jobs(library_root: Path) -> list[JobSummary]:
    if not library_root.exists():
        return []
    jobs: list[JobSummary] = []
    for path in library_root.iterdir():
        if not path.is_dir() or not (path / MANIFEST_NAME).is_file():
            continue
        try:
            detail = manifest_to_job(path.name, read_manifest(path))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        jobs.append(
            JobSummary(
                job_id=detail.job_id,
                name=detail.name,
                status=detail.status,
                created_at=detail.created_at,
                source_filename=detail.source_filename,
                source_url=detail.source_url,
                page_count=detail.page_count,
                group_count=detail.group_count,
                record_count=detail.record_count,
                status_message=detail.status_message,
            )
        )
    return sorted(jobs, key=lambda job: job.created_at, reverse=True)


def load_job(library_root: Path, job_id: str) -> JobDetail:
    job_dir = library_root / job_id
    if not job_dir.is_dir():
        raise FileNotFoundError(job_id)
    return manifest_to_job(job_id, read_manifest(job_dir))


def remove_job(library_root: Path, job_id: str) -> None:
    job_dir = library_root / job_id
    if not job_dir.is_dir():
        raise FileNotFoundError(job_id)
    shutil.rmtree(job_dir)


def manifest_to_job(job_id: str, manifest: dict[str, Any]) -> JobDetail:
    pages = [PageAsset.model_validate(page) for page in manifest.get("pages", [])]
    groups = [WireTableGroup.model_validate(group) for group in manifest.get("groups", [])]
    created_at_value = manifest.get("created_at")
    created_at = datetime.fromisoformat(created_at_value) if created_at_value else datetime.now(timezone.utc)
    return JobDetail(
        job_id=job_id,
        name=manifest.get("name") or manifest.get("source_filename") or job_id,
        status=manifest.get("status") or _derive_status(groups),
        created_at=created_at,
        source_filename=manifest.get("source_filename") or "upload.pdf",
        source_url=manifest.get("source_url"),
        page_count=len(pages),
        group_count=len(groups),
        record_count=sum(group.record_count for group in groups),
        status_message=manifest.get("status_message"),
        pages=pages,
        groups=groups,
        manifest=manifest,
    )


def make_manifest(
    *,
    name: str,
    source_filename: str,
    source_url: str,
    status: str,
    pages: list[PageAsset],
    groups: list[WireTableGroup],
    grouping_raw: Any | None = None,
    status_message: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "source_filename": source_filename,
        "source_url": source_url,
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pages": [page.model_dump(mode="json") for page in pages],
        "groups": [group.model_dump(mode="json") for group in groups],
        "grouping_raw": grouping_raw,
        "status_message": status_message,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _derive_status(groups: list[WireTableGroup]) -> str:
    if not groups:
        return "empty"
    if all(group.status == "success" for group in groups):
        return "success"
    if any(group.status == "success" for group in groups):
        return "partial"
    if any(group.status == "failed" for group in groups):
        return "failed"
    return "processing"


def _records_json(records: list[WireRecord]) -> str:
    return json.dumps([record.model_dump(exclude_none=False) for record in records], ensure_ascii=False, indent=2)


def _safe_filename(filename: str) -> str:
    name = Path(filename).name.strip() or "upload.pdf"
    return re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", name)


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", value).strip("_")
    return cleaned[:40] or "drawing"
