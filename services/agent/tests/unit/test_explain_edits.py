"""Fake models/HTTP only; proposal tools never receive a business-row commit capability."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from src.agent.explain_agent import ExplainActor, ExplainTurn, create_explain_agent
from src.agent.explain_agent.models import ConnectionEditRequest
from src.agent.explain_agent.repository import SupabaseExplanationRepository
from src.harness.model_gateway import FakeModelGateway, ModelResponse, ModelToolCall
from src.infrastructure.supabase_client import SupabaseClient

from .test_explain_agent import OWNER, PROJECT, ROW, Backend

EDIT = {
    "scope": {"workspace_code": "003.C"},
    "operation": {"kind": "remove_terminal_prefix", "endpoint": "end", "prefix": "XD"},
    "reason": "用户要求删除终点前缀",
}


class EditBackend(Backend):
    def __init__(self):
        super().__init__()
        self.proposals = {}
        self.preparations = []

    def request(self, request):
        if request.url.path.endswith("/rpc/prepare_explain_connection_edit"):
            self.calls.append(request)
            value = json.loads(request.content)["value"]
            assert value["actor"] == str(OWNER) and value["project_id"] == str(PROJECT)
            assert value["batch_id"] == "batch-a"
            self.preparations.append(value)
            payload = {
                "proposal_id": value["proposal_id"],
                "project_id": str(PROJECT),
                "batch_id": "batch-a",
                "checksum": "sha256:" + "1" * 64,
                "status": "pending",
                "request": value["request"],
                "matched_count": 1,
                "changed_count": 1,
                "changes": [
                    {
                        "connection_id": str(ROW),
                        "record_version": 1,
                        "principle_number": "003C0101",
                        "before": {"end_terminal": "XD10:1"},
                        "after": {"end_terminal": "10:1"},
                    }
                ],
                "created_at": "2026-10-18T00:00:00Z",
                "expires_at": "2026-10-19T00:00:00Z",
            }
            self.proposals[value["proposal_id"]] = payload
            return httpx.Response(200, json=payload)
        if request.url.path.endswith("/connection_edit_proposals"):
            assert request.method == "GET" and request.url.params["created_by"] == f"eq.{OWNER}"
            return httpx.Response(200, json=list(self.proposals.values()))
        return super().request(request)


def agent(backend, responses):
    gateway = FakeModelGateway(responses)
    repository = SupabaseExplanationRepository(
        SupabaseClient(
            base_url="http://database",
            service_role_key="private-test-key",
            transport=httpx.MockTransport(backend.request),
        )
    )
    return create_explain_agent(repository=repository, gateway=gateway), gateway


def tool(name, arguments):
    return ModelResponse(
        "", None, "fake", 0, 1, tool_calls=(ModelToolCall("call-1", name, json.dumps(arguments)),)
    )


def test_edit_tool_creates_persisted_preview_then_returns_it_on_cached_retry():
    async def run():
        backend = EditBackend()
        assistant, gateway = agent(
            backend, [tool("propose_connection_edit", EDIT), "已生成1行修改对照，确认后才保存。"]
        )
        turn = ExplainTurn(project_id=PROJECT, connection_id=ROW, message="把003.C工作区的终点XD前缀去掉")
        actor = ExplainActor(user_id=OWNER)
        original = deepcopy(backend.row)
        events = []

        async def emit(event):
            events.append(event)

        result = await assistant.ask(turn, actor, on_event=emit)
        assert len(result.proposals) == 1 and result.proposals[0].status == "pending"
        assert backend.row == original  # No business data changed, only a proposal RPC.
        assert len(backend.preparations) == 1
        assert any(e.type == "edit_proposal" for e in events)
        assert {t["function"]["name"] for t in gateway.calls[0].tools} == {
            "search_connections",
            "view_drawings",
            "propose_connection_edit",
            "rescan_connections",
        }
        retry = await assistant.ask(turn, actor)
        assert retry.cached and retry.proposals[0].proposal_id == result.proposals[0].proposal_id
        assert len(gateway.calls) == 2 and len(backend.preparations) == 1

    asyncio.run(run())


@pytest.mark.parametrize(
    "edit",
    [
        {**EDIT, "scope": {}},
        {**EDIT, "actor": str(uuid4())},
        {**EDIT, "operation": {"kind": "sql", "sql": "delete from data"}},
        {**EDIT, "operation": {"kind": "set_fields", "changes": {"project_id": str(uuid4())}}},
        {**EDIT, "operation": {"kind": "set_fields", "changes": {}}},
    ],
)
def test_edit_schema_rejects_unscoped_identity_or_arbitrary_code(edit):
    with pytest.raises(ValidationError):
        ConnectionEditRequest.model_validate(edit)


def test_model_cannot_call_confirmation_and_proposals_survive_narration_failure():
    async def run():
        backend = EditBackend()
        assistant, _ = agent(
            backend, [tool("commit_connection_edit", {"accepted": True}), "我没有提交权限。"]
        )
        turn = ExplainTurn(project_id=PROJECT, connection_id=ROW, message="修改")
        result = await assistant.ask(turn, ExplainActor(user_id=OWNER))
        assert not result.proposals and not backend.preparations
        assistant, _ = agent(
            backend, [tool("propose_connection_edit", EDIT), RuntimeError("fake model down")]
        )
        events = []

        async def emit(event):
            events.append(event)

        with pytest.raises(RuntimeError):
            await assistant.ask(
                turn.model_copy(update={"turn_id": uuid4()}), ExplainActor(user_id=OWNER), on_event=emit
            )
        assert len(backend.proposals) == 1 and any(e.proposal for e in events)

    asyncio.run(run())


def test_unbacked_preview_claim_is_retracted_and_repaired_with_real_tool():
    async def run():
        backend = EditBackend()
        assistant, gateway = agent(
            backend,
            [
                "已按你的要求生成修改预览，匹配行数：1，请在前端确认。",
                tool("propose_connection_edit", EDIT),
                "真实修改方案已保存，请核对后点击确认修改。",
            ],
        )
        events = []

        async def emit(event):
            events.append(event)

        result = await assistant.ask(
            ExplainTurn(project_id=PROJECT, connection_id=ROW, message="把终点XD前缀去掉"),
            ExplainActor(user_id=OWNER),
            on_event=emit,
        )
        assert len(backend.preparations) == 1 and len(result.proposals) == 1
        assert len(gateway.calls) == 3
        assert any(event.type == "answer_reset" for event in events)
        assert "匹配行数" not in result.answer
        assert result.answer == "真实修改方案已保存，请核对后点击确认修改。"
        assert backend.row["end_terminal"] == "XD10:1"

    asyncio.run(run())


def test_repeated_unbacked_claim_fails_without_manufacturing_confirmable_data():
    async def run():
        backend = EditBackend()
        assistant, gateway = agent(backend, ["已生成修改预览", "修改方案已生成，请确认"])
        from src.agent.explain_agent.models import ExplainError

        with pytest.raises(ExplainError, match="未生成可确认"):
            await assistant.ask(
                ExplainTurn(project_id=PROJECT, connection_id=ROW, message="修改终点为X3:1"),
                ExplainActor(user_id=OWNER),
            )
        assert len(gateway.calls) == 2 and not backend.preparations and not backend.proposals

    asyncio.run(run())


@pytest.mark.parametrize(
    ("text", "claimed"),
    [
        ("已按你的要求生成修改预览", True),
        ("修改方案已生成，请核对", True),
        ("修改预览：匹配行数：1", True),
        ("不要声称已生成修改预览", False),
        ("不能说已经生成修改方案", False),
        ("查询匹配行数：1", False),
        ("历史说明写着“已生成修改预览”，不能视为执行回执", False),
        ("尚未生成修改方案，请提供明确的新值", False),
    ],
)
def test_preview_receipt_guard_does_not_treat_instructions_or_quotes_as_actions(text, claimed):
    from src.agent.explain_agent.graph import unbacked_edit_claim

    assert unbacked_edit_claim(text) is claimed
