from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from agent_service.agents.supervisor import SupervisorAgent
from agent_service.application.workflow_registry import WorkflowRegistry
from agent_service.domain.models.supervisor import ConversationTurn
from agent_service.graphs.supervisor.graph import run_supervisor_graph
from agent_service.harness.model_gateway import (
    FakeModelGateway,
    ModelGatewayError,
    ModelRequest,
    OpenAICompatibleModelGateway,
)
from agent_service.harness.retry import RetryPolicy

PROMPT = Path(__file__).resolve().parents[2] / "prompts/supervisor.md"


def test_chat_streams_answer_without_plan_confirmation_or_workflow() -> None:
    async def run() -> None:
        gateway = FakeModelGateway(
            [
                json.dumps({"intent": "CHAT", "confidence": 0.99, "reason": "日常问候"}),
                "你好！我是电气图纸与线表智能助手，可以帮你解释图纸、提取连接和核对线表。",
            ]
        )
        events = []

        async def emit(event):
            events.append(event)

        result = await run_supervisor_graph(
            agent=SupervisorAgent(gateway=gateway, prompt_path=PROMPT),
            workflows=WorkflowRegistry(),
            turn=ConversationTurn(conversation_id="chat", user_id="user", message="你好"),
            on_event=emit,
        )
        assert result.decision.status.value == "ANSWERED"
        assert result.decision.requires_input is False
        assert result.receipt is None
        assert result.user_event.event_type == "ASSISTANT_MESSAGE"
        assert events and all(e.event_type == "ASSISTANT_DELTA" for e in events)
        assert "".join(e.user_message for e in events) == result.user_event.user_message
        assert gateway.calls[-1].output_model is None

    asyncio.run(run())


def test_extract_without_pdf_is_plain_upload_prompt_without_dispatch() -> None:
    async def run() -> None:
        gateway = FakeModelGateway(
            [
                json.dumps(
                    {
                        "intent": "PROCESS_DOCUMENT",
                        "confidence": 0.99,
                        "reason": "提取图纸",
                    }
                )
            ]
        )
        result = await run_supervisor_graph(
            agent=SupervisorAgent(gateway=gateway, prompt_path=PROMPT),
            workflows=WorkflowRegistry(),
            turn=ConversationTurn(conversation_id="chat", user_id="user", message="帮我提取"),
        )
        assert result.receipt is None
        assert result.decision.status.value == "ANSWERED"
        assert not result.user_event.requires_input
        assert result.user_event.event_type == "ASSISTANT_MESSAGE"
        assert "PDF" in result.user_event.user_message

    asyncio.run(run())


def test_gateway_stream_emits_only_content_not_reasoning() -> None:
    async def run() -> None:
        seen = []

        async def emit(text: str) -> None:
            seen.append(text)

        def serve(request: httpx.Request) -> httpx.Response:
            assert json.loads(request.content)["stream"] is True
            return httpx.Response(
                200,
                text=(
                    'data: {"choices":[{"delta":{"reasoning_content":"private"}}]}\n\n'
                    'data: {"choices":[{"delta":{"content":"你好"}}]}\n\n'
                    'data: {"choices":[{"delta":{"content":"！"}}]}\n\n'
                    "data: [DONE]\n\n"
                ),
                headers={"Content-Type": "text/event-stream"},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
            gateway = OpenAICompatibleModelGateway(
                base_url="https://fixture.invalid/v1", default_model="fake", client=client
            )
            response = await gateway.stream_text(
                ModelRequest(agent_name="chat", run_id="turn", messages=[]), emit
            )
        assert seen == ["你好", "！"]
        assert response.content == "你好！"

    asyncio.run(run())


def test_gateway_partial_stream_failure_is_not_retried() -> None:
    class BrokenStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
            raise httpx.ReadError("injected disconnect")

    async def run() -> None:
        calls = []
        texts = []

        def serve(request):
            calls.append(request)
            return httpx.Response(200, stream=BrokenStream(), headers={"Content-Type": "text/event-stream"})

        async def emit(text):
            texts.append(text)

        async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
            gateway = OpenAICompatibleModelGateway(
                base_url="https://fixture.invalid/v1", default_model="fake", client=client
            )
            with pytest.raises(ModelGatewayError, match="interrupted"):
                await gateway.stream_text(ModelRequest(agent_name="chat", run_id="turn", messages=[]), emit)
        assert len(calls) == 1
        assert texts == ["partial"]

    asyncio.run(run())


@pytest.mark.parametrize("status, expected_calls", [(503, 2), (403, 1)])
def test_stream_retries_only_temporary_errors_before_text(status: int, expected_calls: int) -> None:
    async def run() -> None:
        calls = []

        def serve(request):
            calls.append(request)
            return httpx.Response(status, json={"error": {"message": "injected provider error"}})

        async def emit(text):
            pytest.fail("No text should be emitted for an HTTP error")

        async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
            gateway = OpenAICompatibleModelGateway(
                base_url="https://fixture.invalid/v1",
                default_model="fake",
                client=client,
                retry_policy=RetryPolicy(max_retries=1, initial_backoff_seconds=0),
            )
            with pytest.raises(ModelGatewayError):
                await gateway.stream_text(ModelRequest(agent_name="chat", run_id="turn", messages=[]), emit)
        assert len(calls) == expected_calls

    asyncio.run(run())
