from __future__ import annotations

import pytest

from src.agent.extraction_agent.application.review import evaluate_review, facts_only


def facts(**changes):
    return {
        "start_terminal": "XD3:1",
        "end_terminal": "X1:2",
        "endpoint_role": "source",
        "direction_basis": "按可见箭头方向",
        **changes,
    }


@pytest.mark.parametrize("status,flag", [("needs_review", True), ("complete", False), ("resolved", False)])
def test_model_verdict_never_controls_final_review(status, flag):
    result = evaluate_review(
        facts(status=status, needs_review=flag, confidence=0.01), phase="final", strict_evidence=True
    )
    assert not result.needs_review


def test_waiting_for_completion_is_not_a_missing_endpoint_review():
    data = facts(end_terminal=None, references=[{"target_pdf_page": 2}])
    pending = evaluate_review(data, phase="scan", strict_evidence=True)
    assert pending.processing_status == "pending_completion"
    assert not pending.needs_review
    final = evaluate_review(data, phase="final", strict_evidence=True)
    assert final.needs_review
    assert final.review_reasons[0].code == "missing_end_terminal"


def test_visual_uncertainty_and_runtime_conflict_have_structured_reasons():
    result = evaluate_review(
        facts(
            completion_state="conflicting",
            uncertainties=[
                {"field": "start", "detail": "针脚文字有两个候选"},
            ],
        ),
        phase="final",
        strict_evidence=True,
    )
    assert {item.code for item in result.review_reasons} == {"target_conflict", "visual_uncertainty"}


def test_model_schema_and_response_hide_program_fields():
    schema = {"properties": {"status": {}, "needs_review": {}, "start": {}}, "required": ["status", "start"]}
    assert facts_only(schema) == {"properties": {"start": {}}, "required": ["start"]}
