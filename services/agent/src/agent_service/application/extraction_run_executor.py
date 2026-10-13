from __future__ import annotations

import asyncio
import re
from dataclasses import replace
from pathlib import Path

from ..config import AgentSettings
from ..domain.enums import AgentStage, EventType, ProfileDetectionStatus, RunStatus
from ..domain.models.runs import AgentRun
from ..domain.models.stage_persistence import StageInput
from ..domain.ports import ArtifactRepository
from ..harness.stores import CancellationToken
from ..infrastructure.document.pdf_runtime import load_pdf_module
from ..infrastructure.project_assets import SupabaseProjectAssetStore
from ..infrastructure.source_documents import SourceDocumentProvider
from ..infrastructure.supabase_profile_packages import SupabaseProfilePackageRepository
from ..infrastructure.supabase_stage_repository import SupabaseStageRepository
from ..profiles import ProfileRegistry
from ..tools.profile_detection import ProfileDetectionTool
from ..tools.result_proposal import build_extraction_result_proposal
from .page_workflow_extraction import run_page_workflow_extraction
from .run_control import RunEventPublisher
from .stage_persistence import DurableExtractionSession
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
        durable_stages: SupabaseStageRepository | None = None,
        profile_packages: SupabaseProfilePackageRepository | None = None,
    ) -> None:
        self._settings = settings
        self._profiles = profiles
        self._documents = documents
        self._artifacts = artifacts
        self._publisher = publisher
        self._runtime_root = runtime_root.resolve()
        self._profile_detection = profile_detection
        self._project_assets = project_assets
        self._durable_stages = durable_stages
        self._profile_packages = profile_packages

    async def execute(self, run: AgentRun, cancellation: CancellationToken) -> RunExecutionOutcome:
        cancellation.raise_if_cancelled()
        if run.expected_result_version is None:
            return RunExecutionOutcome(status=RunStatus.WAITING_INPUT)
        access = await self._documents.get(run.source_document_id, run.project_id)
        confirmation = run.options.profile_confirmation
        if confirmation and (
            confirmation.source_checksum != access.checksum
            or confirmation.profile != run.profile
            or confirmation.confirmed_by != run.requested_by
        ):
            raise ValueError("Confirmed Profile/source/actor no longer matches the frozen run.")
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
        profile = (
            await self._profile_packages.bind(run.profile)
            if self._profile_packages and run.profile
            else self._profiles.bind(profile_key, run.profile.version if run.profile else None)
        )
        run.profile = profile.profile
        if run.protocol_version == 2:
            if self._durable_stages is None:
                raise ValueError("Protocol 2 requires durable stages.")
            return await self._execute_durable(run, access.local_path, access.checksum, cancellation)
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
                elif message.startswith("page_extraction: persisted PDF page"):
                    pages_completed += 1
                    await self._publisher.publish(
                        run,
                        EventType.ITEM_COMPLETED,
                        stage=AgentStage.PAGE_SCAN,
                        message="page extraction persisted",
                        metrics={"processed": pages_completed, "total": page_total},
                    )
                elif message.startswith("assemble_table:"):
                    await complete_stage(
                        AgentStage.PAGE_SCAN,
                        "stage_artifacts",
                        ("page-scan-results.json", "wire-units.json", "cross-page-results.json"),
                    )
                    await start_stage(AgentStage.VALIDATION)
                    await complete_stage(AgentStage.VALIDATION, "final_workbook", ("table.json",))

        def report_progress(message: str) -> None:
            progress_queue.put_nowait(message)

        await start_stage(AgentStage.RENDER)
        progress_task = asyncio.create_task(consume_progress())
        try:
            result = await run_page_workflow_extraction(
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

    async def _execute_durable(
        self, run: AgentRun, pdf_path: Path, checksum: str, cancellation: CancellationToken
    ) -> RunExecutionOutcome:
        repository = self._durable_stages
        assert repository is not None and run.profile is not None
        profile = (
            await self._profile_packages.bind(run.profile)
            if self._profile_packages
            else self._profiles.bind(run.profile.key, run.profile.version)
        )
        inputs = await repository.load_input(run.agent_run_id)
        if inputs is None:

            def page_count() -> int:
                with load_pdf_module().open(str(pdf_path)) as document:
                    return int(document.page_count)

            inputs = StageInput(
                run_id=run.agent_run_id,
                project_id=run.project_id,
                source_document_id=run.source_document_id,
                source_checksum=checksum,
                profile=profile.profile,
                page_count=await asyncio.to_thread(page_count),
                configuration={
                    "workflow": "page_extraction_v2",
                    "model": run.options.model_override or self._settings.default_model,
                    "render_dpi": self._settings.extraction_render_dpi,
                    "max_tokens": self._settings.model_max_tokens,
                    "json_mode": self._settings.model_json_mode,
                    "enable_thinking": self._settings.model_enable_thinking,
                    "fewshot_max_image_side": self._settings.model_fewshot_max_image_side,
                    "bucket": self._settings.supabase_storage_bucket,
                },
            )
        if inputs.source_checksum != checksum or inputs.profile != profile.profile:
            raise ValueError("Source or frozen Profile changed.")
        if inputs.configuration.get("workflow") != "page_extraction_v2":
            raise ValueError("Legacy three-stage run is read-only; submit a new extraction run.")
        await repository.initialize(inputs)
        output_dir = self._runtime_root / run.agent_run_id
        session = DurableExtractionSession(repository, inputs, output_dir, pdf_path)
        frozen_settings = replace(
            self._settings,
            default_model=inputs.configuration["model"],
            extraction_render_dpi=inputs.configuration["render_dpi"],
            model_max_tokens=inputs.configuration["max_tokens"],
            model_json_mode=inputs.configuration["json_mode"],
            model_enable_thinking=inputs.configuration["enable_thinking"],
            model_fewshot_max_image_side=inputs.configuration["fewshot_max_image_side"],
            supabase_storage_bucket=inputs.configuration["bucket"],
        )
        result = await run_page_workflow_extraction(
            pdf_path=pdf_path,
            output_dir=output_dir,
            profile=profile,
            settings=frozen_settings,
            run_id=run.agent_run_id,
            project_id=run.project_id,
            cancellation=cancellation,
            durable=session,
        )
        proposal = build_extraction_result_proposal(
            agent_run_id=run.agent_run_id,
            project_id=run.project_id,
            source_document_id=run.source_document_id,
            base_result_version=run.expected_result_version or 0,
            profile=profile,
            model_name=str(inputs.configuration["model"] or "unconfigured"),
            state=result.execution.state,
            validation_warnings=result.execution.validation_warnings,
        )
        return RunExecutionOutcome(
            status=RunStatus.NEEDS_REVIEW if proposal.status == "NEEDS_REVIEW" else RunStatus.SUCCEEDED,
            proposal=proposal,
        )
