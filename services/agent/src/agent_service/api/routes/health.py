from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ...infrastructure.supabase_client import SupabaseClient

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    return {
        "status": "ok",
        "service": "agent",
        "version": request.app.version,
        "environment": settings.environment,
    }


@router.get("/health/ready", response_model=None)
async def ready(request: Request) -> JSONResponse:
    settings = request.app.state.settings
    registry = request.app.state.profile_registry
    checks: dict[str, dict[str, Any]] = {}

    runtime_ready = settings.persistence_backend == "memory" or settings.supabase_configured
    checkpoint_ready = settings.checkpoint_backend == "memory" or settings.supabase_configured
    checks["runtime"] = {
        "ready": runtime_ready and checkpoint_ready,
        "persistence_backend": settings.persistence_backend,
        "checkpoint_backend": settings.checkpoint_backend,
        "reason": None
        if runtime_ready and checkpoint_ready
        else "Supabase URL and service-role key are required for the Supabase backend.",
    }
    supabase_client = getattr(request.app.state, "supabase", None)
    supabase_connected = settings.persistence_backend != "supabase"
    if settings.persistence_backend == "supabase" and isinstance(supabase_client, SupabaseClient):
        try:
            await supabase_client.select("projects", params={"select": "id", "limit": "0"})
            supabase_connected = True
        except Exception:
            supabase_connected = False
    checks["supabase"] = {
        "ready": settings.persistence_backend != "supabase"
        or (settings.supabase_configured and supabase_connected),
        "configured": settings.supabase_configured,
        "connected": supabase_connected,
        "bucket": settings.supabase_storage_bucket,
        "reason": None
        if settings.persistence_backend != "supabase" or settings.supabase_configured
        else "Agent Supabase configuration is incomplete.",
    }
    checks["profiles"] = {
        "ready": not registry.errors and bool(registry.list_profiles()),
        "count": len(registry.list_profiles()),
        "errors": list(registry.errors),
    }
    checks["model"] = {
        "ready": settings.model_configured,
        "model": settings.default_model,
        "base_url_configured": bool(settings.model_base_url),
        "endpoint_configured": bool(settings.model_chat_completions_url or settings.model_base_url),
        "reason": None if settings.model_configured else "Model endpoint and model name are required.",
    }

    is_ready = all(check["ready"] for check in checks.values())
    return JSONResponse(
        status_code=200 if is_ready else 503,
        content={"status": "ready" if is_ready else "not_ready", "checks": checks},
    )
