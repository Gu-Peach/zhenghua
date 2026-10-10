from __future__ import annotations

from ..config import AgentSettings
from ..harness.model_gateway import ModelGateway, OpenAICompatibleModelGateway
from ..harness.retry import RetryPolicy
from ..infrastructure.zh_vlm_stages import ZhVlmExtractionStageAdapter
from .extraction_stage_dispatcher import ProfileBoundStageDispatcher


def build_extraction_stage_dispatcher(
    settings: AgentSettings,
    *,
    gateway: ModelGateway | None = None,
) -> ProfileBoundStageDispatcher:
    """Build profile-specific stage adapters using the agent's own model gateway."""
    if not settings.model_configured and gateway is None:
        raise ValueError("Configure AGENT_MODEL_BASE_URL and AGENT_DEFAULT_MODEL before extraction.")
    model_gateway = gateway or OpenAICompatibleModelGateway(
        base_url=settings.model_base_url or settings.model_chat_completions_url or "",
        chat_completions_url=settings.model_chat_completions_url,
        api_key=settings.model_api_key,
        default_model=settings.default_model or "",
        timeout_seconds=settings.model_timeout_seconds,
        retry_policy=RetryPolicy(
            max_retries=settings.model_max_retries,
            initial_backoff_seconds=settings.model_retry_initial_backoff_seconds,
            max_backoff_seconds=settings.model_retry_max_backoff_seconds,
        ),
    )
    dispatcher = ProfileBoundStageDispatcher()
    dispatcher.register("zh_native", ZhVlmExtractionStageAdapter(settings, model_gateway))
    return dispatcher
