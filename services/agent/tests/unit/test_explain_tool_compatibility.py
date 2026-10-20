"""Provider rejecting required tool_choice can use validated decisions, never prose."""

import asyncio
import json

import httpx
import pytest

from src.agent.explain_agent import ExplainActor, ExplainTurn
from src.agent.explain_agent.models import ExplainError
from src.domain.enums import ErrorCode
from src.harness.model_gateway import ModelGatewayError, OpenAICompatibleModelGateway

from .test_explain_agent import OWNER, PROJECT, ROW
from .test_explain_edits import agent, tool
from .test_explain_rescan_receipts import CLAIM, REQUEST, RescanBackend


def unsupported():
    return ModelGatewayError(
        ErrorCode.INVALID_REQUEST,
        "tool choice rejected",
        details={
            "status_code": 400,
            "provider_code": "tool_choice_not_supported",
            "provider_type": "invalid_request_error",
        },
    )


def planned(action, **arguments):
    return json.dumps({"decision": {"action": action, **arguments}})


def test_rejected_required_uses_schema_decision_and_real_receipt_once():
    async def run():
        backend = RescanBackend()
        assistant, gateway = agent(
            backend, [CLAIM, unsupported(), planned("rescan_connections", request=REQUEST)]
        )
        turn = ExplainTurn(project_id=PROJECT, connection_id=ROW, message="只重新提取本页终点")
        result = await assistant.ask(turn, ExplainActor(user_id=OWNER))
        assert len(backend.enqueues) == 1 and str(result.rescans[0].id) in result.answer
        assert gateway.calls[2].output_model is not None
        assert (
            not gateway.calls[2].tools
            and gateway.calls[2].tool_choice is None
            and not gateway.calls[2].json_mode
        )
        assert not backend.preparations
        retry = await assistant.ask(turn, ExplainActor(user_id=OWNER))
        assert retry.cached and len(backend.enqueues) == 1 and len(gateway.calls) == 3

    asyncio.run(run())


def test_compatibility_mode_can_query_then_rescan_without_retrying_required():
    async def run():
        backend = RescanBackend()
        assistant, gateway = agent(
            backend,
            [
                CLAIM,
                unsupported(),
                planned("search_connections", query={"connection_id": str(ROW)}),
                planned("rescan_connections", request=REQUEST),
            ],
        )
        result = await assistant.ask(
            ExplainTurn(project_id=PROJECT, connection_id=ROW, message="重新提取"),
            ExplainActor(user_id=OWNER),
        )
        assert len(result.rescans) == 1 and len(gateway.calls) == 4
        assert gateway.calls[3].output_model is not None and not gateway.calls[3].tools

    asyncio.run(run())


def test_rejection_in_later_native_tool_round_also_uses_compatibility():
    async def run():
        backend = RescanBackend()
        assistant, gateway = agent(
            backend,
            [
                CLAIM,
                tool("search_connections", {"connection_id": str(ROW)}),
                unsupported(),
                planned("rescan_connections", request=REQUEST),
            ],
        )
        events = []

        async def emit(event):
            events.append(event)

        result = await assistant.ask(
            ExplainTurn(project_id=PROJECT, connection_id=ROW, message="重新提取"),
            ExplainActor(user_id=OWNER),
            on_event=emit,
        )
        assert len(backend.enqueues) == 1 and len(result.rescans) == 1
        assert gateway.calls[2].tool_choice == "required" and gateway.calls[3].output_model is not None
        assert any(event.type == "rescan_started" for event in events)

    asyncio.run(run())


def test_clarification_does_not_create_a_task_or_expand_scope():
    async def run():
        backend = RescanBackend()
        assistant, _ = agent(
            backend, [CLAIM, unsupported(), planned("clarify", question="请明确需要重扫的连接范围。")]
        )
        with pytest.raises(ExplainError) as error:
            await assistant.ask(
                ExplainTurn(project_id=PROJECT, connection_id=ROW, message="重新提取"),
                ExplainActor(user_id=OWNER),
            )
        assert error.value.code == "RESCAN_SCOPE_UNCLEAR" and not backend.enqueues

    asyncio.run(run())


