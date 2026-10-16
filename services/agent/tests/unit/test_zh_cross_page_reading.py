from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.extraction_agent.domain.models.extraction_stages import (
    CrossPageCompletionRequest,
    DrawingPageInput,
)
from src.agent.extraction_agent.domain.models.wiring import WireConnection, WireRecord
from src.agent.extraction_agent.infrastructure.zh_vlm_stages import _select_stage3_examples
from src.agent.extraction_agent.profiles.zh.completion_context import target_only_context
from src.agent.extraction_agent.profiles.zh.normalization import complete_terminal_identifier
from src.agent.extraction_agent.profiles.zh.policy import ZhExtractionPolicy
from src.agent.extraction_agent.profiles.zh.references import prepare_reference
from src.agent.extraction_agent.profiles.zh_gantry_reel.policy import ZhGantryReelPolicy
from src.profiles import ProfileRegistry

ROOT = Path(__file__).resolve().parents[4]


def _reference(page=1, column=1, *, source=61, function="046.R", obj="+01F18"):
    return {"source_pdf_page": source, "raw": f"={function}{obj}/{page}.{column}"}


@pytest.mark.parametrize(
    "raw,function,obj,source,verified,lookup,target",
    [
        ("=046.R+01F18/8.1", "046.R", "+01F18", 61, _reference(), {"046.R:1": 385}, 385),
        (
            "=010.C+01F13/31.1",
            "010.C",
            "+01F13",
            65,
            _reference(source=65, function="010.C", obj="+01F13"),
            {"010.C:1": 148},
            148,
        ),
        (
            "=041J-01F23/1.3",
            "041J",
            "+01F23",
            121,
            _reference(column=3, source=121, function="041.J", obj="+01F23"),
            {"041.J:1": 344},
            344,
        ),
    ],
)
def test_only_unique_same_source_pdf_evidence_recovers_unavailable_address(
    raw,
    function,
    obj,
    source,
    verified,
    lookup,
    target,
):
    result = prepare_reference(
        {"raw": raw, "target_function": function, "target_object": obj},
        source_page={"page_number": source, "function": "003.C"},
        drawing_index={"references": [verified, verified.copy()], "page_lookup": lookup},
    )
    assert result["raw"] == raw
    assert result["source_index_raw"] == verified["raw"]
    assert result["target_pdf_page"] == target
    assert result["external"] is False


@pytest.mark.parametrize(
    "other",
    [
        _reference(2),  # Different addresses on the same source page are ambiguous.
        _reference(source=999),  # Other source pages are not evidence for this connection.
        _reference(obj="+OTHER"),
        _reference(function="080.C"),
    ],
)
def test_recovery_does_not_guess_from_unavailable_or_unrelated_candidates(other):
    candidates = [_reference(), other] if other.get("raw", "").endswith("/2.1") else [other]
    result = prepare_reference(
        {"raw": "=046.R+01F18/8.1", "source_index_raw": "invented"},
        source_page={"page_number": 61, "function": "003.C"},
        drawing_index={"references": candidates, "page_lookup": {"046.R:1": 385}},
    )
    assert result["target_pdf_page"] is None
    assert result["source_index_raw"] is None


def test_available_literal_address_does_not_get_replaced_by_another_page():
    result = prepare_reference(
        {"raw": "=046.R+01F18/8.1"},
        source_page={"page_number": 61, "function": "003.C"},
        drawing_index={"references": [_reference()], "page_lookup": {"046.R:1": 385, "046.R:8": 999}},
    )
    assert result["target_pdf_page"] == 999
    assert result["source_index_raw"] is None


@pytest.mark.parametrize("terminal,board", [("X2", "X2"), ("X2:X2", "X2"), ("XD21", None), ("XD21:", None)])
def test_board_without_a_pin_is_not_a_complete_zh_terminal(terminal, board):
    connection, _ = ZhExtractionPolicy().orient_connection(
        WireConnection(
            endpoint_role="source",
            direction_basis="visible source segment",
            start={"terminal": "XD3:17"},
            end={
                "terminal": terminal,
                "terminal_board": board,
                "terminal_coordinates": {"x": 0.5, "y": 0.5, "pdf_page_number": 139},
            },
        )
    )
    assert connection.end.terminal is None
    assert connection.end.terminal_coordinates is None
    assert connection.status == "needs_review"


def test_symbolic_pins_bars_and_other_profile_behavior_are_preserved():
    for pin in ("1", "2A", "L1", "U2"):
        assert complete_terminal_identifier(pin, "X2", require_pin=True) == f"X2:{pin}"
    assert complete_terminal_identifier("N-BAR", "XD10", require_pin=True) == "N-BAR"
    assert complete_terminal_identifier("PE-BAR", "XD10", require_pin=True) == "PE-BAR"
    row = WireRecord(line_number="PE", start_device="+01F35", start_terminal="PE", end_terminal="PE-BAR")
    assert not ZhExtractionPolicy().validate_record(row, {})
    assert complete_terminal_identifier("X2", "X2") == "X2:X2"
    assert (
        ZhGantryReelPolicy()
        .normalize_record(WireRecord(start_terminal="X2", start_terminal_board="X2"), {})
        .start_terminal
        == "X2"
    )


def test_v1_context_is_sanitized_before_becoming_v2_model_input(tmp_path):
    registry = ProfileRegistry(
        profile_root=ROOT / "services/agent/src/agent/extraction_agent/profiles",
        workspace_root=ROOT,
        allow_legacy_references=True,
    )
    registry.load_all()
    request = CrossPageCompletionRequest(
        run_id="offline",
        project_id="offline",
        profile=registry.bind("zh"),
        task_id="one",
        target_page=DrawingPageInput(pdf_page_number=426, image_path=tmp_path / "not-read.png"),
        task_context=json.dumps(
            {
                "context_version": 1,
                "task_id": "old",
                "source_page": {},
                "target_page": {},
                "start": {
                    "device": "+01F11.3",
                    "terminal": "XD21:18",
                    "terminal_coordinates": {"x": 0.12345, "y": 0.23456, "pdf_page_number": 68},
                },
            }
        ),
    )
    context = target_only_context(request)
    assert context.context_version == 2 and context.task_id == "one"
    assert context.source_component.device == "+01F11.3"
    assert "XD21:18" not in context.model_dump_json()
    assert "0.12345" not in context.model_dump_json()


def test_v2_example_selection_uses_signal_and_business_page_without_source_pin():
    base = {
        "context_version": 2,
        "source_page": {"drawing_function": "004.C", "drawing_page_number": 9},
        "target_page": {"drawing_function": "005.C", "drawing_page_number": 1},
        "signal_name": "-LCM_FC50_L",
    }
    examples = [
        {"id": "control", "input_json": json.dumps({**base, "signal_name": "-FC11_N"})},
        {"id": "heater", "input_json": json.dumps(base)},
    ]
    assert _select_stage3_examples(examples, input_json=json.dumps(base), limit=1)[0]["id"] == "heater"
