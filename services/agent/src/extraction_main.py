"""Optional shared extraction host; production may run the Worker without an HTTP port."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.agent.extraction_agent.application.incremental_worker import run_worker
from src.config import AgentSettings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = AgentSettings.from_env()
    task = asyncio.create_task(run_worker(settings)) if settings.inline_worker else None
    app.state.worker = task
    try:
        yield
    finally:
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="Extraction Agent", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, object]:
    task = getattr(app.state, "worker", None)
    return {"service": "extraction_agent", "worker_running": bool(task and not task.done())}
