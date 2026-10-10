from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import __version__
from .agents.evaluation_judge import EvaluationJudgeAgent
from .agents.improvement_diagnoser import ImprovementDiagnoserAgent
from .agents.profile_patch_builder import ProfilePatchBuilderAgent
from .agents.supervisor import SupervisorAgent
from .api.routes.health import router as health_router
from .api.routes.improvement import router as improvement_router
from .api.routes.profiles import router as profiles_router
from .api.routes.proposals import router as proposals_router
from .api.routes.runs import router as runs_router
from .api.routes.supervisor import router as supervisor_router
from .application.correction_workflow import CorrectionWorkflowExecutor
from .application.extraction_run_executor import FullExtractionRunExecutor
from .application.extraction_stage_dispatcher import ProfileBoundStageDispatcher
from .application.extraction_stage_factory import build_extraction_stage_dispatcher
from .application.improvement_run_executor import ImprovementRunExecutor
from .application.improvement_workflow import ImprovementWorkflow, default_sandbox_root
from .application.profile_detection import create_profile_detection_runtime
from .application.run_control import RunControlService
from .application.supervisor_conversation import SupervisorConversationService
from .application.supervisor_handlers import register_default_supervisor_handlers
from .application.worker import AgentWorker
from .application.workflow_registry import WorkflowRegistry
from .config import AgentSettings
from .domain.enums import RunType
from .domain.ports import (
    ArtifactRepository,
    CandidateRepository,
    CheckpointStore,
    EvalRepository,
    EventRepository,
    ProposalSink,
    ResultDataRepository,
    RunQueue,
    RunRepository,
    TraceStore,
)
from .harness import (
    InMemoryArtifactRepository,
    InMemoryCandidateRepository,
    InMemoryCheckpointStore,
    InMemoryEvalRepository,
    InMemoryEventRepository,
    InMemoryProposalRepository,
    InMemoryRunRepository,
    InMemoryTraceStore,
    OpenAICompatibleModelGateway,
    ProfileSandbox,
)
from .harness.retry import RetryPolicy
from .infrastructure.conversation_memory import ShortTermConversationStore
from .infrastructure.correction_data import (
    CorrectionDataRepository,
    InMemoryCorrectionDataProvider,
    SupabaseCorrectionDataRepository,
)
from .infrastructure.project_assets import SupabaseProjectAssetStore, SupabaseSourceDocumentProvider
from .infrastructure.queue import InMemoryRunQueue
from .infrastructure.result_data import InMemoryResultDataRepository
from .infrastructure.source_documents import InMemorySourceDocumentProvider, SourceDocumentProvider
from .infrastructure.supabase_client import SupabaseClient
from .infrastructure.supabase_improvement import (
    SupabaseCandidateRepository,
    SupabaseEvalRepository,
)
from .infrastructure.supabase_repositories import (
    SupabaseArtifactRepository,
    SupabaseCheckpointStore,
    SupabaseEventRepository,
    SupabaseProposalRepository,
    SupabaseRunQueue,
    SupabaseRunRepository,
    SupabaseTraceStore,
)
from .infrastructure.supabase_result_data import SupabaseResultDataRepository
from .observability import configure_logging
from .profiles.registry import ProfileRegistry
from .tools.extraction_runner import ScopedExtractionRunner
from .tools.profile_detection import ProfileDetectionTool
from .tools.result_data import ControlledResultDataTool


