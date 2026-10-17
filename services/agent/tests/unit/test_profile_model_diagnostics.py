from __future__ import annotations

import asyncio
import json
import logging

import httpx
import pytest

from src.agent.extraction_agent.infrastructure.document.model_traces import LocalModelTraceStore
from src.agent.profile_agent.api import public_error
from src.agent.profile_agent.diagnostics import ProfileModelGateway
from src.agent.profile_agent.wizard import GeneratedAnswer
from src.harness.model_gateway import (
    FakeModelGateway,
    ModelGatewayError,
    ModelRequest,
    OpenAICompatibleModelGateway,
)
from src.harness.retry import RetryPolicy


def query():
    return ModelRequest(
        agent_name="profile_agent",
        run_id="profile-stage:fixture",
        max_tokens=8000,
        messages=[{"role": "user", "content": "private input must not be written into diagnostics"}],
        output_model=GeneratedAnswer,
        metadata={"stage": "scan", "operation": "wizard_generate"},
    )


def test_schema_failure_has_terminal_log_private_response_and_public_field_error(tmp_path, caplog):
    async def check():
        content = json.dumps({"rule_text": "读取图中标记", "expected": {}, "unknown": "unexpected field"})

        def handle(request):
            return httpx.Response(
                200, json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}
            )

        traces = LocalModelTraceStore(tmp_path)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            delegate = OpenAICompatibleModelGateway(
                base_url="http://model",
                default_model="fake",
                api_key="fixture-secret",
                client=client,
                trace_store=traces,
            )
            gateway = ProfileModelGateway(delegate, traces)
            with pytest.raises(ModelGatewayError) as caught:
                await gateway.invoke(query())
        status, detail = public_error(caught.value)
        assert status == 502 and detail["code"] == "MODEL_SCHEMA_INVALID"
        assert "unknown" in detail["message"] and detail["diagnostic_id"]
        rows = await traces.list(query().run_id)
        assert len(rows) == 2 and rows[0]["response_content"] == content
        serialized = json.dumps(rows)
        assert "private input" not in serialized and "fixture-secret" not in serialized
        assert detail["diagnostic_id"] in caplog.text and "MODEL_SCHEMA_INVALID" in caplog.text

    with caplog.at_level(logging.ERROR):
        asyncio.run(check())


@pytest.mark.parametrize("status", [400, 403, 413, 429, 503])
def test_http_errors_keep_status_without_leaking_provider_messages(status, tmp_path, caplog):
    async def check():
        def handle(request):
            return httpx.Response(
                status,
                json={"error": {"message": "api_key=fixture-secret Bearer fixture-secret private upstream"}},
            )

        traces = LocalModelTraceStore(tmp_path)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            delegate = OpenAICompatibleModelGateway(
                base_url="http://model",
                default_model="fake",
                client=client,
                trace_store=traces,
                retry_policy=RetryPolicy(max_retries=0),
            )
            with pytest.raises(ModelGatewayError) as caught:
                await ProfileModelGateway(delegate, traces).invoke(query())
        _, detail = public_error(caught.value)
        assert f"HTTP {status}" in detail["message"]
        data = json.dumps(await traces.list(query().run_id)) + json.dumps(detail) + caplog.text
        assert "fixture-secret" not in data and "private upstream" not in data

    asyncio.run(check())


def test_truncated_json_is_distinguished_from_schema_invalid(tmp_path):
    async def check():
        def handle(request):
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": '{"rule_text":"unfinished'}, "finish_reason": "length"}
                    ]
                },
            )

        traces = LocalModelTraceStore(tmp_path)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            delegate = OpenAICompatibleModelGateway(
                base_url="http://model", default_model="fake", client=client, trace_store=traces
            )
            with pytest.raises(ModelGatewayError) as caught:
                await ProfileModelGateway(delegate, traces).invoke(query())
        assert public_error(caught.value)[1]["code"] == "MODEL_TRUNCATED"

    asyncio.run(check())


def test_diagnostic_files_unavailable_do_not_replace_model_failure(tmp_path, monkeypatch):
    async def check():
        traces = LocalModelTraceStore(tmp_path)

        def fail(*args, **kwargs):
            raise OSError("fixture disk error")

        monkeypatch.setattr(traces, "_write", fail)

        def handle(request):
            raise httpx.ReadTimeout("private timeout detail", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            delegate = OpenAICompatibleModelGateway(
                base_url="http://model",
                default_model="fake",
                client=client,
                trace_store=traces,
                retry_policy=RetryPolicy(max_retries=0),
            )
            with pytest.raises(ModelGatewayError) as caught:
                await ProfileModelGateway(delegate, traces).invoke(query())
        assert "超时" in public_error(caught.value)[1]["message"]

    asyncio.run(check())


def test_profile_model_settings_are_forwarded_without_forcing_json_on_tool_chat(tmp_path):
    async def check():
        delegate = FakeModelGateway(['{"rule_text":"sample","expected":{}}', "plain reply"])
        gateway = ProfileModelGateway(
            delegate,
            LocalModelTraceStore(tmp_path),
            enable_thinking=False,
            json_mode=True,
            default_model="configured-model",
        )
        await gateway.invoke(query())
        assert delegate.calls[0].enable_thinking is False
        assert delegate.calls[0].json_mode is True and delegate.calls[0].model == "configured-model"
        await gateway.invoke(
            ModelRequest(
                agent_name="profile_agent", run_id="tool-chat", messages=[], tools=[{"type": "function"}]
            )
        )
        assert delegate.calls[1].json_mode is False

    asyncio.run(check())
