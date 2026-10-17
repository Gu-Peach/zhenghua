from __future__ import annotations

from pathlib import Path

from src.config import AgentSettings
from src.harness.model_gateway import ModelGateway, ModelRequest, ModelResponse, OpenAICompatibleModelGateway
from src.harness.retry import RetryPolicy
from src.profiles.registry import ProfileRegistry

from .models import ProfileError
from .service import ProfileAgent
from .store import DraftStore


class _UnconfiguredModel:
    async def invoke(self, request: ModelRequest) -> ModelResponse:
        raise ProfileError("MODEL_NOT_CONFIGURED", "规则助手模型未配置；草稿读取、确认和导出仍可使用", 503)


def create_profile_agent(
    settings: AgentSettings | None = None,
    *,
    state_root: Path | None = None,
    gateway: ModelGateway | None = None,
    registry: ProfileRegistry | None = None,
) -> ProfileAgent:
    """Build a standalone agent without opening a port, business DB or production rule writer."""
    config = settings or AgentSettings.from_env()
    if registry is None:
        registry = ProfileRegistry(
            profile_root=config.profile_root,
            workspace_root=config.workspace_root,
            allow_legacy_references=True,
        )
        registry.load_all(strict=False)
    if gateway is None:
        if config.model_configured:
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
        else:
            gateway = _UnconfiguredModel()
    store = DraftStore(state_root or config.workspace_root / ".runtime" / "profile-agent", registry)
    return ProfileAgent(store, gateway, max_tokens=config.model_max_tokens or 8000)
