"""Fake-only diagnostics: distinguish capacity/checkpoint errors without storing content."""

import asyncio
import base64
import json
from uuid import UUID

import pytest

from src.domain.enums import ErrorCode
from src.harness.model_gateway import FakeModelGateway, ModelGatewayError, ModelRequest, ModelResponse


@pytest.mark.parametrize(
    "message,cause",
    [
        ("CUDA out of memory SECRET", "memory_capacity"),
        ("maximum context length exceeded SECRET", "context_limit"),
        ("published MTP checkpoint is not materializable SECRET", "model_checkpoint"),
        ("tool calling is not supported SECRET", "tool_compatibility"),
        ("unknown internal failure SECRET", "unknown"),
    ],
)
def test_error_captures_shape_and_safe_cause_without_private_provider_message(
    tmp_path, caplog, message, cause
):
    from src.agent.explain_agent.api import _public_error
    from src.agent.explain_agent.diagnostics import ExplainDiagnosticGateway
    from src.agent.extraction_agent.infrastructure.document.model_traces import LocalModelTraceStore

    error = ModelGatewayError(
        ErrorCode.MODEL_TEMPORARILY_UNAVAILABLE,
        "SECRET",
        details={
            "failure_kind": "provider_stream_error",
            "provider_message": message,
            "provider_code": "internal_error",
        },
    )
    wrapped = ExplainDiagnosticGateway(FakeModelGateway([error]), LocalModelTraceStore(tmp_path), "fake")
    request = ModelRequest(
        agent_name="explain_agent",
        run_id="explain:test",
        messages=[
            {"role": "user", "content": "PRIVATE QUESTION"},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64," + base64.b64encode(b"PRIVATE IMAGE").decode()
                        },
                    }
                ],
            },
        ],
        metadata={"tool_round": 2, "history_messages": 2, "history_characters": 10},
        tools=[{"type": "function", "function": {"name": "search_connections"}}],
    )
    with pytest.raises(ModelGatewayError) as caught:
        asyncio.run(wrapped.invoke(request))
    identifier = caught.value.details["diagnostic_id"]
    UUID(identifier)
    rows = asyncio.run(LocalModelTraceStore(tmp_path).list("explain:test"))
    assert len(rows) == 1
    assert rows[0]["schema_error"]["cause"] == cause
    summary = rows[0]["metadata"]["request_summary"]
    assert summary["image_count"] == 1 and summary["tool_round"] == 2
    assert summary["tool_names"] == ["search_connections"]
    status, public = _public_error(caught.value)
    assert status == 502 and identifier in public["message"]
    output = json.dumps(rows) + caplog.text + str(public)
    assert "SECRET" not in output and "PRIVATE QUESTION" not in output and "PRIVATE IMAGE" not in output
    assert "data:image" not in output


def test_stream_diagnostic_passes_text_through_and_records_only_numeric_usage(tmp_path):
    from src.agent.explain_agent.diagnostics import ExplainDiagnosticGateway
    from src.agent.extraction_agent.infrastructure.document.model_traces import LocalModelTraceStore

    class Delegate:
        async def stream_text(self, request, on_text):
            await on_text("PRIVATE ANSWER")
            return ModelResponse(
                "PRIVATE ANSWER", None, "fake", 0, 1, usage={"total_tokens": 12, "private": "SECRET"}
            )

    store = LocalModelTraceStore(tmp_path)
    gateway = ExplainDiagnosticGateway(Delegate(), store, "fake")
    chunks = []

    async def collect(value):
        chunks.append(value)

    asyncio.run(
        gateway.stream_text(ModelRequest(agent_name="explain_agent", run_id="test", messages=[]), collect)
    )
    assert chunks == ["PRIVATE ANSWER"]
    rows = asyncio.run(store.list("test"))
    assert rows[0]["usage"] == {"total_tokens": 12}
    assert rows[0]["metadata"]["returned_tool_calls"] == 0
    assert "PRIVATE ANSWER" not in json.dumps(rows) and "SECRET" not in json.dumps(rows)


def test_diagnostic_write_failure_does_not_hide_original_model_result():
    from src.agent.explain_agent.diagnostics import ExplainDiagnosticGateway

    class BrokenStore:
        async def append(self, *args):
            raise OSError("PRIVATE PATH")

    result = asyncio.run(
        ExplainDiagnosticGateway(FakeModelGateway(["OK"]), BrokenStore(), "fake").invoke(
            ModelRequest(agent_name="explain_agent", run_id="test", messages=[]),
        )
    )
    assert result.content == "OK"


def test_error_diagnostic_rejects_credential_shaped_provider_codes():
    from src.agent.explain_agent.diagnostics import error_summary

    error = ModelGatewayError(
        ErrorCode.MODEL_TEMPORARILY_UNAVAILABLE,
        "PRIVATE",
        details={
            "provider_message": "PRIVATE",
            "provider_code": "sk-private-token",
            "provider_type": "Bearer abc",
        },
    )
    assert "private" not in json.dumps(error_summary(error)).casefold()


def test_tool_choice_rejection_is_classified_by_provider_code_without_body():
    from src.agent.explain_agent.api import _public_error
    from src.agent.explain_agent.diagnostics import error_summary

    error = ModelGatewayError(
        ErrorCode.INVALID_REQUEST,
        "PRIVATE",
        details={"status_code": 400, "provider_code": "tool_choice_not_supported"},
    )
    summary = error_summary(error)
    assert summary["cause"] == "tool_choice_compatibility"
    error.details["diagnostic_cause"] = summary["cause"]
    assert "不支持强制工具选择" in _public_error(error)[1]["message"]
    assert "PRIVATE" not in json.dumps(summary)


def test_request_summary_identifies_after_tool_failure_without_copying_result():
    from src.agent.explain_agent.diagnostics import request_summary

    request = ModelRequest(
        agent_name="explain_agent",
        run_id="x",
        messages=[
            {
                "role": "assistant",
                "tool_calls": [{"function": {"name": "search_connections", "arguments": "PRIVATE"}}],
            },
            {"role": "tool", "content": "PRIVATE RESULT"},
        ],
        tools=[{"type": "function", "function": {"name": "search_connections"}}],
    )
    summary = request_summary(request)
    assert summary["tool_result_messages"] == 1 and summary["prior_tool_names"] == ["search_connections"]
    assert "PRIVATE" not in json.dumps(summary)
