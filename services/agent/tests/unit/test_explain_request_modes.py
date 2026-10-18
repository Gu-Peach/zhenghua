"""Automatic explanations do not enqueue rescans or inherit unrelated project history."""

import asyncio
import json
from uuid import uuid4

import httpx
import pytest

from src.agent.explain_agent import ExplainActor, ExplainTurn, create_explain_agent
from src.agent.explain_agent.models import ExplainError
from src.agent.explain_agent.repository import SupabaseExplanationRepository
from src.config import AgentSettings
from src.harness.model_gateway import FakeModelGateway
from src.infrastructure.supabase_client import SupabaseClient
from tests.unit.test_explain_agent import OWNER, PROJECT, ROW, Backend
from tests.unit.test_explain_edits import tool


def repository(backend):
    return SupabaseExplanationRepository(
        SupabaseClient(
            base_url="https://db.invalid",
            service_role_key="fixture",
            transport=httpx.MockTransport(backend.request),
        )
    )


def test_readonly_automatic_turn_hides_and_denies_rescan_tool():
    async def run():
        backend = Backend()
        gateway = FakeModelGateway(
            [
                tool("rescan_connections", {"scope": {"connection_ids": [str(ROW)]}, "fields": "all"}),
                "本轮仅说明已保存的连接依据。",
            ]
        )
        assistant = create_explain_agent(AgentSettings(), repository=repository(backend), gateway=gateway)
        result = await assistant.ask(
            ExplainTurn(project_id=PROJECT, connection_id=ROW, allow_rescan=False),
            ExplainActor(user_id=OWNER),
        )
        assert not result.rescans
        assert "rescan_connections" not in {item["function"]["name"] for item in gateway.calls[0].tools}
        replies = [
            json.loads(item["content"]) for item in gateway.calls[1].messages if item["role"] == "tool"
        ]
        assert replies[0]["error"] == "RESCAN_NOT_REQUESTED"
        assert not any("enqueue_connection_rescan" in str(call.url) for call in backend.calls)

    asyncio.run(run())


@pytest.mark.parametrize("explicit", [False, True])
def test_only_current_conversation_history_is_implicit_but_explicit_task_can_be_read(explicit):
    async def run():
        identifier, other_conversation = uuid4(), uuid4()
        history = {
            "id": str(identifier),
            "project_id": str(PROJECT),
            "conversation_id": str(other_conversation),
            "batch_id": "batch-a",
            "status": "applied",
            "stage": "ready",
            "request": {"scope": {"connection_ids": [str(ROW)]}},
            "profile": {},
            "created_at": "now",
            "updated_at": "now",
        }

        class HistoryBackend(Backend):
            def request(self, request):
                if request.url.path.endswith("/connection_rescan_runs"):
                    self.history_query = dict(request.url.params)
                    selected = (
                        explicit or request.url.params.get("conversation_id") == f"eq.{other_conversation}"
                    )
                    return httpx.Response(200, json=[history] if selected else [])
                return super().request(request)

        backend = HistoryBackend()
        current = ExplainTurn(
            project_id=PROJECT,
            connection_id=ROW,
            batch_id="batch-a",
            rescan_id=identifier if explicit else None,
        )
        result = await repository(backend).rescans(current, ExplainActor(user_id=OWNER))
        assert len(result) == (1 if explicit else 0)
        assert backend.history_query["created_by"] == f"eq.{OWNER}"
        if not explicit:
            assert backend.history_query["conversation_id"] == f"eq.{current.conversation_id}"

    asyncio.run(run())


def test_history_response_must_not_override_bound_conversation():
    async def run():
        class WrongHistory(Backend):
            def request(self, request):
                if request.url.path.endswith("/connection_rescan_runs"):
                    return httpx.Response(
                        200,
                        json=[
                            {
                                "id": str(uuid4()),
                                "project_id": str(PROJECT),
                                "conversation_id": str(uuid4()),
                                "batch_id": "batch-a",
                                "status": "ready",
                                "stage": "ready",
                                "request": {"scope": {"connection_ids": [str(ROW)]}},
                                "profile": {},
                                "created_at": "now",
                                "updated_at": "now",
                            }
                        ],
                    )
                return super().request(request)

        with pytest.raises(ExplainError, match="不属于请求范围"):
            await repository(WrongHistory()).rescans(
                ExplainTurn(project_id=PROJECT, connection_id=ROW, batch_id="batch-a"),
                ExplainActor(user_id=OWNER),
            )

    asyncio.run(run())
