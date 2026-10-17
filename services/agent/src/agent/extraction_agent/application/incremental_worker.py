"""Independent extraction Worker. One process serves all selected DrawingProfiles."""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import re
import tempfile
import zipfile
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import httpx

from src.agent.extraction_agent.application.incremental import ExtractionStep, WorkerClaim
from src.agent.extraction_agent.application.page_workflow_extraction import run_page_workflow_extraction
from src.agent.extraction_agent.application.review import REVIEW_CONTRACT_VERSION
from src.agent.extraction_agent.infrastructure.incremental_repository import (
    IncrementalRepository,
    IncrementalSession,
    IncrementalTraceStore,
)
from src.config import AgentSettings
from src.domain.errors import AgentServiceError
from src.domain.models.profiles import ProfileBinding
from src.profiles.package import PackageManifest, build_package, checksum, safe_path, verify_package
from src.profiles.registry import ProfileRegistry

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.agent.extraction_agent.application.stage_persistence import DurableExtractionSession


async def frozen_profile(
    session: IncrementalSession, settings: AgentSettings, directory: Path
) -> ProfileBinding:
    """Freeze assets in private Storage; retries do not reread mutable local Profiles."""
    cached = await session.repository.artifact(session.run, "profile-package")
    if cached:
        meta = cached["snapshot"]
        content = await session.repository.get("project-assets", meta["path"])
        if checksum(content) != meta["checksum"]:
            raise ValueError("Frozen Profile package checksum mismatch")
    else:
        response = await session.repository.request(
            "GET",
            "/rest/v1/extraction_profiles",
            params={
                "profile_key": f"eq.{session.profile['key']}",
                "profile_version": f"eq.{session.profile['version']}",
                "checksum": f"eq.{session.profile['checksum']}",
                "limit": "1",
            },
        )
        rows = response.json()
        ref = rows[0].get("resource_ref", "") if rows else ""
        if ref.startswith("storage://"):
            match = re.fullmatch(
                r"storage://project-assets/(profiles/[0-9a-f-]{36}/[a-z][a-z0-9_-]{0,63}/\d+\.\d+\.\d+/[0-9a-f]{64}\.zip)",
                ref,
            )
            if not match:
                raise ValueError("Invalid published Profile storage scope")
            content = await session.repository.get("project-assets", match[1])
            if checksum(content) != session.profile["checksum"]:
                raise ValueError("Published Profile package checksum mismatch")
        else:
            content = await local_profile_archive(session, settings, directory)
        path = f"projects/{session.project}/runs/{session.run}/profile.zip"
        await session.repository.put("project-assets", path, content, "application/zip")
        await session.commit(
            "profile-package",
            ExtractionStep(
                kind="cache", stage="configuration", snapshot={"path": path, "checksum": checksum(content)}
            ),
        )
    root = directory / "profiles" / "selected"
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if len(archive.infolist()) > 500 or sum(f.file_size for f in archive.infolist()) > 30 * 1024 * 1024:
            raise ValueError("Profile archive expansion limit")
        for name in archive.namelist():
            target = root / safe_path(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
    manifest = PackageManifest.model_validate_json((root / "manifest.json").read_bytes())
    verify_package(root, manifest)
    registry = ProfileRegistry(profile_root=root.parent, workspace_root=directory)
    registry.load_all()
    return registry.bind(session.profile["key"], session.profile["version"], allow_experimental=True)


async def local_profile_archive(
    session: IncrementalSession, settings: AgentSettings, directory: Path
) -> bytes:
    """Keep the established local selection checksum and packaging path unchanged."""
    registry = ProfileRegistry(
        profile_root=settings.profile_root,
        workspace_root=settings.workspace_root,
        allow_legacy_references=True,
    )
    registry.load_all(strict=False)
    snapshot = registry.resolve(session.profile["key"], session.profile["version"], allow_experimental=True)
    files = {snapshot.manifest_path}
    for resource in snapshot.resolved_resources.values():
        files.update(p for p in resource.rglob("*") if p.is_file()) if resource.is_dir() else files.add(
            resource
        )
    digest = hashlib.sha256()
    for file in sorted(files, key=lambda p: str(p).lower()):
        digest.update(file.relative_to(settings.workspace_root).as_posix().encode())
        digest.update(b"\0")
        digest.update(file.read_bytes())
    if f"sha256:{digest.hexdigest()}" != session.profile["checksum"]:
        raise ValueError("Selected Profile resources changed after upload")
    with tempfile.TemporaryDirectory(dir=directory) as temporary:
        package = Path(temporary) / "selected"
        await asyncio.to_thread(build_package, snapshot, package)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in package.rglob("*"):
                if file.is_file():
                    archive.writestr(file.relative_to(package).as_posix(), file.read_bytes())
        content = stream.getvalue()
    return content


async def execute_job(session: IncrementalSession, settings: AgentSettings) -> None:
    session.job = WorkerClaim.model_validate(session.job).model_dump(mode="json")
    if session.job["lease"]["worker"] != session.worker:
        raise ValueError("Claimed worker mismatch")
    directory = settings.workspace_root / ".runtime" / "incremental-extraction" / session.run
    directory.mkdir(parents=True, exist_ok=True)
    if not await session.repository.artifact(session.run, "preparing"):
        await session.commit("preparing", ExtractionStep(kind="rendered", stage="preparing"))
    await session.configuration(
        {
            "workflow": "simple_extraction_v1.1",
            "model": settings.default_model,
            "endpoint_checksum": checksum(
                (settings.model_chat_completions_url or settings.model_base_url or "").encode()
            ),
            "review_contract": REVIEW_CONTRACT_VERSION,
            "max_tokens": settings.model_max_tokens,
            "enable_thinking": settings.model_enable_thinking,
            "json_mode": settings.model_json_mode,
            "render_dpi": settings.extraction_render_dpi,
            "image_max_side": settings.model_input_max_image_side,
            "max_total_pixels": settings.model_max_total_image_pixels,
        }
    )
    profile = await frozen_profile(session, settings, directory)
    project = session.job["project"]
    path = str(project["source_pdf_path"])
    if not path.startswith(f"projects/{session.project}/") or ".." in Path(path).parts:
        raise ValueError("Invalid source object scope")
    content = await session.repository.get(project["source_pdf_bucket"], path)
    if checksum(content) != session.job["run"]["options"]["source_checksum"]:
        raise ValueError("Source PDF checksum mismatch")
    pdf = directory / "source.pdf"
    await asyncio.to_thread(pdf.write_bytes, content)
    result = await run_page_workflow_extraction(
        pdf_path=pdf,
        output_dir=directory / "result",
        profile=profile,
        settings=replace(settings, extraction_max_pdf_pages=0, extraction_output_mode="library"),
        run_id=session.run,
        project_id=session.project,
        # The incremental adapter implements the durable callbacks used by the page workflow.
        durable=cast("DurableExtractionSession", session),
        trace_store=IncrementalTraceStore(session),
    )
    if result.execution.extraction_errors:
        raise RuntimeError("One or more pages failed; committed rows are retained for retry")
    await session.commit("finished", ExtractionStep(kind="finished", stage="finished"))


async def run_worker(settings: AgentSettings | None = None, *, once: bool = False) -> None:
    settings = settings or AgentSettings.from_env()
    worker = f"extraction-{uuid4()}"
    async with httpx.AsyncClient(timeout=settings.supabase_request_timeout_seconds) as http:
        repository = IncrementalRepository(settings, http)
        while True:
            job = await repository.rpc("claim_simple_extraction", {"worker": worker})
            if not job:
                if once:
                    return
                await asyncio.sleep(2)
                continue
            session = IncrementalSession(repository, job, worker)
            heartbeat = asyncio.create_task(session.heartbeat())
            task = asyncio.create_task(execute_job(session, settings))
            try:
                done, _ = await asyncio.wait({heartbeat, task}, return_when=asyncio.FIRST_COMPLETED)
                for completed in done:
                    completed.result()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Do not emit provider response text, signed URLs or model credentials.
                code = str(exc.code) if isinstance(exc, AgentServiceError) else "EXTRACTION_FAILED"
                logger.error("Extraction run %s failed: %s (%s)", session.run, type(exc).__name__, code)
                if not session.lost:
                    with suppress(Exception):
                        await session.commit(
                            f"failed:{job['lease']['token']}",
                            ExtractionStep(
                                kind="failed",
                                stage="failed",
                                error={
                                    "code": code,
                                    "message": "模型请求被拒绝，请检查模型名称、权限与配置后重试。"
                                    if code == "INVALID_REQUEST"
                                    else "提取未完成，已保存结果保留；请检查Worker日志和配置后重试。",
                                },
                            ),
                        )
            finally:
                heartbeat.cancel()
                task.cancel()
                await asyncio.gather(heartbeat, task, return_exceptions=True)
            if once:
                return


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())
