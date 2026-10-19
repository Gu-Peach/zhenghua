from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.agent.extraction_agent.domain.models.extraction_stages import (
    CrossPageCompletionRequest,
    DrawingPageInput,
)
from src.agent.extraction_agent.graphs.document_extraction.cross_page import (
    _apply_cross_page_completion,
    _resolve_cross_page_node,
)
from src.agent.extraction_agent.infrastructure.zh_vlm_stages import (
    ZhVlmExtractionStageAdapter,
    _normalize_cross_page,
    _select_stage3_examples,
)
from src.config import AgentSettings
from src.harness.model_gateway import FakeModelGateway
from src.profiles import ProfileRegistry

ROOT = Path(__file__).resolve().parents[4]
ASSETS = ROOT / "services/agent/src/agent/extraction_agent/prompts/zh/examples_wiring/002c"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"result": {}},
        {"completion": {}},
        {"task_id": "one"},
        {"end": None},
        {"end": None, "source_note": "  ", "uncertainties": []},
        {"end": {"terminal": "X21:5"}},
        {"end": None, "warnings": ["unknown"]},
    ],
)
def test_zh_empty_completion_cannot_become_a_valid_default_result(payload: dict) -> None:
    with pytest.raises(ValueError):
        _normalize_cross_page(payload, "one", require_response=True)


def test_explicit_unknown_with_evidence_is_valid_and_other_adapters_are_unchanged() -> None:
    result = _normalize_cross_page(
        {"end": None, "uncertainties": [{"field": "end", "detail": "two N lines lack source identity"}]},
        "one",
        require_response=True,
    )
    assert result["end"] is None and result["uncertainties"]
    assert _normalize_cross_page({}, "one")["task_id"] == "one"
    with pytest.raises(ValueError, match="task_id"):
        _normalize_cross_page(
            {"task_id": "another", "end": None, "source_note": "not visible"},
            "one",
            require_response=True,
        )


def _request() -> CrossPageCompletionRequest:
    registry = ProfileRegistry(
        profile_root=ROOT / "services/agent/src/agent/extraction_agent/profiles",
        workspace_root=ROOT,
        allow_legacy_references=True,
    )
    registry.load_all()
    return CrossPageCompletionRequest(
        run_id="offline",
        project_id="offline",
        profile=registry.bind("zh"),
        task_id="one",
        target_page=DrawingPageInput(pdf_page_number=403, image_path=ASSETS / "images/080c10.png"),
        task_context=json.dumps(
            {
                "task_id": "one",
                "source_pdf_page": 60,
                "references": [{"target_pdf_page": 403, "target_column": 1}],
            }
        ),
    )


def test_empty_answer_retries_once_and_recovers_without_changing_input_image() -> None:
    async def check() -> None:
        gateway = FakeModelGateway(
            [
                "{}",
                json.dumps({"end": None, "source_note": "No uniquely matching return reference is visible"}),
            ]
        )
        adapter = ZhVlmExtractionStageAdapter(AgentSettings(default_model="fake"), gateway)
        result = await adapter.resolve_cross_page(_request())
        assert result.end is None and result.source_note
        assert len(gateway.calls) == 2
        assert gateway.calls[0].messages[-1] == gateway.calls[1].messages[-2]
        assert "end=null" in gateway.calls[1].messages[-1]["content"]

    asyncio.run(check())


def test_empty_answers_exhaust_only_the_existing_two_attempts() -> None:
    async def check() -> None:
        gateway = FakeModelGateway(["{}", "{}"])
        adapter = ZhVlmExtractionStageAdapter(AgentSettings(default_model="fake"), gateway)
        with pytest.raises(ValueError, match="two attempts"):
            await adapter.resolve_cross_page(_request())
        assert len(gateway.calls) == 2

    asyncio.run(check())


def test_completion_failure_preserves_source_and_unresolved_visual_evidence() -> None:
    start = {"terminal": "XD22:21", "terminal_coordinates": {"x": 0.2, "y": 0.5, "pdf_page_number": 118}}
    units = {"u": {"connections": [{"connection_id": "c", "start": start.copy()}]}}
    detail = {"field": "end", "detail": "No valid model response after two attempts"}
    _apply_cross_page_completion(
        units,
        {"unit_id": "u", "connection_id": "c", "target_pdf_page": 139, "references": []},
        {
            "completion_state": "failed",
            "end": None,
            "uncertainties": [detail],
            "warnings": [detail["detail"]],
        },
    )
    connection = units["u"]["connections"][0]
    assert connection["start"] == start
    assert connection["completion_state"] == "failed"
    assert connection["uncertainties"] == [detail]
    assert "two attempts" in connection["source_note"]


def test_failed_completion_does_not_block_the_next_connection(tmp_path: Path) -> None:
    async def check() -> None:
        calls = []

        async def resolve(image, *, source_image, task_context):
            task = json.loads(task_context)
            calls.append(task["task_id"])
            if task["task_id"] == "first":
                raise ValueError("page_completion returned invalid structured data after two attempts")
            return {"end": {"terminal": "X2:10"}, "source_note": "matched heater N reference"}

        runtime = SimpleNamespace(
            extraction_client=SimpleNamespace(completion_uses_source_image=False, resolve_cross_page=resolve),
            output_mode="library",
            durable=None,
            validation_warnings=[],
            extraction_errors={},
            payload_for=lambda path: path,
            log=lambda message: None,
        )
        tasks = [
            {
                "task_id": name,
                "unit_id": "u",
                "connection_id": name,
                "source_pdf_page": 118,
                "target_pdf_page": 139,
                "references": [],
            }
            for name in ("first", "second")
        ]
        state = {
            "output_path": str(tmp_path),
            "cross_page_tasks": tasks,
            "pages": [{"page_number": 139, "image_path": "target.png"}],
            "wire_units": {
                "u": {
                    "connections": [
                        {"connection_id": name, "start": {"terminal": "XD22:21"}}
                        for name in ("first", "second")
                    ]
                }
            },
        }
        result = await _resolve_cross_page_node(state, runtime, use_checkpoint=False)
        first, second = result["wire_units"]["u"]["connections"]
        assert calls == ["first", "second"]
        assert first["completion_state"] == "failed" and first["uncertainties"]
        assert second["end"]["terminal"] == "X2:10"

    asyncio.run(check())


@pytest.mark.parametrize(
    "case_id,terminal",
    [("c02_fc11_n_to_005c01_x21_5", "X21:5"), ("c09_lcm_n_to_005c01_x2_10", "X2:10")],
)
def test_repeated_n_selects_the_matching_source_signal_example(case_id: str, terminal: str) -> None:
    manifest = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
    examples = [
        {**case, "input_json": (ASSETS / case["input"]).read_text(encoding="utf-8")}
        for case in manifest["stage3_cases"]
    ]
    case = next(item for item in examples if item["id"] == case_id)
    selected = _select_stage3_examples(examples, input_json=case["input_json"], limit=1)
    assert selected[0]["id"] == case_id
    expected = json.loads((ASSETS / selected[0]["expected"]).read_text(encoding="utf-8"))
    assert expected["end"]["terminal"] == terminal
    assert expected["current"] is None
