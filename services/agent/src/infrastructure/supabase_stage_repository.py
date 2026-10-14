from __future__ import annotations

from typing import Any
from uuid import uuid4

from src.domain.enums import AgentStage, ErrorCode
from src.domain.errors import AgentServiceError
from src.domain.models.stage_persistence import (
    RunFinalizationReceipt,
    RunLease,
    StageCommitReceipt,
    StageInput,
    StageItem,
    StageManifest,
)
from src.infrastructure.run_lease_context import current_run_lease
from src.infrastructure.supabase_client import SupabaseClient


class SupabaseStageRepository:
    """Fenced database stage operations; large images remain in private Storage."""

    def __init__(self, client: SupabaseClient, *, lease_seconds: int = 300) -> None:
        self.client = client
        self.owner = f"agent-{uuid4()}"
        self.lease_seconds = lease_seconds

    async def claim(self) -> RunLease | None:
        value = await self.client.rpc(
            "claim_durable_agent_run", {"worker_id": self.owner, "lease_seconds": self.lease_seconds}
        )
        return RunLease.model_validate(value) if value else None

    def token(self, run_id: str) -> dict[str, Any]:
        lease = current_run_lease.get()
        if lease is None or lease.run_id != run_id:
            raise AgentServiceError(ErrorCode.CHECKPOINT_CONFLICT, "No current run lease.")
        return lease.model_dump(mode="json")

    async def action(self, lease: RunLease, action: str, value: dict[str, Any] | None = None) -> Any:
        return await self.client.rpc(
            "gate_a_lease_action",
            {
                "target": lease.run_id,
                "token": lease.model_dump(mode="json"),
                "action": action,
                "value": value or {},
            },
        )

    async def initialize(self, inputs: StageInput) -> StageInput:
        value = await self.client.rpc(
            "gate_a_initialize",
            {
                "target": inputs.run_id,
                "token": self.token(inputs.run_id),
                "input_value": inputs.model_dump(mode="json"),
            },
        )
        return StageInput.model_validate(value)

    async def start_stage(self, run_id: str, stage: AgentStage) -> None:
        await self.client.rpc("gate_a_start_stage", {
            "target": run_id, "token": self.token(run_id), "stage_name": stage.value,
        })

    async def load_input(self, run_id: str) -> StageInput | None:
        value = await self._artifact(run_id, f"{run_id}:durable-input")
        return StageInput.model_validate(value) if value else None

    async def load_item(
        self, run_id: str, stage: AgentStage, item_id: str, *, model_cache: bool = False
    ) -> StageItem | None:
        kind = "gate_a_model" if model_cache else "gate_a_item"
        value = await self._artifact(run_id, f"{run_id}:{kind}:{stage.value}:{item_id}")
        return StageItem.model_validate(value) if value else None

    async def commit_item(self, item: StageItem, *, model_cache: bool = False) -> StageCommitReceipt:
        receipt = StageCommitReceipt.model_validate(
            await self.client.rpc(
                "gate_a_commit_item",
                {
                    "target": item.run_id,
                    "token": self.token(item.run_id),
                    "item": item.model_dump(mode="json"),
                    "model_cache": model_cache,
                },
            )
        )
        if receipt.result_digest != item.result_digest or receipt.conflict:
            raise AgentServiceError(ErrorCode.CHECKPOINT_CONFLICT, "Canonical stage result conflict.")
        return receipt

    async def record_attempt(
        self, run_id: str, stage: AgentStage, item_id: str, details: dict[str, Any]
    ) -> None:
        await self.client.rpc(
            "gate_a_runtime_write",
            {
                "target": run_id,
                "token": self.token(run_id),
                "kind": "artifact",
                "value": {
                    "artifact_id": f"{run_id}:attempt:{uuid4()}",
                    "agent_run_id": run_id,
                    "kind": "gate_a_attempt",
                    "stage": stage.value,
                    "item_id": item_id,
                    **details,
                },
            },
        )

    async def seal(self, run_id: str, stage: AgentStage, snapshot: dict[str, Any]) -> StageManifest:
        value = await self.client.rpc(
            "gate_a_seal",
            {
                "target": run_id,
                "token": self.token(run_id),
                "stage_name": stage.value,
                "snapshot_value": snapshot,
            },
        )
        return StageManifest.model_validate(value)

    async def load_snapshot(self, run_id: str, stage: AgentStage) -> StageManifest | None:
        value = await self._artifact(run_id, f"{run_id}:gate_a_manifest:{stage.value}:manifest")
        return StageManifest.model_validate(value) if value else None

    async def final_receipt(self, run_id: str) -> RunFinalizationReceipt | None:
        value = await self._artifact(run_id, f"{run_id}:finalized")
        if not value:
            value = await self._artifact(run_id, f"{run_id}:final-receipt")
        return RunFinalizationReceipt.model_validate(value) if value else None

    async def finalize(self, run_id: str) -> RunFinalizationReceipt:
        value = await self.client.rpc("gate_a_finalize", {"target": run_id, "token": self.token(run_id)})
        return RunFinalizationReceipt.model_validate(value)

    async def _artifact(self, run_id: str, artifact_id: str) -> dict[str, Any] | None:
        rows = await self.client.select(
            "agent_artifacts",
            params={
                "agent_run_id": f"eq.{run_id}",
                "artifact_id": f"eq.{artifact_id}",
                "limit": "1",
            },
        )
        return dict(rows[0]["payload"]) if rows else None
