from __future__ import annotations

import asyncio
import re
from pathlib import Path

from ..config import AgentSettings
from ..domain.enums import AgentStage, EventType, ProfileDetectionStatus, RunStatus
from ..domain.models.runs import AgentRun
from ..domain.ports import ArtifactRepository
from ..harness.stores import CancellationToken
from ..infrastructure.project_assets import SupabaseProjectAssetStore
from ..infrastructure.source_documents import SourceDocumentProvider
from ..profiles import ProfileRegistry
from ..tools.profile_detection import ProfileDetectionTool
from ..tools.result_proposal import build_extraction_result_proposal
from .run_control import RunEventPublisher
from .three_stage_extraction import run_three_stage_extraction
from .worker import RunExecutionOutcome


class FullExtractionRunExecutor:
    def __init__(
        self,
        *,
        settings: AgentSettings,
        profiles: ProfileRegistry,
        documents: SourceDocumentProvider,
        artifacts: ArtifactRepository,
        publisher: RunEventPublisher,
        runtime_root: Path,
        profile_detection: ProfileDetectionTool | None = None,
        project_assets: SupabaseProjectAssetStore | None = None,
    ) -> None:
        self._settings = settings
        self._profiles = profiles
        self._documents = documents
        self._artifacts = artifacts
        self._publisher = publisher
        self._runtime_root = runtime_root.resolve()
        self._profile_detection = profile_detection
        self._project_assets = project_assets

    async def execute(self, run: AgentRun, cancellation: CancellationToken) -> RunExecutionOutcome:
        cancellation.raise_if_cancelled()
        if run.expected_result_version is None:
            return RunExecutionOutcome(status=RunStatus.WAITING_INPUT)
        access = await self._documents.get(run.source_document_id, run.project_id)
        profile_key = run.profile_hint or (run.profile.key if run.profile else None)
        if not profile_key:
            if self._profile_detection is None:
                return RunExecutionOutcome(status=RunStatus.WAITING_INPUT)
            detection = await self._profile_detection.detect(
                run_id=run.agent_run_id,
                project_id=run.project_id,
                pdf_path=access.local_path,
            )
            artifact_id = f"{run.agent_run_id}:profile-detection"
            await self._artifacts.put(
                artifact_id,
                {
                    "artifact_id": artifact_id,
                    "agent_run_id": run.agent_run_id,
                    "kind": "profile_detection",
                    "payload": detection.model_dump(mode="json"),
                },
            )
            await self._publisher.publish(
                run,
                EventType.PROFILE_DETECTED
                if detection.status == ProfileDetectionStatus.PROFILE_SELECTED
                else EventType.PROFILE_REVIEW_REQUIRED,
                stage=AgentStage.PROFILE_DETECTION,
                message=detection.reason,
                artifact_refs=[artifact_id],
            )
            if detection.assigned_profile is None:
                return RunExecutionOutcome(
                    status=RunStatus.WAITING_INPUT,
                    artifact_ids=[artifact_id],
                )
            profile_key = detection.assigned_profile.key
            run.profile_hint = profile_key
        profile = self._profiles.bind(profile_key)
        run.profile = profile.profile
        output_dir = self._runtime_root / run.agent_run_id
        artifact_ids: list[str] = []
        completed_stages: set[AgentStage] = set()
        project_pages_published = False
        progress_queue: asyncio.Queue[str | None] = asyncio.Queue()
        page_total = 0
        pages_completed = 0

        async def publish_project_pages() -> None:
            nonlocal project_pages_published
            if self._project_assets is None or project_pages_published:
                return
            published = await self._project_assets.publish_extraction_pages(run, output_dir)
            project_pages_published = True
            project_assets_id = f"{run.agent_run_id}:project-assets"
            await self._artifacts.put(
                project_assets_id,
                {
                    "artifact_id": project_assets_id,
                    "agent_run_id": run.agent_run_id,
                    "kind": "project_assets",
                    "storage_bucket": self._settings.supabase_storage_bucket,
                    "workspace_count": published.workspace_count,
                    "drawing_count": published.drawing_count,
                    "object_paths": published.object_paths,
                },
            )
            artifact_ids.append(project_assets_id)

        async def start_stage(stage: AgentStage) -> None:
            await self._publisher.publish(
                run,
                EventType.STAGE_STARTED,
                stage=stage,
                message=f"{stage.value.lower()} started",
            )

        async def complete_stage(
            stage: AgentStage,
            kind: str,
            names: tuple[str, ...],
        ) -> None:
            nonlocal project_pages_published
            artifact_id = f"{run.agent_run_id}:{stage.value.lower()}"
            local_files = [
                output_dir / "agent" / name for name in names if (output_dir / "agent" / name).is_file()
            ]
            files: list[dict[str, object]] | list[str]
            artifact_path: str | None = str(
                output_dir / "pages" if stage == AgentStage.RENDER else output_dir / "agent"
            )
            storage_bucket: str | None = None
            if self._project_assets is not None:
                files = [
                    await self._project_assets.upload_run_artifact(
                        project_id=run.project_id,
                        run_id=run.agent_run_id,
                        stage=stage.value.lower(),
                        file_path=file_path,
                    )
                    for file_path in local_files
                ]
                artifact_path = None
                storage_bucket = self._settings.supabase_storage_bucket
            else:
                files = [str(path) for path in local_files]
            if stage == AgentStage.PAGE_CLASSIFICATION and self._project_assets is not None:
                await publish_project_pages()
            await self._artifacts.put(
                artifact_id,
                {
                    "artifact_id": artifact_id,
                    "agent_run_id": run.agent_run_id,
                    "kind": kind,
                    "stage": stage.value,
                    "path": artifact_path,
                    "storage_bucket": storage_bucket,
                    "files": files,
                    "source_checksum": access.checksum,
                    "profile_checksum": profile.profile.checksum,
                },
            )
            artifact_ids.append(artifact_id)
            completed_stages.add(stage)
            await self._publisher.publish(
                run,
                EventType.STAGE_COMPLETED,
                stage=stage,
                message=f"{stage.value.lower()} completed",
                metrics={"total": page_total}
                if stage in {AgentStage.RENDER, AgentStage.PAGE_CLASSIFICATION}
                else {},
                artifact_refs=[artifact_id],
            )

        async def consume_progress() -> None:
            nonlocal page_total, pages_completed
            while True:
                message = await progress_queue.get()
                if message is None:
                    return
                if message.startswith("pdf_to_images: rendered"):
                    match = re.search(r"rendered (\d+) page", message)
                    page_total = int(match.group(1)) if match else 0
                    await complete_stage(AgentStage.RENDER, "rendered_pages", ())
                    await start_stage(AgentStage.PAGE_CLASSIFICATION)
                elif message.startswith("classify_pages:"):
                    await complete_stage(
                        AgentStage.PAGE_CLASSIFICATION,
                        "stage_artifacts",
                        ("page-classifications.json", "drawing_index.json", "plant-function-groups.json"),
                    )
                    await start_stage(AgentStage.PAGE_SCAN)
                elif message.startswith("page_scan: PDF page"):
                    pages_completed += 1
                    await self._publisher.publish(
                        run,
                        EventType.ITEM_COMPLETED,
                        stage=AgentStage.PAGE_SCAN,
                        message="page scan item completed",
                        metrics={"processed": pages_completed, "total": page_total},
                    )
                elif message.startswith("build_cross_page_tasks:"):
                    await complete_stage(
                        AgentStage.PAGE_SCAN,
                        "stage_artifacts",
                        (
                            "page-scan-results.json",
                            "wire-units.json",
                            "page-scan-checkpoint.json",
                            "wire-units-checkpoint.json",
                        ),
                    )
                    await start_stage(AgentStage.BUILD_CROSS_PAGE_TASKS)
                    await complete_stage(
                        AgentStage.BUILD_CROSS_PAGE_TASKS,
                        "stage_artifacts",
                        ("cross-page-tasks.json", "stage2-table.json"),
                    )
                    await start_stage(AgentStage.CROSS_PAGE_COMPLETION)
                elif message.startswith("resolve_cross_page: completed"):
                    await complete_stage(
                        AgentStage.CROSS_PAGE_COMPLETION,
                        "stage_artifacts",
                        ("cross-page-results.json", "cross-page-checkpoint.json", "table.json"),
                    )
                    await start_stage(AgentStage.VALIDATION)
                elif message.startswith("assemble_xlsx:"):
                    cross_page_artifact = (
                        f"{run.agent_run_id}:{AgentStage.CROSS_PAGE_COMPLETION.value.lower()}"
                    )
                    if cross_page_artifact not in artifact_ids:
                        await complete_stage(
                            AgentStage.CROSS_PAGE_COMPLETION,
                            "stage_artifacts",
                            ("cross-page-results.json", "cross-page-checkpoint.json", "table.json"),
                        )
                        await start_stage(AgentStage.VALIDATION)
                    await complete_stage(AgentStage.VALIDATION, "final_workbook", ("table.json",))

        def report_progress(message: str) -> None:
            progress_queue.put_nowait(message)

        await start_stage(AgentStage.RENDER)
        progress_task = asyncio.create_task(consume_progress())
        try:
            result = await run_three_stage_extraction(
                pdf_path=access.local_path,
                output_dir=output_dir,
                profile=profile,
                settings=self._settings,
                run_id=run.agent_run_id,
                project_id=run.project_id,
                max_pdf_pages=0,
                progress=report_progress,
                cancellation=cancellation,
            )
        finally:
            progress_queue.put_nowait(None)
            await progress_task
        cancellation.raise_if_cancelled()
        await publish_project_pages()
        for stage, kind, names in (
            (
                AgentStage.PAGE_CLASSIFICATION,
                "stage_artifacts",
                ("page-classifications.json", "drawing_index.json", "plant-function-groups.json"),
            ),
            (
                AgentStage.PAGE_SCAN,
                "stage_artifacts",
                (
                    "page-scan-results.json",
                    "wire-units.json",
                    "page-scan-checkpoint.json",
                    "wire-units-checkpoint.json",
                ),
            ),
            (
                AgentStage.BUILD_CROSS_PAGE_TASKS,
                "stage_artifacts",
                ("cross-page-tasks.json", "stage2-table.json"),
            ),
            (
                AgentStage.CROSS_PAGE_COMPLETION,
                "stage_artifacts",
                ("cross-page-results.json", "cross-page-checkpoint.json", "table.json"),
            ),
            (AgentStage.VALIDATION, "final_workbook", ("table.json",)),
        ):
            if stage in completed_stages:
                continue
            await start_stage(stage)
            await complete_stage(stage, kind, names)
        final_workbook = (
            await self._project_assets.upload_run_artifact(
                project_id=run.project_id,
                run_id=run.agent_run_id,
                stage="exports",
                file_path=result.final_xlsx,
            )
            if self._project_assets is not None
            else None
        )
        await self._artifacts.put(
            f"{run.agent_run_id}:final-xlsx",
            {
                "artifact_id": f"{run.agent_run_id}:final-xlsx",
                "agent_run_id": run.agent_run_id,
                "kind": "final_xlsx",
                "path": None if self._project_assets is not None else str(result.final_xlsx),
                "storage_bucket": self._settings.supabase_storage_bucket
                if self._project_assets is not None
                else None,
                "storage_path": final_workbook["storage_path"] if final_workbook else None,
                "checksum": final_workbook["checksum"] if final_workbook else None,
                "size_bytes": final_workbook["size_bytes"] if final_workbook else None,
                "source_checksum": access.checksum,
                "profile_checksum": profile.profile.checksum,
            },
        )
        artifact_ids.append(f"{run.agent_run_id}:final-xlsx")
        proposal = build_extraction_result_proposal(
            agent_run_id=run.agent_run_id,
            project_id=run.project_id,
            source_document_id=run.source_document_id,
            base_result_version=run.expected_result_version,
            profile=profile,
            model_name=run.options.model_override or self._settings.default_model or "unconfigured",
            state=result.execution.state,
            validation_warnings=result.execution.validation_warnings,
        )
        return RunExecutionOutcome(
            status=RunStatus.NEEDS_REVIEW if proposal.status == "NEEDS_REVIEW" else RunStatus.SUCCEEDED,
            proposal=proposal,
            artifact_ids=artifact_ids,
            metrics={"operations": len(proposal.operations), "pages": page_total},
        )
