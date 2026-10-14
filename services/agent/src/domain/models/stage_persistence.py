"""Durable stage contracts. Model work and durable completion are distinct."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field

from src.domain.enums import AgentStage
from src.domain.models.common import StrictModel, utc_now
from src.domain.models.runs import ProfileRef


def canonical_json(value: Any) -> str:
    """Stable UTF-8 JSON; ordered business arrays are intentionally preserved."""
    if isinstance(value, dict):
        return (
            "{"
            + ",".join(
                json.dumps(str(key), ensure_ascii=False) + ":" + canonical_json(value[key])
                for key in sorted(value)
            )
            + "}"
        )
    if isinstance(value, list):
        return "[" + ",".join(canonical_json(item) for item in value) + "]"
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Non-finite numbers are not valid stage data.")
        if value == 0:
            return "0"
        number = format(Decimal(str(value)), "f")
        return number.rstrip("0").rstrip(".") if "." in number else number
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class RunLease(StrictModel):
    run_id: str
    owner: str
    generation: int = Field(ge=1)
    expires_at: datetime
    mode: Literal["execute", "recover", "cleanup"] = "execute"


class StageInput(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    run_id: str
    project_id: str
    source_document_id: str
    source_checksum: str
    profile: ProfileRef
    page_count: int = Field(ge=1)
    configuration: dict[str, Any]

    @property
    def fingerprint(self) -> str:
        return digest(self.model_dump(mode="json"))


class StageItem(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    run_id: str
    stage: AgentStage
    item_id: str
    input_fingerprint: str
    status: Literal["completed", "skipped"] = "completed"
    needs_review: bool = False
    result: dict[str, Any]
    attempt: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=utc_now)
    metrics: dict[str, Any] = Field(default_factory=dict)

    @property
    def result_digest(self) -> str:
        return digest(self.model_dump(mode="json", exclude={"attempt", "created_at", "metrics"}))


class StageManifest(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    run_id: str
    stage: AgentStage
    upstream_stage: AgentStage | None
    expected_item_ids: list[str]
    item_artifact_ids: list[str]
    counts: dict[str, int]
    ready_for_next_stage: bool
    snapshot: dict[str, Any]
    result_digest: str
    tree_published: bool = False


class StageCommitReceipt(StrictModel):
    artifact_id: str
    result_digest: str
    idempotent: bool = False
    conflict: bool = False


class RunFinalizationReceipt(StrictModel):
    run_id: str
    proposal_id: str
    result_version_id: str
    result_version: int
    status: Literal["SUCCEEDED", "NEEDS_REVIEW"]
    finalized: bool = False