def test_structured_query_loop_stops_at_existing_tool_budget():
    async def run():
        backend = RescanBackend()
        query = planned("search_connections", query={"connection_id": str(ROW)})
        assistant, gateway = agent(backend, [CLAIM, unsupported(), *[query] * 8])
        with pytest.raises(ExplainError, match="达到上限"):
            await assistant.ask(
                ExplainTurn(project_id=PROJECT, connection_id=ROW, message="重新提取"),
                ExplainActor(user_id=OWNER),
            )
        assert len(gateway.calls) == 10 and not backend.enqueues

    asyncio.run(run())


def test_actual_http_payload_falls_back_without_tool_choice_or_response_format():
    async def run():
        backend = RescanBackend()
        assistant, _ = agent(backend, [])
        bodies = []

        def handle(request):
            body = json.loads(request.content)
            bodies.append(body)
            if len(bodies) == 1:
                return httpx.Response(
                    200, json={"choices": [{"message": {"content": CLAIM}, "finish_reason": "stop"}]}
                )
            if len(bodies) == 2:
                assert body["tool_choice"] == "required"
                return httpx.Response(
                    400,
                    json={"error": {"code": "tool_choice_not_supported", "message": "Unsupported selection"}},
                )
            assert "tool_choice" not in body and "tools" not in body and "response_format" not in body
            assert not any(message["role"] == "tool" for message in body["messages"])
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {"content": planned("rescan_connections", request=REQUEST)},
                            "finish_reason": "stop",
                        }
                    ]
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            assistant.gateway = OpenAICompatibleModelGateway(
                base_url="https://model.invalid", default_model="fake", client=client
            )
            result = await assistant.ask(
                ExplainTurn(project_id=PROJECT, connection_id=ROW, message="重新提取"),
                ExplainActor(user_id=OWNER),
            )
        assert len(bodies) == 3 and len(backend.enqueues) == 1 and result.rescans[0].status == "queued"

    asyncio.run(run())


@pytest.mark.parametrize(
    "response",
    [
        CLAIM,
        planned("commit_connection_edit", accepted=True),
        planned("rescan_connections", request={"scope": {}, "fields": "end"}),
        planned("rescan_connections", request={**REQUEST, "actor": "foreign"}),
        planned("rescan_connections", request={**REQUEST, "result_mode": "replace_scope"}),
    ],
)
def test_invalid_decision_never_enqueues_or_commits(response):
    async def run():
        backend = RescanBackend()
        assistant, _ = agent(backend, [CLAIM, unsupported(), response])
        with pytest.raises((ExplainError, ModelGatewayError)):
            await assistant.ask(
                ExplainTurn(project_id=PROJECT, connection_id=ROW, message="重新提取"),
                ExplainActor(user_id=OWNER),
            )
        assert not backend.enqueues and not backend.preparations

    asyncio.run(run())


@pytest.mark.parametrize("code,status", [("other_invalid_request", 400), ("tool_choice_not_supported", 401)])
def test_other_errors_do_not_trigger_an_extra_model_call(code, status):
    async def run():
        backend = RescanBackend()
        error = ModelGatewayError(
            ErrorCode.INVALID_REQUEST, "rejected", details={"status_code": status, "provider_code": code}
        )
        assistant, gateway = agent(backend, [CLAIM, error])
        with pytest.raises(ModelGatewayError):
            await assistant.ask(
                ExplainTurn(project_id=PROJECT, connection_id=ROW, message="重新提取"),
                ExplainActor(user_id=OWNER),
            )
        assert len(gateway.calls) == 2 and not backend.enqueues

    asyncio.run(run())