def create_app(
    settings: AgentSettings | None = None,
    profile_registry: ProfileRegistry | None = None,
) -> FastAPI:
    resolved_settings = settings or AgentSettings.from_env()
    configure_logging(resolved_settings.log_level)

    registry = profile_registry or ProfileRegistry(
        profile_root=resolved_settings.profile_root,
        workspace_root=resolved_settings.workspace_root,
        allow_legacy_references=True,
    )
    if profile_registry is None:
        registry.load_all(strict=False)

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        worker_task = (
            asyncio.create_task(worker.run_forever(), name="agent-inline-worker")
            if resolved_settings.inline_worker
            else None
        )
        try:
            yield
        finally:
            if worker_task is not None:
                worker.request_stop()
                await worker_task

    application = FastAPI(
        title="Zhenghua Agent Service",
        version=__version__,
        description="Independent drawing-agent control plane and runtime foundation.",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.profile_registry = registry
    runs: RunRepository
    events: EventRepository
    artifacts: ArtifactRepository
    proposals: ProposalSink
    queue: RunQueue
    checkpoints: CheckpointStore
    source_documents: SourceDocumentProvider
    result_data_repository: ResultDataRepository
    correction_data: CorrectionDataRepository
    candidates: CandidateRepository
    evals: EvalRepository
    traces: TraceStore
    supabase = None
    project_assets = None
    if resolved_settings.persistence_backend == "supabase":
        if not resolved_settings.supabase_configured:
            raise ValueError(
                "Supabase persistence requires AGENT_SUPABASE_URL and AGENT_SUPABASE_SERVICE_ROLE_KEY."
            )
        supabase = SupabaseClient(
            base_url=resolved_settings.supabase_url or "",
            service_role_key=resolved_settings.supabase_service_role_key or "",
            timeout_seconds=resolved_settings.supabase_request_timeout_seconds,
        )
        runs = SupabaseRunRepository(supabase)
        events = SupabaseEventRepository(supabase)
        artifacts = SupabaseArtifactRepository(supabase)
        proposals = SupabaseProposalRepository(supabase)
        queue = SupabaseRunQueue(supabase)
        checkpoints = SupabaseCheckpointStore(supabase)
        source_documents = SupabaseSourceDocumentProvider(
            supabase,
            cache_root=resolved_settings.workspace_root / "services" / "agent" / ".runtime" / "sources",
        )
        project_assets = SupabaseProjectAssetStore(
            supabase,
            bucket=resolved_settings.supabase_storage_bucket,
        )
        result_data_repository = SupabaseResultDataRepository(
            supabase,
            profiles=registry,
            drawing_cache_root=resolved_settings.workspace_root
            / "services"
            / "agent"
            / ".runtime"
            / "drawings",
        )
        correction_data = SupabaseCorrectionDataRepository(
            supabase,
            cache_root=resolved_settings.workspace_root / "services" / "agent" / ".runtime" / "corrections",
        )
        candidates = SupabaseCandidateRepository(supabase)
        evals = SupabaseEvalRepository(supabase)
        traces = SupabaseTraceStore(supabase)
    else:
        runs = InMemoryRunRepository()
        events = InMemoryEventRepository()
        artifacts = InMemoryArtifactRepository()
        proposals = InMemoryProposalRepository()
        queue = InMemoryRunQueue()
        checkpoints = InMemoryCheckpointStore()
        source_documents = InMemorySourceDocumentProvider()
        result_data_repository = InMemoryResultDataRepository()
        correction_data = InMemoryCorrectionDataProvider()
        candidates = InMemoryCandidateRepository()
        evals = InMemoryEvalRepository()
        traces = InMemoryTraceStore()
    run_control = RunControlService(
        runs=runs,
        events=events,
        artifacts=artifacts,
        queue=queue,
    )
    application.state.run_control = run_control
    application.state.proposal_repository = proposals
    application.state.checkpoint_store = checkpoints
    application.state.supabase = supabase
    application.state.project_assets = project_assets
    worker = AgentWorker(
        runs=runs,
        queue=queue,
        publisher=run_control.publisher,
        artifacts=artifacts,
        proposals=proposals,
        result_data=result_data_repository,
    )
    result_data_tool = ControlledResultDataTool(
        repository=result_data_repository,
        correction_data=correction_data,
    )
    model_gateway = None
    profile_detection_tool: ProfileDetectionTool | None = None
    if resolved_settings.model_configured:
        model_gateway = OpenAICompatibleModelGateway(
            base_url=resolved_settings.model_base_url or resolved_settings.model_chat_completions_url or "",
            chat_completions_url=resolved_settings.model_chat_completions_url,
            api_key=resolved_settings.model_api_key,
            default_model=resolved_settings.default_model or "",
            timeout_seconds=resolved_settings.model_timeout_seconds,
            retry_policy=RetryPolicy(
                max_retries=resolved_settings.model_max_retries,
                initial_backoff_seconds=resolved_settings.model_retry_initial_backoff_seconds,
                max_backoff_seconds=resolved_settings.model_retry_max_backoff_seconds,
            ),
            trace_store=traces,
        )
        profile_detection_runtime = create_profile_detection_runtime(
            settings=resolved_settings,
            registry=registry,
            gateway=model_gateway,
        )
        profile_detection_tool = ProfileDetectionTool(profile_detection_runtime)
    worker.register(
        RunType.FULL_EXTRACTION,
        FullExtractionRunExecutor(
            settings=resolved_settings,
            profiles=registry,
            documents=source_documents,
            artifacts=artifacts,
            publisher=run_control.publisher,
            runtime_root=resolved_settings.workspace_root / "services" / "agent" / ".runtime",
            profile_detection=profile_detection_tool,
            project_assets=project_assets,
        ),
    )
    correction_stages = (
        build_extraction_stage_dispatcher(resolved_settings)
        if resolved_settings.model_configured
        else ProfileBoundStageDispatcher()
    )
    correction_executor = CorrectionWorkflowExecutor(
        data=correction_data,
        stages=ScopedExtractionRunner(correction_stages),
        model_name=resolved_settings.default_model or "unconfigured",
    )
    worker.register(RunType.SCOPED_CORRECTION, correction_executor)
    worker.register(RunType.SCOPED_REMEDIATION, correction_executor)
    application.state.source_documents = source_documents
    application.state.correction_data = correction_data
    application.state.result_data_repository = result_data_repository
    application.state.result_data_tool = result_data_tool
    application.state.agent_worker = worker
    application.state.candidate_repository = candidates
    application.state.eval_repository = evals
    if model_gateway is not None:
        prompt_root = resolved_settings.workspace_root / "services" / "agent" / "prompts"
        improvement_workflow = ImprovementWorkflow(
            profiles=registry,
            diagnoser=ImprovementDiagnoserAgent(
                gateway=model_gateway,
                prompt_path=prompt_root / "improvement_diagnosis.md",
            ),
            patch_builder=ProfilePatchBuilderAgent(
                gateway=model_gateway,
                prompt_path=prompt_root / "profile_patch_builder.md",
            ),
            judge=EvaluationJudgeAgent(
                gateway=model_gateway,
                prompt_path=prompt_root / "evaluation_judge.md",
            ),
            sandbox=ProfileSandbox(default_sandbox_root(resolved_settings.workspace_root)),
            candidates=candidates,
        )
        worker.register(
            RunType.IMPROVEMENT_CANDIDATE,
            ImprovementRunExecutor(
                result_data=result_data_repository,
                workflow=improvement_workflow,
                artifacts=artifacts,
            ),
        )
        workflows = WorkflowRegistry()
        register_default_supervisor_handlers(
            workflows,
            run_control,
            registry,
            result_data_tool,
            proposals,
        )
        application.state.supervisor_runtime = {
            "agent": SupervisorAgent(
                gateway=model_gateway,
                prompt_path=resolved_settings.workspace_root
                / "services"
                / "agent"
                / "prompts"
                / "supervisor.md",
            ),
            "workflows": workflows,
        }
        if profile_detection_tool is not None:
            application.state.supervisor_conversations = SupervisorConversationService(
                agent=application.state.supervisor_runtime["agent"],
                workflows=workflows,
                profiles=registry,
                detection=profile_detection_tool,
                memory=ShortTermConversationStore(),
                model_name=resolved_settings.default_model or "unconfigured",
                attachment_root=(
                    resolved_settings.workspace_root / "services" / "agent" / ".runtime" / "conversations"
                ),
            )
        application.state.improvement_workflow = improvement_workflow
    application.include_router(health_router)
    application.include_router(profiles_router)
    application.include_router(runs_router)
    application.include_router(supervisor_router)
    application.include_router(improvement_router)
    application.include_router(proposals_router)
    return application


app = create_app()
