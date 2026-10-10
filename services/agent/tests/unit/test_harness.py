from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from pydantic import BaseModel

from agent_service.domain.enums import ErrorCode, RunType, ScopeType
from agent_service.domain.errors import AgentServiceError
from agent_service.domain.models.runs import CreateRunRequest, ProfileRef, RunScope
from agent_service.harness import (
    ContextBuilder,
    ContextResource,
    FakeModelGateway,
    InMemoryCheckpointStore,
    InMemoryRunRepository,
    ModelRequest,
    OpenAICompatibleModelGateway,
    ToolCallContext,
    ToolDefinition,
    ToolRegistry,
    checkpoint_key,
)
from agent_service.harness.retry import RetryPolicy


class ParsedAnswer(BaseModel):
    value: str


class ToolInput(BaseModel):
    value: int


class ToolOutput(BaseModel):
    doubled: int


def test_fake_model_gateway_validates_structured_output_without_network() -> None:
    async def run() -> None:
        gateway = FakeModelGateway(['{"value":"ok"}'])
        response = await gateway.invoke(
            ModelRequest(
                agent_name="test-agent",
                run_id="run-1",
                messages=[{"role": "user", "content": "test"}],
                output_model=ParsedAnswer,
            )
        )
        assert isinstance(response.parsed, ParsedAnswer)
        assert response.parsed.value == "ok"
        assert len(gateway.calls) == 1

    asyncio.run(run())


def test_fake_model_gateway_rejects_invalid_json() -> None:
    async def run() -> None:
        gateway = FakeModelGateway(["not-json"])
        with pytest.raises(AgentServiceError) as error:
            await gateway.invoke(
                ModelRequest(
                    agent_name="test-agent",
                    run_id="run-1",
                    messages=[{"role": "user", "content": "test"}],
                    output_model=ParsedAnswer,
                )
            )
        assert error.value.code == ErrorCode.MODEL_SCHEMA_INVALID

    asyncio.run(run())


def test_openai_gateway_retries_transient_http_error() -> None:
    async def run() -> None:
        attempts = 0

        async def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(503, json={"error": "temporary"})
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": '{"value":"ok"}'}}]},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = OpenAICompatibleModelGateway(
                base_url="http://model.test/v1",
                default_model="fake-vlm",
                retry_policy=RetryPolicy(max_retries=1, initial_backoff_seconds=0),
                client=client,
            )
            response = await gateway.invoke(
                ModelRequest(
                    agent_name="test-agent",
                    run_id="run-1",
                    messages=[{"role": "user", "content": "test"}],
                    output_model=ParsedAnswer,
                )
            )
        assert attempts == 2
        assert response.attempts == 2

    asyncio.run(run())


def test_openai_gateway_serializes_structured_message_content_for_provider() -> None:
    async def run() -> None:
        received: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            received.update(json.loads(request.content))
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": '{"value":"ok"}'}}]},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = OpenAICompatibleModelGateway(
                base_url="http://model.test/v1",
                default_model="fake-vlm",
                client=client,
            )
            response = await gateway.invoke(
                ModelRequest(
                    agent_name="supervisor",
                    run_id="run-structured-content",
                    messages=[
                        {"role": "system", "content": "system"},
                        {"role": "user", "content": {"message": "识别", "attachment_count": 1}},
                    ],
                    output_model=ParsedAnswer,
                )
            )

        messages = received["messages"]
        assert isinstance(messages, list)
        user_content = messages[1]["content"]
        assert isinstance(user_content, str)
        assert '"message":"识别"' in user_content
        assert isinstance(response.parsed, ParsedAnswer)

    asyncio.run(run())


def test_openai_gateway_does_not_request_provider_structured_output_by_default() -> None:
    async def run() -> None:
        received: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            received.update(json.loads(request.content))
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": '{"value":"ok"}'}}]},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = OpenAICompatibleModelGateway(
                base_url="http://model.test/v1",
                default_model="fake-vlm",
                client=client,
            )
            await gateway.invoke(
                ModelRequest(
                    agent_name="supervisor",
                    run_id="run-no-provider-structured-output",
                    messages=[{"role": "user", "content": "识别"}],
                    output_model=ParsedAnswer,
                )
            )

        assert "response_format" not in received

    asyncio.run(run())


def test_openai_gateway_can_opt_into_provider_structured_output() -> None:
    async def run() -> None:
        received: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            received.update(json.loads(request.content))
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": '{"value":"ok"}'}}]},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = OpenAICompatibleModelGateway(
                base_url="http://model.test/v1",
                default_model="fake-vlm",
                client=client,
            )
            await gateway.invoke(
                ModelRequest(
                    agent_name="test-agent",
                    run_id="run-provider-structured-output",
                    messages=[{"role": "user", "content": "识别"}],
                    output_model=ParsedAnswer,
                    json_mode=True,
                )
            )

        assert received["response_format"] == {"type": "json_object"}

    asyncio.run(run())


