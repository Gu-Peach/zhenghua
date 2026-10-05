from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from ..core.config import Settings


class SupabaseStoreError(RuntimeError):
    """Raised when Supabase Storage or REST synchronization fails."""


async def sync_job_to_supabase(
    settings: Settings,
    job_dir: Path,
    manifest: dict[str, Any],
) -> dict[str, Any] | None:
    """Upload a completed local job folder and upsert one row per wire table."""
    if not settings.supabase_enabled:
        return None
    _require_config(settings)

    job_id = job_dir.name
    bucket = settings.supabase_storage_bucket
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0)) as client:
        uploaded = await _upload_tree(client, settings, job_dir, job_id, bucket)
        rows = _build_rows(manifest, job_dir, job_id)
        if rows:
            await _upsert_rows(client, settings, rows)

    return {
        "enabled": True,
        "bucket": bucket,
        "job_id": job_id,
        "uploaded_files": uploaded,
        "row_count": len(rows),
        "source_url": _public_url(settings, bucket, f"{job_id}/source/{_source_filename(job_dir)}"),
    }


def _require_config(settings: Settings) -> None:
    missing = []
    if not settings.supabase_url:
        missing.append("SUPABASE_URL")
    if not settings.supabase_service_role_key:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if missing:
        raise SupabaseStoreError(f"Supabase is enabled but missing: {', '.join(missing)}")


async def _upload_tree(
    client: httpx.AsyncClient,
    settings: Settings,
    job_dir: Path,
    job_id: str,
    bucket: str,
) -> int:
    files = [path for path in job_dir.rglob("*") if path.is_file()]
    for path in files:
        relative = path.relative_to(job_dir).as_posix()
        object_path = f"{job_id}/{relative}"
        url = f"{settings.supabase_url}/storage/v1/object/{quote(bucket, safe='')}/{quote(object_path, safe='/')}"
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        response = await client.post(
            url,
            content=path.read_bytes(),
            headers={
                "apikey": settings.supabase_service_role_key or "",
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": content_type,
                "x-upsert": "true",
            },
        )
        if response.status_code >= 300:
            raise SupabaseStoreError(
                f"Storage upload failed for {object_path}: {response.status_code} {response.text}"
            )
    return len(files)


async def _upsert_rows(
    client: httpx.AsyncClient,
    settings: Settings,
    rows: list[dict[str, Any]],
) -> None:
    url = f"{settings.supabase_url}/rest/v1/wiring_tables?on_conflict=job_id%2Cgroup_id"
    response = await client.post(
        url,
        json=rows,
        headers={
            "apikey": settings.supabase_service_role_key or "",
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
    )
    if response.status_code >= 300:
        raise SupabaseStoreError(
            f"Database upsert failed: {response.status_code} {response.text}"
        )


def _build_rows(manifest: dict[str, Any], job_dir: Path, job_id: str) -> list[dict[str, Any]]:
    source_filename = _source_filename(job_dir)
    diagnostics_path = f"{job_id}/agent/merge_decisions.json"
    all_page_paths = [
        f"{job_id}/pages/{path.name}"
        for path in sorted((job_dir / "pages").glob("page_*.png"))
        if path.is_file()
    ]
    rows: list[dict[str, Any]] = []
    for group in manifest.get("groups", []):
        group_id = str(group.get("group_id") or "").strip()
        if not group_id:
            continue
        group_dir = job_dir / "groups" / group_id
        records = group.get("records") or _read_json(group_dir / "records.json", default=[])
        page_numbers = [int(page) for page in group.get("pages", [])]
        page_paths = [
            f"{job_id}/groups/{group_id}/pages/page_{page:03d}.png"
            for page in page_numbers
            if (group_dir / "pages" / f"page_{page:03d}.png").is_file()
        ]
        rows.append(
            {
                "job_id": job_id,
                "group_id": group_id,
                "source_filename": str(manifest.get("source_filename") or source_filename),
                "title": str(group.get("title") or group_id),
                "status": str(group.get("status") or manifest.get("status") or "processing"),
                "pages": page_numbers,
                "reason": group.get("reason"),
                "record_count": int(group.get("record_count") or len(records)),
                "records": records,
                "source_pdf_path": f"{job_id}/source/{source_filename}",
                "page_paths": page_paths,
                "all_page_paths": all_page_paths,
                "records_path": f"{job_id}/groups/{group_id}/records.json",
                "xlsx_path": f"{job_id}/groups/{group_id}/wiring-table.xlsx",
                "diagnostics_path": diagnostics_path,
                "error": group.get("error"),
                "metadata": {
                    "job_name": manifest.get("name"),
                    "job_status": manifest.get("status"),
                    "status_message": manifest.get("status_message"),
                },
            }
        )
    return rows


def _read_json(path: Path, *, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _source_filename(job_dir: Path) -> str:
    source_files = sorted(path for path in (job_dir / "source").glob("*") if path.is_file())
    return source_files[0].name if source_files else "upload.pdf"


def _public_url(settings: Settings, bucket: str, object_path: str) -> str:
    return f"{settings.supabase_url}/storage/v1/object/public/{quote(bucket, safe='')}/{quote(object_path, safe='/')}"
