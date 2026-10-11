from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from agent_service.agents.improvement_diagnoser import ImprovementDiagnoserAgent
from agent_service.domain.models.improvement import AcceptedFeedback, Diagnosis
from agent_service.harness.model_gateway import (
    FakeModelGateway,
    ModelGatewayError,
    OpenAICompatibleModelGateway,
)

ROOT = Path(__file__).resolve().parents[4]
PROMPT = ROOT / "services/agent/prompts/improvement_diagnosis.md"


def feedback() -> AcceptedFeedback:
    return AcceptedFeedback(
        feedback_id="feedback-1",
        project_id="project-1",
        accepted=True,
        result_version_id="version-1",
        profile={"key": "zh", "version": "1.0.0", "checksum": "sha256:" + "a" * 64},
        model_name="fake",
        target={"type": "CONNECTION", "ids": ["connection-1"]},
        before={"end_terminal": "999"},
        after={"end_terminal": "2"},
        evidence_ids=["evidence-1"],
        stage_artifact_ids=["artifact-1"],
        prompt_checksum="sha256:" + "a" * 64,
        feedback_origin="manual_injected_test_error",
    )


def valid_output(category: str = "USER_EXPECTATION_MISMATCH") -> dict[str, Any]:
    return {
        "category": category,
        "confidence": 0.9,
        "affected_stage": ["PAGE_SCAN"],
        "affected_scope": {"type": "CONNECTION", "ids": ["connection-1"]},
        "evidence_ids": ["evidence-1"],
        "explanation": "人工注错已纠正；不证明原模型幻觉或生产规则有缺陷。",
        "recommended_action": "保留审计；本次不创建规则候选。",
        "profile_candidate_required": False,
        "needs_human_input": False,
    }


def test_diagnoser_supplies_complete_runtime_schema_to_model() -> None:
    async def run() -> None:
        gateway = FakeModelGateway([json.dumps(valid_output())])
        agent = ImprovementDiagnoserAgent(gateway=gateway, prompt_path=PROMPT)
        diagnosis = await agent.diagnose(feedback())
        request = gateway.calls[0]
        system = request.messages[0]["content"]
        schema = json.loads(system.split("Output JSON Schema:\n", 1)[1])
        assert schema == Diagnosis.model_json_schema()
        assert schema["additionalProperties"] is False
        assert "affected_scope" in schema["required"]
        assert "SOURCE_INSUFFICIENT" in schema["$defs"]["RootCauseCategory"]["enum"]
        assert schema["$defs"]["AffectedScope"]["properties"]["ids"]["minItems"] == 1
        assert request.output_model is Diagnosis
        assert request.json_mode is False
        assert len(gateway.calls) == 1
        assert not diagnosis.profile_candidate_required
        assert json.loads(request.messages[1]["content"][0]["text"]) == feedback().model_dump(mode="json")

    asyncio.run(run())


@pytest.mark.parametrize("category", ["SOURCE_INSUFFICIENT", "PROMPT_RULE_GAP"])
def test_valid_schema_categories_are_not_replaced_by_forced_no_rule_verdict(category: str) -> None:
    async def run() -> None:
        output = valid_output(category)
        output["profile_candidate_required"] = category == "PROMPT_RULE_GAP"
        output["needs_human_input"] = category == "SOURCE_INSUFFICIENT"
        gateway = FakeModelGateway([json.dumps(output)])
        result = await ImprovementDiagnoserAgent(gateway=gateway, prompt_path=PROMPT).diagnose(feedback())
        assert result.category.value == category
        assert result.profile_candidate_required == output["profile_candidate_required"]
        assert result.needs_human_input == output["needs_human_input"]

    asyncio.run(run())


def test_freeform_failed_run_output_still_fails_strict_validation() -> None:
    async def run() -> None:
        # The failed run invented these field names instead of the Diagnosis contract.
        gateway = FakeModelGateway(
            [
                json.dumps(
                    {
                        "feedback_id": "feedback-1",
                        "diagnosis": "CORRECTION_PIPELINE_VERIFIED",
                        "confidence": 0.95,
                        "summary": "Corrected injected data",
                        "root_cause": "MANUAL_TEST_INJECTION",
                        "requires_human_review": False,
                    }
                )
            ]
        )
        with pytest.raises(ModelGatewayError) as error:
            await ImprovementDiagnoserAgent(gateway=gateway, prompt_path=PROMPT).diagnose(feedback())
        fields = error.value.details["validation_errors"]
        assert any(field["location"] == ["category"] and field["type"] == "missing" for field in fields)
        assert any(
            field["location"] == ["diagnosis"] and field["type"] == "extra_forbidden" for field in fields
        )
        assert len(gateway.calls) == 1  # Never auto-retry/relabel a schema error as success.

    asyncio.run(run())


def test_openai_compatible_request_contains_schema_without_provider_json_mode() -> None:
    async def run() -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            body = json.loads(request.content)
            schema = json.loads(body["messages"][0]["content"].split("Output JSON Schema:\n", 1)[1])
            assert schema == Diagnosis.model_json_schema()
            assert "response_format" not in body
            assert body["messages"][1]["content"][0]["type"] == "text"
            return httpx.Response(
                200, json={"choices": [{"message": {"content": json.dumps(valid_output())}}]}
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = OpenAICompatibleModelGateway(
                base_url="http://model.invalid",
                default_model="fake",
                client=client,
            )
            result = await ImprovementDiagnoserAgent(gateway=gateway, prompt_path=PROMPT).diagnose(feedback())
        assert calls == 1
        assert result.category.value == "USER_EXPECTATION_MISMATCH"

    asyncio.run(run())
