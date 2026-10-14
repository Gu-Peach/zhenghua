from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from time import perf_counter
from typing import Any, TypeVar, cast
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel

from src.domain.enums import AgentStage, ErrorCode
from src.domain.errors import AgentServiceError
from src.agent.extraction_agent.domain.models.image_payload import ImagePayload
from src.domain.models.stage_persistence import StageInput, StageItem, digest
from src.agent.extraction_agent.domain.models.wiring import WireRecord
from src.agent.extraction_agent.graphs.document_extraction.state import GraphState
from src.infrastructure.supabase_stage_repository import SupabaseStageRepository
from src.agent.extraction_agent.application.document_extraction.runtime import GraphRuntime

T = TypeVar("T", bound=BaseModel)
STAGES = (
    AgentStage.RENDER,
    AgentStage.PAGE_CLASSIFICATION,
    AgentStage.PAGE_SCAN,
    AgentStage.VALIDATION,
)


class DurableExtractionSession:
    """Database barriers around the existing deterministic document algorithms."""

    def __init__(
        self, repository: SupabaseStageRepository, inputs: StageInput, output_dir: Path, pdf_path: Path
    ) -> None:
        self.repository, self.inputs, self.output_dir = repository, inputs, output_dir
        self.pdf_path = pdf_path

    async def load_page(self, number: int) -> dict[str, Any] | None:
        item = await self.repository.load_item(self.inputs.run_id, AgentStage.PAGE_SCAN, f"pdf-page:{number}")
        return item.result if item else None

    async def commit_page(self, number: int, state: GraphState) -> None:
        """Commit completed page facts separately from raw model-response caches."""
        from src.agent.extraction_agent.graphs.document_extraction.page_extraction import page_result

        snapshot = await self._snapshot(AgentStage.PAGE_SCAN, state)
        result = page_result(cast(GraphState, snapshot), number)
        scan = result.get("scan") or {}
        page = result["page"]
        await self.repository.commit_item(
            StageItem(
                run_id=self.inputs.run_id,
                stage=AgentStage.PAGE_SCAN,
                item_id=f"pdf-page:{number}",
                input_fingerprint=await self._fingerprint(AgentStage.PAGE_SCAN, f"pdf-page:{number}"),
                result=result,
                needs_review=bool(scan.get("needs_review")),
                status="skipped" if page.get("blank") or page.get("is_non_wiring") else "completed",
            )
        )

    async def model_result(
        self, stage: AgentStage, item_id: str, model: type[T], invoke: Callable[[], Awaitable[T]]
    ) -> T:
        fingerprint = await self._fingerprint(stage, item_id)
        cached = await self.repository.load_item(self.inputs.run_id, stage, item_id, model_cache=True)
        if cached:
            if cached.input_fingerprint != fingerprint:
                raise ValueError("Frozen model input mismatch.")
            return model.model_validate(cached.result)
        started = perf_counter()
        try:
            result = await invoke()
        except Exception as exc:
            await self.repository.record_attempt(
                self.inputs.run_id,
                stage,
                item_id,
                {
                    "input_fingerprint": fingerprint,
                    "error_type": type(exc).__name__,
                    "duration_seconds": perf_counter() - started,
                },
            )
            raise
        await self.repository.commit_item(
            StageItem(
                run_id=self.inputs.run_id,
                stage=stage,
                item_id=item_id,
                input_fingerprint=fingerprint,
                result=result.model_dump(mode="json"),
                needs_review=bool(getattr(result, "needs_review", False)),
                metrics={
                    "model": self.inputs.configuration.get("model"),
                    "duration_seconds": perf_counter() - started,
                    "usage": None,
                    "cost": None,
                    "model_attempts": None,
                },
            ),
            model_cache=True,
        )
        return result

    async def _fingerprint(self, stage: AgentStage, item_id: str) -> str:
        index = STAGES.index(stage)
        prior = await self.repository.load_snapshot(self.inputs.run_id, STAGES[index - 1]) if index else None
        if index and not prior:
            raise ValueError("Missing frozen upstream model input.")
        return digest(
            {
                "root": self.inputs.fingerprint,
                "stage": stage.value,
                "item_id": item_id,
                "upstream_result_digest": prior.result_digest if prior else None,
            }
        )

    async def run_node(
        self,
        stage: AgentStage,
        node: Callable[[GraphState], Awaitable[dict[str, Any]]],
        initial: GraphState,
        runtime: GraphRuntime,
    ) -> dict[str, Any]:
        existing = await self.repository.load_snapshot(self.inputs.run_id, stage)
        if existing:
            restored = await self._hydrate(existing.snapshot, runtime)
            if stage == AgentStage.VALIDATION:
                await node(restored)  # Regenerate exports from DB, never model calls.
            return dict(restored)
        index = STAGES.index(stage)
        await self.repository.start_stage(self.inputs.run_id, stage)
        if index:
            prior = await self.repository.load_snapshot(self.inputs.run_id, STAGES[index - 1])
            if prior is None:
                raise ValueError("Upstream snapshot has not committed.")
            state = await self._hydrate(prior.snapshot, runtime)
        else:
            state = initial
        # Local checkpoints may be diagnostics, never inputs to a durable run.
        for filename in (
            "page-classifications.json",
            "page-scan-checkpoint.json",
            "wire-units-checkpoint.json",
            "cross-page-checkpoint.json",
        ):
            path = self.output_dir / "agent" / filename
            if path.is_file():
                await asyncio.to_thread(path.unlink)
        update = await node(state)
        state = cast(GraphState, {**state, **update})
        if runtime.extraction_errors:
            raise AgentServiceError(
                ErrorCode.MODEL_SCHEMA_INVALID, "Stage has failed items; downstream is blocked."
            )
        snapshot = await self._snapshot(stage, state)
        await self._commit_items(stage, snapshot)
        await self.repository.seal(self.inputs.run_id, stage, snapshot)
        # Force read-after-commit, rather than returning the computed object.
        sealed = await self.repository.load_snapshot(self.inputs.run_id, stage)
        if sealed is None:
            raise ValueError("Commit receipt exists without a readable snapshot.")
        return dict(await self._hydrate(sealed.snapshot, runtime))

    async def _snapshot(self, stage: AgentStage, state: GraphState) -> dict[str, Any]:
        def plain(value: Any) -> Any:
            if isinstance(value, BaseModel):
                return plain(value.model_dump(mode="json"))
            if isinstance(value, dict):
                return {
                    k: plain(v)
                    for k, v in value.items()
                    if k not in {"pdf_path", "output_path", "image_path", "source_image"}
                }
            if isinstance(value, list):
                return [plain(v) for v in value]
            return value

        snapshot: dict[str, Any] = plain(dict(state))
        pages = snapshot.get("pages", [])
        used_business_pages: set[tuple[str, str]] = set()
        if stage in {AgentStage.RENDER, AgentStage.PAGE_CLASSIFICATION}:
            for page, local in zip(pages, state.get("pages", []), strict=True):
                content = await asyncio.to_thread(Path(local["image_path"]).read_bytes)
                checksum = "sha256:" + hashlib.sha256(content).hexdigest()
                number = int(page["page_number"])
                if stage == AgentStage.RENDER:
                    path = (
                        f"projects/{self.inputs.project_id}/runs/{self.inputs.run_id}/"
                        f"render/{number}/{checksum[7:]}.png"
                    )
                else:
                    function = str(page.get("function") or "UNKNOWN")
                    workspace = str(
                        uuid5(NAMESPACE_URL, f"zhenghua:{self.inputs.run_id}:workspace:{function}")
                    )
                    drawing = str(uuid5(NAMESPACE_URL, f"zhenghua:{self.inputs.run_id}:drawing:{number}"))
                    page.update(
                        {
                            "workspace_id": workspace,
                            "drawing_id": drawing,
                            "workspace_page": str(page["internal_page"])
                            if page.get("internal_page")
                            else None,
                        }
                    )
                    key = (workspace, str(page["workspace_page"]))
                    if page["workspace_page"] and key in used_business_pages:
                        page["workspace_page"] = None
                        page["needs_review"] = True
                    used_business_pages.add(key)
                    path = (
                        f"projects/{self.inputs.project_id}/workspaces/{workspace}/"
                        f"drawings/{drawing}/images/{checksum[7:]}.png"
                    )
                bucket = str(self.inputs.configuration.get("bucket", "project-assets"))
                await self.repository.client.upload(
                    bucket=bucket, object_path=path, content=content, content_type="image/png"
                )
                page["image_ref"] = {"storage_bucket": bucket, "storage_path": path, "checksum": checksum}
        # This exact coverage inventory is derived from normalized connections,
        # not from the tasks the planner happened to emit.
        sources: dict[str, Any] = {}
        for unit in snapshot.get("wire_units", {}).values():
            for connection in unit.get("connections", []):
                connection_id = connection.get("connection_id") or connection.get("local_connection_id")
                if connection_id:
                    sources[str(connection_id)] = connection
        snapshot["planning_sources"] = sources
        return snapshot

    async def _commit_items(self, stage: AgentStage, snapshot: dict[str, Any]) -> None:
        if stage == AgentStage.PAGE_SCAN:
            # Page workflow commits immediately, before it advances to the next page.
            return
        items: list[tuple[str, dict[str, Any], bool]] = []
        if stage in {AgentStage.RENDER, AgentStage.PAGE_CLASSIFICATION, AgentStage.PAGE_SCAN}:
            for page in snapshot["pages"]:
                number = int(page["page_number"])
                skipped = stage != AgentStage.RENDER and (
                    page.get("blank") or (stage == AgentStage.PAGE_SCAN and page.get("is_non_wiring"))
                )
                result = {"page": page}
                if stage == AgentStage.PAGE_CLASSIFICATION:
                    result["classification"] = snapshot.get("page_classifications", {}).get(str(number))
                elif stage == AgentStage.PAGE_SCAN:
                    result["scan"] = snapshot.get("page_scan_results", {}).get(str(number))
                items.append((f"pdf-page:{number}", result, bool(skipped)))
        elif stage == AgentStage.BUILD_CROSS_PAGE_TASKS:
            for connection_id, connection in snapshot["planning_sources"].items():
                items.append(
                    (
                        connection_id,
                        {
                            "connection": connection,
                            "tasks": [
                                t
                                for t in snapshot.get("cross_page_tasks", [])
                                if t["connection_id"] == connection_id
                            ],
                        },
                        False,
                    )
                )
        elif stage == AgentStage.CROSS_PAGE_COMPLETION:
            for task in snapshot.get("cross_page_tasks", []):
                result = snapshot.get("cross_page_results", {}).get(task["task_id"])
                items.append((task["task_id"], {"task": task, "completion": result}, result is None))
        else:
            items.append(("validation", snapshot, False))
        for item_id, result, skipped in items:
            await self.repository.commit_item(
                StageItem(
                    run_id=self.inputs.run_id,
                    stage=stage,
                    item_id=item_id,
                    input_fingerprint=await self._fingerprint(stage, item_id),
                    result=result,
                    status="skipped" if skipped else "completed",
                    needs_review=bool(result.get("page", {}).get("needs_review"))
                    or (stage == AgentStage.CROSS_PAGE_COMPLETION and skipped),
                )
            )

    async def _hydrate(self, snapshot: dict[str, Any], runtime: GraphRuntime) -> GraphState:
        state = cast(GraphState, json.loads(json.dumps(snapshot)))
        state["pdf_path"] = str(self.pdf_path)
        state["output_path"] = str(self.output_dir)
        runtime.payload_by_path.clear()
        index_pages = {int(p["pdf_page"]): p for p in state.get("drawing_index", {}).get("pages", [])}
        for page in state.get("pages", []):
            ref = page.get("image_ref")
            if not ref:
                raise ValueError("A durable page must have a private image reference.")
            number = int(page["page_number"])
            path = self.output_dir / "cache" / f"{number}-{ref['checksum'][7:]}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            content = await self.repository.client.download(
                bucket=ref["storage_bucket"], object_path=ref["storage_path"]
            )
            if "sha256:" + hashlib.sha256(content).hexdigest() != ref["checksum"]:
                raise ValueError("Private image checksum mismatch.")
            await asyncio.to_thread(path.write_bytes, content)
            page["image_path"] = str(path)
            runtime.payload_by_path[str(path.resolve())] = ImagePayload(
                name=path.name,
                mime_type="image/png",
                content=b"",
                page_number=number,
                page_text=index_pages.get(number, {}).get("text"),
                blank=bool(page.get("blank")),
            )
        state["wiring_records"] = {
            key: [WireRecord.model_validate(record) for record in values]
            for key, values in state.get("wiring_records", {}).items()
        }
        return state