def test_openai_gateway_retries_timeout() -> None:
    async def run() -> None:
        attempts = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise httpx.ReadTimeout("temporary timeout", request=request)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": '{"value":"ok"}'}}]},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = OpenAICompatibleModelGateway(
                base_url="http://model.test/v1",
                default_model="fake-vlm",
                retry_policy=RetryPolicy(max_retries=1, initial_backoff_seconds=0),
                client=client,
            )
            response = await gateway.invoke(
                ModelRequest(
                    agent_name="test-agent",
                    run_id="run-1",
                    messages=[{"role": "user", "content": "test"}],
                    output_model=ParsedAnswer,
                )
            )
        assert attempts == 2
        assert response.attempts == 2

    asyncio.run(run())


def test_openai_gateway_does_not_retry_schema_error() -> None:
    async def run() -> None:
        attempts = 0

        async def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": '{"wrong":"value"}'}}]},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = OpenAICompatibleModelGateway(
                base_url="http://model.test/v1",
                default_model="fake-vlm",
                retry_policy=RetryPolicy(max_retries=3, initial_backoff_seconds=0),
                client=client,
            )
            with pytest.raises(AgentServiceError) as error:
                await gateway.invoke(
                    ModelRequest(
                        agent_name="test-agent",
                        run_id="run-1",
                        messages=[{"role": "user", "content": "test"}],
                        output_model=ParsedAnswer,
                    )
                )
        assert attempts == 1
        assert error.value.code == ErrorCode.MODEL_SCHEMA_INVALID

    asyncio.run(run())


def test_tool_registry_enforces_agent_allowlist() -> None:
    async def handler(_context: ToolCallContext, payload: BaseModel) -> ToolOutput:
        validated = ToolInput.model_validate(payload)
        return ToolOutput(doubled=validated.value * 2)

    async def run() -> None:
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="double",
                description="test tool",
                allowed_agents=frozenset({"allowed-agent"}),
                input_model=ToolInput,
                output_model=ToolOutput,
                handler=handler,
            )
        )
        result = await registry.invoke(
            "double",
            ToolCallContext(
                run_id="run-1",
                project_id="project-1",
                agent_name="allowed-agent",
                scope_id="scope-1",
            ),
            {"value": 3},
        )
        assert result == ToolOutput(doubled=6)

        with pytest.raises(AgentServiceError) as error:
            await registry.invoke(
                "double",
                ToolCallContext(
                    run_id="run-1",
                    project_id="project-1",
                    agent_name="blocked-agent",
                    scope_id="scope-1",
                ),
                {"value": 3},
            )
        assert error.value.code == ErrorCode.TOOL_NOT_ALLOWED

    asyncio.run(run())


def test_checkpoint_uses_optimistic_revision() -> None:
    async def run() -> None:
        store = InMemoryCheckpointStore()
        assert await store.save("run:stage:item", {"done": False}) == 1
        assert (
            await store.save(
                "run:stage:item",
                {"done": True},
                expected_revision=1,
            )
            == 2
        )
        with pytest.raises(AgentServiceError):
            await store.save(
                "run:stage:item",
                {"done": True},
                expected_revision=1,
            )

    asyncio.run(run())


def test_checkpoint_key_contains_all_idempotency_dimensions() -> None:
    assert checkpoint_key("run-1", "extraction", "page-scan", "drawing-2") == (
        "run-1:extraction:page-scan:drawing-2"
    )


def test_run_repository_reuses_same_idempotency_request() -> None:
    async def run() -> None:
        repository = InMemoryRunRepository()
        request = CreateRunRequest(
            run_type=RunType.FULL_EXTRACTION,
            project_id="project-1",
            source_document_id="document-1",
            requested_by="user-1",
            scope=RunScope(type=ScopeType.PROJECT, id="project-1"),
        )
        first = await repository.create(request, "idempotency-1")
        second = await repository.create(request, "idempotency-1")
        assert first.agent_run_id == second.agent_run_id

    asyncio.run(run())


def test_context_builder_enforces_image_budget() -> None:
    builder = ContextBuilder(max_images=1, max_total_bytes=100)
    resources = [
        ContextResource(resource_id="a", kind="drawing_image", object_ref="drawing-a", size_bytes=20),
        ContextResource(resource_id="b", kind="drawing_image", object_ref="drawing-b", size_bytes=20),
    ]
    with pytest.raises(ValueError, match="images"):
        builder.build(
            run_id="run-1",
            agent_name="page-scanner",
            profile=ProfileRef(key="zh", version="1.0.0"),
            resources=resources,
        )
