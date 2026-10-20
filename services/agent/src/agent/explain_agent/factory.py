from __future__ import annotations

from src.agent.extraction_agent.infrastructure.document.model_traces import LocalModelTraceStore
from src.config import AgentSettings
from src.harness.model_gateway import ModelGateway, OpenAICompatibleModelGateway
from src.harness.retry import RetryPolicy
from src.infrastructure.supabase_client import SupabaseClient

from .diagnostics import ExplainDiagnosticGateway
from .repository import ExplanationRepository, SupabaseExplanationRepository
from .service import ExplainAgent


def create_explain_agent(
    settings: AgentSettings | None = None,
    *,
    repository: ExplanationRepository | None = None,
    gateway: ModelGateway | None = None,
    max_sessions: int = 128,
) -> ExplainAgent:
    """Build an independently callable agent, with injectable offline dependencies."""
    config = settings or AgentSettings.from_env()
    if repository is None:
        if not config.supabase_configured:
            raise ValueError("Explain Agent requires Supabase configuration or an injected repository")
        repository = SupabaseExplanationRepository(
            SupabaseClient(
                base_url=config.supabase_url or "",
                service_role_key=config.supabase_service_role_key or "",
                timeout_seconds=config.supabase_request_timeout_seconds,
            ),
            bucket=config.supabase_storage_bucket,
        )
    if gateway is None:
        if not config.model_configured:
            raise ValueError("Explain Agent requires model configuration or an injected gateway")
        gateway = OpenAICompatibleModelGateway(
            base_url=config.model_base_url or config.model_chat_completions_url or "",
            chat_completions_url=config.model_chat_completions_url,
            default_model=config.default_model or "",
            api_key=config.model_api_key,
            timeout_seconds=config.model_timeout_seconds,
            retry_policy=RetryPolicy(
                max_retries=config.model_max_retries,
                initial_backoff_seconds=config.model_retry_initial_backoff_seconds,
                max_backoff_seconds=config.model_retry_max_backoff_seconds,
            ),
        )
        gateway = ExplainDiagnosticGateway(
            gateway,
            LocalModelTraceStore(config.workspace_root / ".runtime" / "explain-diagnostics"),
            config.default_model or "",
        )
    return ExplainAgent(
        repository, gateway, max_sessions=max_sessions, max_tokens=config.model_max_tokens or 2000
    )
