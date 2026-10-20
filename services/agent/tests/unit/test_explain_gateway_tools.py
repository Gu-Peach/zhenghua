from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import httpx
import pytest

from src.agent.explain_agent.tools.retrieval import ConnectionSearchTool
from src.harness.model_gateway import ModelGatewayError, ModelRequest, OpenAICompatibleModelGateway
from src.harness.retry import RetryPolicy


def request():
    return ModelRequest(
        agent_name="explain_agent",
        run_id="test",
        messages=[{"role": "user", "content": "查页"}],
        tools=[ConnectionSearchTool.definition()],
    )


def tool_message(arguments='{"drawing_page":"003C01"}'):
    return {
        "id": "query_1",
        "type": "function",
        "function": {
            "name": "search_connections",
            "arguments": arguments,
        },
    }


def test_native_tool_request_and_null_content_response_roundtrip():
    async def run():
        calls = []

        def handle(req):
            calls.append(json.loads(req.content))
            if calls[-1].get("tools"):
                return httpx.Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {
                                    "content": None,
                                    "tool_calls": [tool_message()],
                                },
                                "finish_reason": "tool_calls",
                            }
                        ]
                    },
                )
            return httpx.Response(200, json={"choices": [{"message": {"content": "plain"}}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            gateway = OpenAICompatibleModelGateway(
                base_url="https://model.invalid", default_model="fake", client=client
            )
            result = await gateway.invoke(request())
            assert not result.content and result.tool_calls[0].name == "search_connections"
            assert json.loads(result.tool_calls[0].arguments) == {"drawing_page": "003C01"}
            assert result.finish_reason == "tool_calls"
            await gateway.invoke(ModelRequest(agent_name="old", run_id="old", messages=[]))
            assert "tools" not in calls[-1]
            assert calls[0]["tools"][0]["function"]["parameters"]["additionalProperties"] is False

    asyncio.run(run())


@pytest.mark.parametrize("streaming", [False, True])
def test_required_tool_choice_is_sent_only_when_explicitly_requested(streaming):
    async def run():
        bodies = []

        def handle(req):
            bodies.append(json.loads(req.content))
            if streaming:
                frame = {
                    "choices": [
                        {
                            "delta": {"tool_calls": [{"index": 0, **tool_message()}]},
                            "finish_reason": "tool_calls",
                        }
                    ]
                }
                return httpx.Response(
                    200,
                    text="data: " + json.dumps(frame) + "\n\ndata: [DONE]\n\n",
                    headers={"content-type": "text/event-stream"},
                )
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {"content": None, "tool_calls": [tool_message()]},
                            "finish_reason": "tool_calls",
                        }
                    ]
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            gateway = OpenAICompatibleModelGateway(
                base_url="https://model.invalid", default_model="fake", client=client
            )

            async def emit(_text):
                pass

            for choice in (None, "required"):
                value = replace(request(), tool_choice=choice)
                result = await gateway.stream_text(value, emit) if streaming else await gateway.invoke(value)
                assert result.tool_calls[0].name == "search_connections"
            assert "tool_choice" not in bodies[0] and bodies[1]["tool_choice"] == "required"

    asyncio.run(run())


def test_stream_assembles_tool_fragments_and_forwards_only_public_text():
    async def run():
        frames = [
            {
                "choices": [
                    {
                        "delta": {
                            "reasoning_content": "PRIVATE-THOUGHT",
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "query_1",
                                    "type": "function",
                                    "function": {"name": "search_connections", "arguments": '{"drawing_'},
                                }
                            ],
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {
                                        "arguments": 'page":"003C01"}',
                                    },
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
        ]
        stream = "".join("data: " + json.dumps(frame) + "\n\n" for frame in frames) + "data: [DONE]\n\n"
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, text=stream, headers={"content-type": "text/event-stream"})
            )
        ) as client:
            gateway = OpenAICompatibleModelGateway(
                base_url="https://model.invalid", default_model="fake", client=client
            )
            public = []

            async def emit(text):
                public.append(text)

            result = await gateway.stream_text(request(), emit)
            assert public == [] and result.content == ""
            assert result.tool_calls[0].id == "query_1"
            assert json.loads(result.tool_calls[0].arguments) == {"drawing_page": "003C01"}

    asyncio.run(run())


@pytest.mark.parametrize(
    "calls",
    [
        [tool_message(), tool_message()],
        [{"id": "x", "type": "other", "function": {}}],
        [tool_message({"drawing_page": "x"})],
        "not-a-list",
    ],
)
def test_invalid_provider_tool_shapes_are_safe_schema_errors(calls):
    with pytest.raises(ModelGatewayError, match="Invalid model tool"):
        OpenAICompatibleModelGateway._read_tool_calls({"tool_calls": calls})


def test_partial_tool_stream_is_not_retried_or_executed():
    async def run():
        calls = []

        def handle(req):
            calls.append(req)
            frame = {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "query_1",
                                    "function": {"name": "search_connections", "arguments": "{"},
                                }
                            ]
                        }
                    }
                ]
            }
            return httpx.Response(
                200, text="data: " + json.dumps(frame) + "\n\n", headers={"content-type": "text/event-stream"}
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            gateway = OpenAICompatibleModelGateway(
                base_url="https://model.invalid",
                default_model="fake",
                client=client,
                retry_policy=RetryPolicy(max_retries=2, initial_backoff_seconds=0),
            )

            async def emit(_):
                pytest.fail("No public text in a tool-only stream")

            with pytest.raises(ModelGatewayError, match="ended before completion"):
                await gateway.stream_text(request(), emit)
            assert len(calls) == 1

    asyncio.run(run())


@pytest.mark.parametrize("prefix", ["", 'data: {"choices":[{"delta":{"content":"部分公开文本"}}]}\n\n'])
def test_http_200_provider_error_frame_is_not_schema_error_or_retried(prefix):
    async def run():
        calls = []

        def handle(req):
            calls.append(req)
            frame = {
                "error": {
                    "type": "internal_error",
                    "message": "published MTP checkpoint is not materializable",
                }
            }
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text=prefix + "data: " + json.dumps(frame) + "\n\ndata: [DONE]\n\n",
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            gateway = OpenAICompatibleModelGateway(
                base_url="https://model.invalid",
                default_model="fake",
                client=client,
                retry_policy=RetryPolicy(max_retries=2, initial_backoff_seconds=0),
            )
            public = []

            async def emit(text):
                public.append(text)

            with pytest.raises(ModelGatewayError) as caught:
                await gateway.stream_text(request(), emit)
            assert str(caught.value.code) == "MODEL_TEMPORARILY_UNAVAILABLE"
            assert caught.value.details["failure_kind"] == "provider_stream_error"
            assert caught.value.details["provider_type"] == "internal_error"
            assert not caught.value.retryable and len(calls) == 1
            assert public == (["部分公开文本"] if prefix else [])

    asyncio.run(run())


def test_malformed_sse_frame_remains_schema_error():
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    text="data: {broken\n\n",
                )
            )
        ) as client:
            gateway = OpenAICompatibleModelGateway(
                base_url="https://model.invalid", default_model="fake", client=client
            )

            async def emit(_):
                pytest.fail("Malformed stream must not expose public output")

            with pytest.raises(ModelGatewayError) as caught:
                await gateway.stream_text(request(), emit)
            assert str(caught.value.code) == "MODEL_SCHEMA_INVALID"

    asyncio.run(run())
