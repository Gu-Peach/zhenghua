"""Capture transport evidence without network access, database access or request secrets."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from src.harness.model_gateway import ModelRequest, OpenAICompatibleModelGateway

# isort: split
from src.agent.extraction_agent.infrastructure.document.model_traces import LocalModelTraceStore
from src.agent.extraction_agent.infrastructure.zh_vlm_stages import _schema_retry_instruction


def test_truncated_inner_json_is_saved_with_stop_reason_and_usage(tmp_path: Path) -> None:
    async def run() -> None:
        raw = '{"units":[{"connections":['
        store = LocalModelTraceStore(tmp_path / "model_calls")
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    json={
                        "choices": [{"message": {"content": raw}, "finish_reason": "length"}],
                        "usage": {"completion_tokens": 1234},
                    },
                )
            )
        ) as client:
            gateway = OpenAICompatibleModelGateway(
                base_url="http://model.invalid/v1",
                default_model="fake",
                api_key="test-secret",
                trace_store=store,
                client=client,
            )
            result = await gateway.invoke(
                ModelRequest(
                    agent_name="page_scan",
                    run_id="invalid/filename",
                    metadata={"input_pdf_pages": [1]},
                    messages=[{"role": "user", "content": "private request text"}],
                )
            )
        assert result.finish_reason == "length"
        rows = await store.list("invalid/filename")
        assert len(rows) == 1
        assert rows[0]["response_content"] == raw
        assert rows[0]["response_char_count"] == len(raw)
        assert rows[0]["finish_reason"] == "length"
        assert rows[0]["usage"]["completion_tokens"] == 1234
        serialized = json.dumps(rows)
        assert "test-secret" not in serialized and "private request text" not in serialized
        assert "messages" not in rows[0]
        assert len(list((tmp_path / "model_calls").glob("*.json"))) == 1

    asyncio.run(run())


def test_local_trace_disk_error_does_not_fail_the_model_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalModelTraceStore(tmp_path)

    def failed(*_args: object) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr(store, "_write", failed)
    asyncio.run(store.append("run", {"response_content": "{}"}))


def test_json_retry_reports_location_without_replaying_invalid_answer() -> None:
    try:
        json.loads('{"x":1 "y":2}')
    except json.JSONDecodeError as exc:
        instruction = _schema_retry_instruction(exc)
    assert "行1" in instruction and "位置" in instruction
    assert '{"x":1' not in instruction
    assert len(instruction) < 300


def test_length_limited_abb_output_is_not_retried_as_a_comma_error() -> None:
    from src.agent.extraction_agent.domain.models.extraction_stages import DrawingPageInput, PageScanRequest
    from src.agent.extraction_agent.infrastructure.abb_vlm_stages import AbbVlmExtractionStageAdapter
    from src.config import AgentSettings
    from src.harness.model_gateway import ModelResponse
    from src.profiles import ProfileRegistry

    root = Path(__file__).resolve().parents[4]

    class LimitedGateway:
        calls: int = 0

        async def invoke(self, request: ModelRequest) -> ModelResponse:
            self.calls += 1
            schema = json.loads(request.messages[0]["content"].split("输出 JSON Schema：\n", 1)[1])
            assert "DrawingEndpoint" in schema["$defs"]
            assert "ZH" not in schema["$defs"]["DrawingEndpoint"]["properties"]["device"].get(
                "description", ""
            )
            return ModelResponse(
                content='{"units":[',
                parsed=None,
                model="fake",
                duration_seconds=0,
                attempts=1,
                finish_reason="length",
            )

    async def run() -> None:
        registry = ProfileRegistry(
            profile_root=root / "services/agent/src/agent/extraction_agent/profiles",
            workspace_root=root,
            allow_legacy_references=True,
        )
        registry.load_all()
        gateway = LimitedGateway()
        adapter = AbbVlmExtractionStageAdapter(AgentSettings(default_model="fake"), gateway)
        with pytest.raises(ValueError, match="finish_reason=length"):
            await adapter.scan_page(
                PageScanRequest(
                    run_id="length-limited",
                    project_id="offline",
                    profile=registry.bind("abb"),
                    page=DrawingPageInput(
                        pdf_page_number=1,
                        image_path=root / (
                            "services/agent/src/agent/extraction_agent/prompts/abb/"
                            "examples_wiring/lv11/images/lv11_205.png"
                        ),
                    ),
                )
            )
        assert gateway.calls == 1

    asyncio.run(run())
