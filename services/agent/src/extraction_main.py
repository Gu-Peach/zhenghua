"""Shared independent-agent host: optional extraction Worker and authenticated Explain API."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header

from src.agent.explain_agent import ExplainActor, ExplainAgent, create_explain_agent
from src.agent.explain_agent.api import create_explain_router
from src.agent.explain_agent.models import ExplainError
from src.agent.extraction_agent.application.incremental_worker import run_worker
from src.api.dependencies import require_internal_service
from src.config import AgentSettings


def create_app(settings: AgentSettings | None = None, explain_agent: ExplainAgent | None = None) -> FastAPI:
    config = settings or AgentSettings.from_env()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(run_worker(config)) if config.inline_worker else None
        application.state.worker = task
        try:
            yield
        finally:
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    application = FastAPI(title="Independent Agent Service", lifespan=lifespan)
    application.state.settings = config
    cached = explain_agent

    def explanation() -> ExplainAgent:
        nonlocal cached
        if cached is None:
            try:
                cached = create_explain_agent(config)
            except ValueError as exc:
                raise ExplainError("EXPLAIN_NOT_CONFIGURED", "解释服务尚未配置数据库或模型。", 503) from exc
        return cached

    async def actor(
        user: Annotated[UUID, Header(alias="X-Explain-User-Id")],
        _: Annotated[None, Depends(require_internal_service)],
    ) -> ExplainActor:
        return ExplainActor(user_id=user)

    application.include_router(create_explain_router(explanation, actor))

    @application.get("/health")
    async def health() -> dict[str, object]:
        task = getattr(application.state, "worker", None)
        return {"service": "independent_agents", "worker_running": bool(task and not task.done())}

    return application


app = create_app()
