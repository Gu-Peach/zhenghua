from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ...core.config import ConfigError, load_settings
from ...schemas.library import JobDetail, JobSummary, ProcessUploadResponse
from ...services.library_store import list_jobs, load_job, remove_job
from ...services.pdf_pipeline import process_pdf_upload, resume_pdf_extraction_job


router = APIRouter(prefix="/api/v1", tags=["library"])


@router.post("/process/pdf", response_model=ProcessUploadResponse)
async def process_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    model: str | None = Form(default=None),
    base_url: str | None = Form(default=None),
    api_key: str | None = Form(default=None),
    extraction_prompt: str | None = Form(default=None),
    segment_prompt: str | None = Form(default=None),
    grouping_prompt: str | None = Form(default=None),
    max_pdf_pages: int | None = Form(default=None),
) -> ProcessUploadResponse:
    return await process_pdf_upload(
        file=file,
        model=model,
        base_url=base_url,
        api_key=api_key,
        extraction_prompt=extraction_prompt,
        grouping_prompt=segment_prompt or grouping_prompt,
        max_pdf_pages=max_pdf_pages,
        background_tasks=background_tasks,
    )


@router.post("/library/{job_id}/resume", response_model=ProcessUploadResponse)
async def resume_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    force: bool = False,
) -> ProcessUploadResponse:
    return await resume_pdf_extraction_job(
        job_id=job_id,
        background_tasks=background_tasks,
        force=force,
    )


@router.get("/library", response_model=list[JobSummary])
async def get_library() -> list[JobSummary]:
    return list_jobs(_library_root())


@router.get("/library/{job_id}", response_model=JobDetail)
async def get_job(job_id: str) -> JobDetail:
    try:
        return load_job(_library_root(), job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@router.delete("/library/{job_id}")
async def delete_job(job_id: str) -> dict[str, bool]:
    try:
        remove_job(_library_root(), job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    return {"ok": True}


@router.get("/library/{job_id}/{section}/{filename}")
async def get_job_file(job_id: str, section: str, filename: str) -> FileResponse:
    if section not in {"source", "pages", "agent"}:
        raise HTTPException(status_code=404, detail="File not found")
    return _file_response(_library_root() / job_id / section / filename)


@router.get("/library/{job_id}/groups/{group_id}/import-xls")
async def get_group_import_xls(job_id: str, group_id: str) -> FileResponse:
    return _file_response(_library_root() / job_id / "groups" / group_id / "wiring-table-import.xls")


@router.get("/library/{job_id}/groups/{group_id}/{filename}")
async def get_group_file(job_id: str, group_id: str, filename: str) -> FileResponse:
    return _file_response(_library_root() / job_id / "groups" / group_id / filename)


def _library_root() -> Path:
    try:
        settings = load_settings()
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return settings.library_root or Path("frontend/public/library")


def _file_response(path: Path) -> FileResponse:
    try:
        resolved = path.resolve(strict=True)
        root = _library_root().resolve(strict=False)
    except OSError as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc
    if root not in resolved.parents and resolved != root:
        raise HTTPException(status_code=403, detail="Invalid file path")
    return FileResponse(resolved)
