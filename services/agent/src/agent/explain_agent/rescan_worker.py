"""Leased rescan consumer hosted in the existing independent Worker process."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Any, Literal
from uuid import UUID, uuid4

import httpx
from pydantic import BaseModel, Field

from src.agent.extraction_agent.infrastructure.incremental_repository import IncrementalRepository
from src.config import AgentSettings
from src.domain.models.runs import ProfileRef

from .models import RescanRequest
from .rescan_execution import CandidateSession, execute_rescan
from .rescan_planning import RescanPlanError
from .rescan_targets import RescanTargetError

logger = logging.getLogger(__name__)


class RescanSnapshot(BaseModel):
    pages: list[dict[str, Any]]
    scan_pages: list[dict[str, Any]]
    profile_ref: str
    profile_source: Literal["historical", "project_reference"] = "historical"
    profile_id: UUID | None = None
    name: str = ""


class RescanClaim(BaseModel):
    id: UUID
    project_id: UUID
    created_by: UUID
    conversation_id: UUID
    batch_id: str
    lease_token: UUID
    request: RescanRequest
    profile: ProfileRef
    project_snapshot: RescanSnapshot
    baseline: list[dict[str, Any]] = Field(max_length=1000)
    checkpoint: dict[str, Any] = Field(default_factory=dict)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=6)


async def process_rescan(repository: Any, job: dict[str, Any], settings: AgentSettings) -> None:
    validated = RescanClaim.model_validate(job).model_dump(mode="json")
    session = CandidateSession(repository, validated)

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(25)
            await session.advance()

    task = asyncio.create_task(execute_rescan(session, settings))
    pulse = asyncio.create_task(heartbeat())
    try:
        done, _ = await asyncio.wait({task, pulse}, return_when=asyncio.FIRST_COMPLETED)
        if task in done:
            task.result()
        else:
            pulse.result()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.error("Rescan %s failed (%s)", job["id"], type(exc).__name__)
        with suppress(Exception):
            await session.advance(
                stage="failed",
                error=str(exc)
                if isinstance(exc, (RescanTargetError, RescanPlanError))
                else "重扫未完成，原线表保留。请检查原图、任务选定的规则包和模型配置后重新发起。",
            )
    finally:
        task.cancel()
        pulse.cancel()
        await asyncio.gather(task, pulse, return_exceptions=True)


async def run_rescan_worker(settings: AgentSettings, *, once: bool = False) -> bool:
    handled = False
    worker = f"rescan-{uuid4()}"
    warned = False
    async with httpx.AsyncClient(timeout=settings.supabase_request_timeout_seconds) as http:
        repository = IncrementalRepository(settings, http)
        while True:
            try:
                job = await repository.rpc("claim_connection_rescan", {"worker_name": worker})
            except Exception:
                if once:
                    return False
                if not warned:
                    logger.warning(
                        "Rescan queue unavailable; apply migration 20261018050000. "
                        "Normal extraction remains available."
                    )
                    warned = True
                await asyncio.sleep(30)
                continue
            if job:
                handled = True
                try:
                    await process_rescan(repository, job, settings)
                except Exception as exc:
                    logger.error("Invalid rescan claim (%s)", type(exc).__name__)
                    with suppress(Exception):
                        await repository.rpc(
                            "advance_connection_rescan",
                            {
                                "value": {
                                    "id": job["id"],
                                    "token": job["lease_token"],
                                    "stage": "failed",
                                    "error": "重扫任务配置无效，未修改线表，请重新发起。",
                                }
                            },
                        )
            if once:
                return handled
            if not job:
                await asyncio.sleep(2)
