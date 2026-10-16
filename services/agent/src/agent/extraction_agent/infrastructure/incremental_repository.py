"""Service-role adapter for leased, transactional publication to the three-table schema."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from time import perf_counter
from typing import Any, TypeVar
from urllib.parse import quote
from uuid import uuid4

import httpx
from pydantic import BaseModel

from src.agent.extraction_agent.application.incremental import (
    ExtractionStep,
    PublishedPage,
    _drawing_label,
    published_rows,
)
from src.config import AgentSettings
from src.domain.enums import ErrorCode
from src.domain.errors import AgentServiceError
from src.domain.models.stage_persistence import digest

T = TypeVar("T", bound=BaseModel)


class IncrementalRepository:
    def __init__(self, settings: AgentSettings, http: httpx.AsyncClient) -> None:
        if not settings.supabase_configured:
            raise ValueError("Incremental Worker requires Supabase configuration")
        self.settings, self.http = settings, http

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = {
            "apikey": self.settings.supabase_service_role_key or "",
            "Authorization": f"Bearer {self.settings.supabase_service_role_key}",
        }
        headers.update(kwargs.pop("headers", {}))
        for attempt in range(3):
            try:
                response = await self.http.request(
                    method, f"{self.settings.supabase_url}{path}", headers=headers, **kwargs
                )
            except httpx.TransportError:
                if attempt == 2:
                    raise AgentServiceError(
                        ErrorCode.PERSISTENCE_UNAVAILABLE,
                        "Extraction storage transport unavailable",
                        retryable=True,
                    ) from None
            else:
                if response.status_code < 400:
                    return response
                if response.status_code < 500 or attempt == 2:
                    raise AgentServiceError(
                        ErrorCode.CHECKPOINT_CONFLICT
                        if response.status_code == 409
                        else ErrorCode.PERSISTENCE_UNAVAILABLE,
                        f"Extraction storage request rejected ({response.status_code})",
                        retryable=response.status_code >= 500,
                        details={"http_status": response.status_code},
                    )
            await asyncio.sleep(0.5 * (attempt + 1))
        raise AgentServiceError(ErrorCode.PERSISTENCE_UNAVAILABLE, "Extraction storage unavailable")

    async def rpc(self, name: str, value: dict[str, Any]) -> Any:
        return (await self.request("POST", f"/rest/v1/rpc/{name}", json=value)).json()

    async def artifact(self, run: str, item: str) -> dict[str, Any] | None:
        response = await self.request(
            "GET",
            "/rest/v1/agent_artifacts",
            params={
                "artifact_id": f"eq.simple:{run}:{item}",
                "agent_run_id": f"eq.{run}",
                "select": "payload",
                "limit": "1",
            },
        )
        rows = response.json()
        return rows[0]["payload"] if rows else None

    async def put(self, bucket: str, path: str, content: bytes, mime: str) -> None:
        await self.request(
            "POST",
            f"/storage/v1/object/{quote(bucket, safe='')}/{quote(path, safe='/')}",
            content=content,
            headers={"Content-Type": mime, "x-upsert": "true"},
        )

    async def get(self, bucket: str, path: str) -> bytes:
        return (
            await self.request("GET", f"/storage/v1/object/{quote(bucket, safe='')}/{quote(path, safe='/')}")
        ).content


class IncrementalSession:
    """Duck-compatible with the existing durable session, without legacy table writes."""

    incremental = True

    def __init__(self, repository: IncrementalRepository, job: dict[str, Any], worker: str) -> None:
        self.repository, self.job, self.worker = repository, job, worker
        self.run = job["run"]["id"]
        self.project = job["project"]["id"]
        self.token = job["lease"]["token"]
        self.profile = job["run"]["profile"]
        self.lost = False

    async def commit(self, key: str, step: ExtractionStep) -> None:
        if self.lost:
            raise AgentServiceError(ErrorCode.CHECKPOINT_CONFLICT, "Extraction lease was replaced")
        await self.repository.rpc(
            "commit_simple_extraction",
            {
                "run": self.run,
                "worker": self.worker,
                "token": self.token,
                "item_key": key,
                "value": {
                    key: value for key, value in step.model_dump(mode="json").items() if value is not None
                },
            },
        )

    async def run_node(self, stage: Any, invoke: Any, state: Any, runtime: Any) -> Any:
        started = perf_counter()
        result = await invoke(state)
        key = f"stage:{stage}"
        if not await self.repository.artifact(self.run, key):
            await self.commit(
                key,
                ExtractionStep(
                    kind="cache",
                    stage=str(stage),
                    metrics={"duration_seconds": perf_counter() - started, "profile": self.profile},
                ),
            )
        return result

    async def model_result(
        self, stage: Any, item_id: str, model: type[T], invoke: Callable[[], Awaitable[T]]
    ) -> T:
        key = f"model:{stage}:{item_id}"
        cached = await self.repository.artifact(self.run, key)
        if cached:
            return model.model_validate(cached["snapshot"])
        started = perf_counter()
        try:
            result = await invoke()
        except Exception as exc:
            await self.commit(
                f"attempt:{stage}:{item_id}:{uuid4()}",
                ExtractionStep(
                    kind="cache",
                    stage=str(stage),
                    metrics={
                        "error_type": type(exc).__name__,
                        "duration_seconds": perf_counter() - started,
                        "item_id": item_id,
                        "profile": self.profile,
                    },
                ),
            )
            raise
        await self.commit(
            key,
            ExtractionStep(
                kind="cache",
                stage=str(stage),
                snapshot=result.model_dump(mode="json"),
                metrics={
                    "duration_seconds": perf_counter() - started,
                    "item_id": item_id,
                    "profile": self.profile,
                },
            ),
        )
        return result

    def page(self, value: dict[str, Any], status: str) -> PublishedPage:
        number = int(value["page_number"])
        return PublishedPage(
            pdf_page_number=number,
            workspace_code=str(value.get("function") or ""),
            drawing_page=_drawing_label(value),
            status=status,
            image_path=f"projects/{self.project}/runs/{self.run}/pages/{number}.png",
        )

    async def publish_page(self, value: dict[str, Any], kind: str) -> None:
        number = int(value["page_number"])
        key = f"{kind}:{number}"
        if await self.repository.artifact(self.run, key):
            return
        page = self.page(value, kind)
        if kind == "rendered":
            content = await asyncio.to_thread(Path(value["image_path"]).read_bytes)
            await self.repository.put(page.image_bucket, page.image_path, content, "image/png")
        await self.commit(
            key,
            ExtractionStep(kind=kind, stage="render" if kind == "rendered" else "classification", page=page),
        )

    async def publish_rows(self, state: dict[str, Any], number: int, kind: str, item: str) -> None:
        key = f"{kind}:{number}:{item}"
        if await self.repository.artifact(self.run, key):
            return
        page = next(p for p in state["pages"] if p["page_number"] == number)
        rows = published_rows(
            state, project_id=self.project, run_id=self.run, profile=self.profile, number=number
        )
        await self.commit(key, ExtractionStep(kind=kind, stage=kind, page=self.page(page, kind), rows=rows))

    async def load_page(self, number: int) -> dict[str, Any] | None:
        cached = await self.repository.artifact(self.run, f"page:{number}")
        return cached.get("snapshot") if cached else None

    async def commit_page(self, number: int, state: dict[str, Any]) -> None:
        from src.agent.extraction_agent.graphs.document_extraction.page_extraction import page_result

        if await self.load_page(number):
            return
        snapshot = page_result(state, number)
        page = next(p for p in state["pages"] if p["page_number"] == number)
        status = (
            "skipped"
            if page.get("blank") or page.get("is_non_wiring")
            else ("needs_review" if (snapshot.get("scan") or {}).get("needs_review") else "completed")
        )
        await self.commit(
            f"page:{number}",
            ExtractionStep(
                kind="page_completed",
                stage="page_completed",
                page=self.page(page, status),
                snapshot=snapshot,
                rows=published_rows(
                    state, project_id=self.project, run_id=self.run, profile=self.profile, number=number
                ),
            ),
        )

    async def heartbeat(self) -> None:
        while True:
            await asyncio.sleep(25)
            try:
                valid = await self.repository.rpc(
                    "renew_simple_extraction", {"run": self.run, "worker": self.worker, "token": self.token}
                )
            except Exception:
                self.lost = True
                raise
            if not valid:
                self.lost = True
                raise RuntimeError("Extraction lease was replaced")

    async def configuration(self, value: dict[str, Any]) -> None:
        cached = await self.repository.artifact(self.run, "configuration")
        snapshot = {"fingerprint": digest(value), "configuration": value}
        if cached and cached["snapshot"] != snapshot:
            raise ValueError("Model/workflow configuration changed; resume requires original configuration")
        if not cached:
            await self.commit(
                "configuration", ExtractionStep(kind="cache", stage="configuration", snapshot=snapshot)
            )


class IncrementalTraceStore:
    """Record gateway usage/timing in fenced artifacts, excluding raw provider text."""

    def __init__(self, session: IncrementalSession) -> None:
        self.session = session

    async def append(self, run_id: str, trace: Mapping[str, Any]) -> None:
        if run_id != self.session.run:
            raise ValueError("Trace run mismatch")
        metrics = {
            key: trace[key]
            for key in (
                "kind",
                "agent",
                "model",
                "attempts",
                "duration_seconds",
                "usage",
                "finish_reason",
                "metadata",
                "error_type",
            )
            if key in trace
        }
        await self.session.commit(
            f"trace:{uuid4()}",
            ExtractionStep(kind="cache", stage=str(trace.get("agent") or "model"), metrics=metrics),
        )

    async def list(self, run_id: str) -> list[Mapping[str, Any]]:
        if run_id != self.session.run:
            raise ValueError("Trace run mismatch")
        response = await self.session.repository.request(
            "GET",
            "/rest/v1/agent_artifacts",
            params={
                "agent_run_id": f"eq.{run_id}",
                "artifact_id": f"like.simple:{run_id}:trace:*",
                "select": "payload",
                "order": "created_at.asc",
                "limit": "1000",
            },
        )
        return [row["payload"]["metrics"] for row in response.json()]
