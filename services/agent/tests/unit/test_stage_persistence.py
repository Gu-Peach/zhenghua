from __future__ import annotations

import math

import pytest

from src.domain.enums import AgentStage
from src.domain.models.stage_persistence import StageItem, canonical_json, digest


def test_stage_canonical_json_preserves_order_and_normalizes_numbers() -> None:
    assert canonical_json({"z": [2, 1], "a": -0.0}) == '{"a":0,"z":[2,1]}'
    assert digest({"a": 1.0}) == digest({"a": 1})
    assert digest([1, 2]) != digest([2, 1])
    with pytest.raises(ValueError):
        canonical_json({"bad": math.inf})


def test_metrics_and_transport_attempt_do_not_change_business_digest() -> None:
    item = StageItem(
        run_id="run",
        stage=AgentStage.RENDER,
        item_id="pdf-page:1",
        input_fingerprint="sha256:input",
        result={"page": 1},
    )
    replay = item.model_copy(update={"attempt": 2, "metrics": {"duration_seconds": 100}})
    assert item.result_digest == replay.result_digest
    assert digest(item.model_dump(mode="json")) != digest(replay.model_dump(mode="json"))
    changed = item.model_copy(update={"result": {"page": 2}})
    assert changed.result_digest != item.result_digest
