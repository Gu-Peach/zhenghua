from __future__ import annotations

from ..domain.enums import AgentStage
from ..domain.models.imports import RunStageSummaryResponse
from ..infrastructure.supabase_stage_repository import SupabaseStageRepository
from .run_control import RunControlService


async def stage_summary(
    runs: RunControlService, repository: SupabaseStageRepository | None, run_id: str, user_id: str,
) -> RunStageSummaryResponse:
    """Return committed receipts, not speculative in-memory progress."""
    run = await runs.get_required(run_id)
    if run.requested_by != user_id:
        raise PermissionError("Run access denied.")
    stages = []
    inputs = await repository.load_input(run_id) if repository and run.protocol_version == 2 else None
    events = await runs.events.list_after(run_id)
    while events:
        batch = await runs.events.list_after(run_id, events[-1].seq)
        if not batch:
            break
        events.extend(batch)
    for stage in (
        AgentStage.RENDER, AgentStage.PAGE_CLASSIFICATION, AgentStage.PAGE_SCAN,
        AgentStage.BUILD_CROSS_PAGE_TASKS, AgentStage.CROSS_PAGE_COMPLETION, AgentStage.VALIDATION,
    ):
        manifest = await repository.load_snapshot(run_id, stage) if inputs and repository else None
        timestamps = [event.occurred_at for event in events if event.stage == stage]
        stages.append({
            "stage": stage.value, "committed": manifest is not None,
            "counts": manifest.counts if manifest else {},
            "result_digest": manifest.result_digest if manifest else None,
            "tree_published": manifest.tree_published if manifest else False,
            "elapsed_seconds": (max(timestamps) - min(timestamps)).total_seconds() if timestamps else None,
        })
    final = await repository.final_receipt(run_id) if inputs and repository else None
    return RunStageSummaryResponse(
        agent_run_id=run_id, status=run.status.value,
        model_name=inputs.configuration.get("model") if inputs else run.options.model_override,
        profile=run.profile.model_dump(mode="json") if run.profile else None, stages=stages,
        final_receipt=final.model_dump(mode="json") if final else None,
    )
