from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from src.agents.profile_patch_builder import ProfilePatchBuilderAgent
from src.domain.models.improvement import AcceptedFeedback, Diagnosis, ProfilePatchModelOutput
from src.harness.model_gateway import (
    FakeModelGateway,
    ModelGatewayError,
    OpenAICompatibleModelGateway,
)

PROMPT = Path(__file__).resolve().parents[4] / "services/agent/src/agent/extraction_agent/prompts/profile_patch_builder.md"


def feedback() -> AcceptedFeedback:
    return AcceptedFeedback(
        feedback_id="feedback-1",
        project_id="project-1",
        accepted=True,
        result_version_id="result-1",
        profile={"key": "zh-wrong", "version": "1.0.0"},
        model_name="fake",
        target={"type": "CONNECTION", "ids": ["c1"]},
        before={"end_terminal": "999"},
        after={"end_terminal": "X3:1"},
        evidence_ids=["e1"],
        stage_artifact_ids=["a1"],
        prompt_checksum="fixture",
        context={"profile_files": {"resources/cross_page_prompt.md": "# Rule\nKeep X3:1.\n"}},
    )


def diagnosis() -> Diagnosis:
    return Diagnosis(
        category="PROMPT_RULE_GAP",
        confidence=0.95,
        affected_stage=["CROSS_PAGE_COMPLETION"],
        affected_scope={"type": "CONNECTION", "ids": ["c1"]},
        explanation="规则冲突",
        recommended_action="保留前缀",
        profile_candidate_required=True,
    )


def output() -> dict[str, object]:
    return {
        "candidate_type": "PROMPT_PATCH",
        "summary": "修复终点前缀规则",
        "operations": [
            {
                "op": "replace",
                "relative_path": "resources/cross_page_prompt.md",
                "content": "# Rule\n保留完整端子 X3:1，包括前缀。\n",
                "reason": "只替换错误规则，保留其他内容",
            }
        ],
        "expected_benefit": "保留跨页终点完整标识",
        "risks": ["需要回归验证"],
    }


def test_patch_prompt_contains_exact_runtime_schema() -> None:
    async def run() -> None:
        gateway = FakeModelGateway([json.dumps(output(), ensure_ascii=False)])
        result = await ProfilePatchBuilderAgent(gateway=gateway, prompt_path=PROMPT).build(
            feedback=[feedback()], diagnoses=[diagnosis()]
        )
        prompt = gateway.calls[0].messages[0]["content"]
        assert (
            json.loads(prompt.split("Output JSON Schema:\n", 1)[1])
            == ProfilePatchModelOutput.model_json_schema()
        )
        assert result.operations[0].content == output()["operations"][0]["content"]

    asyncio.run(run())


@pytest.mark.parametrize("outer", ["plain", "fenced", "preamble"])
def test_patch_content_embedded_json_fence_is_not_response_wrapper(outer: str) -> None:
    async def run() -> None:
        payload = output()
        payload["operations"] = [
            {
                "op": "replace",
                "relative_path": "resources/cross_page_prompt.md",
                "content": '# Stage 3\n保留 X3:1。\n```json\n{"task_id":"t1","end":null}\n```\n',
                "reason": "保留输出示例代码块",
            }
        ]
        content = json.dumps(payload, ensure_ascii=False)
        if outer == "fenced":
            content = "```json\n" + content + "\n```"
        elif outer == "preamble":
            content = "Patch follows:\n" + content
        gateway = FakeModelGateway([content])
        result = await ProfilePatchBuilderAgent(gateway=gateway, prompt_path=PROMPT).build(
            feedback=[feedback()], diagnoses=[diagnosis()]
        )
        assert result.model_dump(mode="json") == payload

    asyncio.run(run())


def test_wire_request_has_schema_and_pure_json_contract_without_provider_mode() -> None:
    async def run() -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            body = json.loads(req.content)
            assert "response_format" not in body
            system = body["messages"][0]["content"]
            assert "complete replacement file" in system
            assert "raw newlines" in system
            assert (
                json.loads(system.split("Output JSON Schema:\n", 1)[1])
                == ProfilePatchModelOutput.model_json_schema()
            )
            assert isinstance(body["messages"][1]["content"], str)
            return httpx.Response(
                200, json={"choices": [{"message": {"content": json.dumps(output(), ensure_ascii=False)}}]}
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = OpenAICompatibleModelGateway(
                base_url="http://model.invalid", default_model="fake", client=client
            )
            await ProfilePatchBuilderAgent(gateway=gateway, prompt_path=PROMPT).build(
                feedback=[feedback()], diagnoses=[diagnosis()]
            )

    asyncio.run(run())


@pytest.mark.parametrize(
    "content",
    ["Here is the patch:\nnot JSON", '{"summary":"bad\nnewline"}', '{"candidate_type":"PROMPT_PATCH"}'],
)
def test_invalid_output_still_rejected_without_retry(content: str) -> None:
    async def run() -> None:
        gateway = FakeModelGateway([content])
        with pytest.raises(ModelGatewayError):
            await ProfilePatchBuilderAgent(gateway=gateway, prompt_path=PROMPT).build(
                feedback=[feedback()], diagnoses=[diagnosis()]
            )
        assert len(gateway.calls) == 1

    asyncio.run(run())
