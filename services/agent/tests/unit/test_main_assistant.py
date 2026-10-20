from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.agent.main_assistant.api import create_assistant_router
from src.agent.main_assistant.models import AssistantInternalTurn, AssistantScope, AssistantToolCall
from src.agent.main_assistant.service import MainAssistant, RemoteExecutor
from src.agent.main_assistant.tools import definitions
from src.config import AgentSettings
from src.harness.model_gateway import FakeModelGateway, ModelResponse, ModelToolCall


def response(text="", calls=(), reason=None):
    return ModelResponse(text, None, "fake", 0, 1, finish_reason=reason, tool_calls=tuple(calls))


class Executor:
    def __init__(self, results):
        self.results, self.calls = list(results), []

    async def execute(self, call):
        self.calls.append(call)
        return self.results.pop(0)


def invoke(responses, results, message="查找020.U工作区"):
    gateway = FakeModelGateway(responses)
    agent, executor, events = MainAssistant(gateway), Executor(results), []
    turn = AssistantInternalTurn(
        conversation_id=uuid4(), turn_id=uuid4(), message=message, scope=AssistantScope()
    )

    async def emit(event):
        events.append(event)

    asyncio.run(agent.ask(turn, executor, emit))
    return gateway, executor, events


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("No paid model calls")

    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)


def test_lookup_navigation_uses_receipt_ids_and_no_publish_tools():
    project, workspace = str(uuid4()), str(uuid4())
    target = {"project_id": project, "workspace_id": workspace, "workspace_code": "020.U"}
    _, executor, events = invoke(
        [
            response(calls=[ModelToolCall("find", "find_targets", '{"workspace_code":"020.U"}')]),
            response(calls=[ModelToolCall("nav", "navigate_to", json.dumps({"scope": target}))]),
            response("已打开020.U"),
            '{"required_tool":"navigate_to","claims_execution":true}',
        ],
        [
            {"targets": [{"scope": target}], "action_id": str(uuid4())},
            {"event": "navigate", "scope": target, "destination": "project", "action_id": str(uuid4())},
        ],
    )
    assert len(executor.calls) == 2
    assert [e.data["scope"] for e in events if e.type == "navigate"] == [target]
    assert events[-1].type == "completed"
    names = {d["function"]["name"] for d in definitions()}
    assert not any("publish" in name or "commit" in name or "apply" in name for name in names)


def test_explicit_rescan_returns_task_without_second_child_model():
    _, executor, events = invoke(
        [
            response(calls=[ModelToolCall("r", "start_rescan", '{"scope":{"workspace_code":"020.U"}}')]),
            '{"required_tool":"start_rescan","claims_execution":false}',
        ],
        [
            {
                "event": "task_started",
                "kind": "rescan",
                "run_id": str(uuid4()),
                "action_id": str(uuid4()),
                "status": "queued",
            }
        ],
        "重扫020.U",
    )
    assert executor.calls[0].name == "start_rescan"
    assert any(e.type == "task_started" for e in events)


def test_delegated_answer_is_returned_without_rewrite_and_invalid_tool_cannot_execute():
    _, executor, events = invoke(
        [
            response(calls=[ModelToolCall("x", "explain_scope", '{"question":"解释这组终点"}')]),
            '{"required_tool":"explain_scope","claims_execution":false}',
        ],
        [{"delegated": True, "answer": "原图只能支持XA:1，目标页证据不足。", "action_id": str(uuid4())}],
    )
    assert (
        "".join(e.message or "" for e in events if e.type == "answer_delta")
        == "原图只能支持XA:1，目标页证据不足。"
    )
    _, executor, events = invoke(
        [
            response(calls=[ModelToolCall("bad", "publish_profile", "{}")]),
            response("已发布规则"),
            '{"required_tool":null,"claims_execution":true}',
        ],
        [],
    )
    assert not executor.calls
    assert any(e.type == "error" for e in events)
    assert not any(e.type == "answer_delta" for e in events)


def test_rule_followup_does_not_expand_into_extra_connection_edit():
    diagnosis = {
        "delegated": True,
        "answer": "规则差异已生成，提取后的数据可由用户后续校验。",
        "action_id": str(uuid4()),
        "event": "proposal_ready",
        "kind": "profile",
        "proposal_id": str(uuid4()),
    }
    gateway, executor, events = invoke(
        [
            response(
                calls=[
                    ModelToolCall(
                        "rules", "diagnose_profile", '{"question":"开始修改规则","propose_changes":true}'
                    ),
                    ModelToolCall("extra", "propose_connection_edit", '{"question":"完善旧线表"}'),
                ]
            ),
            '{"required_tool":"diagnose_profile","claims_execution":false,"propose_profile_changes":true}',
        ],
        [diagnosis],
        "开始修改",
    )
    assert [call.name for call in executor.calls] == ["diagnose_profile"]
    review = json.loads(gateway.calls[1].messages[-1]["content"])
    assert review["candidate_reply"] == ""
    assert events[-1].data["required_tool"] == "diagnose_profile"
    assert not any(event.type == "error" for event in events)
    assert any(event.type == "proposal_ready" for event in events)


def test_truncation_never_claims_completion():
    with pytest.raises(ValueError, match="截断"):
        invoke([response("partial", reason="length")], [])


def test_unbacked_rescan_claim_is_withheld_then_repaired_once():
    run_id, action_id = str(uuid4()), str(uuid4())
    gateway, executor, events = invoke(
        [
            response("已创建重扫任务，任务ID：02262025-000001，状态queued。"),
            '{"required_tool":"start_rescan","claims_execution":true}',
            response(calls=[ModelToolCall("repair", "start_rescan", '{"scope":{"workspace_code":"GCR.1"}}')]),
        ],
        [
            {
                "event": "task_started",
                "kind": "rescan",
                "run_id": run_id,
                "action_id": action_id,
                "status": "queued",
            }
        ],
        "GCR102图纸的线表重新扫面一遍",
    )
    assert len(executor.calls) == 1 and executor.calls[0].name == "start_rescan"
    text = "".join(event.message or "" for event in events if event.type == "answer_delta")
    assert "02262025-000001" not in text and run_id in text
    assert events[-1].data["completion_verified"] is True
    assert events[-1].data["action_id"] == action_id


def test_rescan_without_tool_after_repair_fails_without_fabricated_answer():
    _, executor, events = invoke(
        [
            response("已创建任务，任务ID：02262025-000001，状态queued。"),
            '{"required_tool":"start_rescan","claims_execution":true}',
            response("已经开始处理，请稍候。"),
        ],
        [],
        "GCR102图纸的线表重新扫面一遍",
    )
    assert not executor.calls
    assert not any(event.type == "answer_delta" for event in events)
    assert any(event.type == "error" and "未启动" in (event.message or "") for event in events)


@pytest.mark.parametrize("text", ["你好，我可以帮助查看图纸。", "重扫会先生成候选，确认后才替换旧结果。"])
def test_chat_and_rescan_explanation_do_not_start_tasks(text):
    _, executor, events = invoke(
        [response(text), '{"required_tool":null,"claims_execution":false}'],
        [],
        "你好" if "你好" in text else "不需要重扫，只解释一下重扫机制",
    )
    assert not executor.calls
    assert "".join(event.message or "" for event in events if event.type == "answer_delta") == text


def test_execution_request_cannot_finish_with_only_promise_or_lookup():
    _, executor, events = invoke(
        [
            response("好的，我来处理。"),
            '{"required_tool":"start_rescan","claims_execution":false}',
            response(calls=[ModelToolCall("find", "find_targets", '{"drawing_page":"GCR102"}')]),
            response("已经找到图纸，我来处理。"),
        ],
        [{"targets": [{"scope": {"project_id": str(uuid4())}}], "action_id": str(uuid4())}],
        "重新扫描GCR102",
    )
    assert len(executor.calls) == 1 and executor.calls[0].name == "find_targets"
    assert not any(event.type == "answer_delta" for event in events)
    assert any(event.type == "error" for event in events)


@pytest.mark.parametrize(
    "result",
    [
        {"error": "无权限", "code": "ACCESS_DENIED"},
        {
            "event": "task_started",
            "kind": "rescan",
            "run_id": "02262025-000001",
            "action_id": str(uuid4()),
            "status": "queued",
        },
    ],
)
def test_failed_or_invalid_rescan_receipt_never_becomes_task_card(result):
    _, executor, events = invoke(
        [
            response(calls=[ModelToolCall("r", "start_rescan", '{"scope":{"workspace_code":"GCR.1"}}')]),
        ],
        [result],
        "重扫GCR102",
    )
    assert len(executor.calls) == 1
    assert not any(event.type in {"task_started", "answer_delta"} for event in events)
    assert any(event.type == "error" for event in events)


def test_real_rescan_acknowledgement_never_uses_model_fabricated_id():
    run_id = str(uuid4())
    gateway, _, events = invoke(
        [
            response(calls=[ModelToolCall("r", "start_rescan", "{}")]),
            '{"required_tool":"start_rescan","claims_execution":false}',
            response("任务ID：fake-id"),
        ],
        [
            {
                "event": "task_started",
                "kind": "rescan",
                "action_id": str(uuid4()),
                "run_id": run_id,
                "status": "queued",
            }
        ],
        "重扫当前页",
    )
    assert len(gateway.calls) == 2
    assert run_id in "".join(event.message or "" for event in events)
    assert "fake-id" not in "".join(event.message or "" for event in events)


def test_ambiguous_lookup_requests_selection_without_starting_rescan():
    _, executor, events = invoke(
        [
            response(calls=[ModelToolCall("find", "find_targets", '{"drawing_page":"GCR102"}')]),
            response("请先选择项目。"),
            '{"required_tool":"start_rescan","claims_execution":false}',
        ],
        [
            {
                "action_id": str(uuid4()),
                "event": "selection_required",
                "targets": [{"scope": {"project_id": str(uuid4())}}, {"scope": {"project_id": str(uuid4())}}],
            }
        ],
        "重扫GCR102",
    )
    assert [call.name for call in executor.calls] == ["find_targets"]
    assert events[-1].data["disposition"] == "clarification"
    assert not any(event.type == "task_started" for event in events)


def test_duplicate_range_lookup_hands_off_edit_and_rule_diagnosis_once():
    project = str(uuid4())
    rows = [
        {
            "id": str(uuid4()),
            "principle_number": f"082R50{i:02}",
            "end_terminal": f"+10-MA{51 if i <= 3 else 52}:{i}",
        }
        for i in range(1, 6)
    ]
    query = json.dumps(
        {"scope": {"project_id": project, "pdf_page_number": 1}, "principle_number": "082R5001-05"}
    )
    gateway, executor, events = invoke(
        [
            response(calls=[ModelToolCall("s1", "search_connections", query)]),
            response(calls=[ModelToolCall("s2", "search_connections", query)]),
            '{"required_tool":"propose_connection_edit","required_tools":["propose_connection_edit","diagnose_profile"],"claims_execution":false,"propose_profile_changes":true}',
        ],
        [
            {
                "action_id": str(uuid4()),
                "scope": {"project_id": project, "pdf_page_number": 1},
                "rows": rows,
                "has_more": False,
                "query_interpretation": {"kind": "number_range", "input": "082R5001-05"},
            },
            {
                "action_id": str(uuid4()),
                "event": "proposal_ready",
                "proposal_id": str(uuid4()),
                "delegated": True,
                "answer": "已生成5条记录的修订候选，尚未应用。",
            },
            {
                "action_id": str(uuid4()),
                "event": "proposal_ready",
                "proposal_id": str(uuid4()),
                "delegated": True,
                "answer": "已诊断并生成规则差异，尚未发布。",
            },
        ],
        "R50页082R5001-05多出了MA51，修改一下，然后在规则层面做个更新",
    )
    assert [call.name for call in executor.calls] == [
        "search_connections",
        "propose_connection_edit",
        "diagnose_profile",
    ]
    assert len(gateway.calls) == 3
    assert executor.calls[2].arguments["propose_changes"] is True
    assert set(executor.calls[1].arguments["scope"]["connection_ids"]) == {row["id"] for row in rows}
    assert sum(event.type == "proposal_ready" for event in events) == 2
    assert events[-1].data["verification_version"] == 2
    assert {item["tool_name"] for item in events[-1].data["action_receipts"]} == {
        "propose_connection_edit",
        "diagnose_profile",
    }
    text = "".join(event.message or "" for event in events if event.type == "answer_delta")
    assert "修订候选" in text and "规则差异" in text


def test_repeated_empty_lookup_stops_before_eight_rounds_with_specific_error():
    query = '{"principle_number":"not-found"}'
    gateway, executor, events = invoke(
        [
            response(calls=[ModelToolCall("s1", "search_connections", query)]),
            response(calls=[ModelToolCall("s2", "search_connections", query)]),
            '{"required_tool":"propose_connection_edit","claims_execution":false}',
            response(calls=[ModelToolCall("s3", "search_connections", query)]),
        ],
        [{"action_id": str(uuid4()), "rows": [], "has_more": False}],
        "修订没找到的记录",
    )
    assert len(executor.calls) == 1 and len(gateway.calls) == 4
    assert any(
        event.type == "error" and event.data.get("code") == "ASSISTANT_NO_PROGRESS" for event in events
    )
    assert "search_connections" not in {tool["function"]["name"] for tool in gateway.calls[-1].tools}


def test_repeated_readonly_lookup_still_presents_actual_rows_and_coverage():
    query = '{"principle_number":"082R5001"}'
    _, executor, events = invoke(
        [
            response(calls=[ModelToolCall("s1", "search_connections", query)]),
            response(calls=[ModelToolCall("s2", "search_connections", query)]),
            '{"required_tool":"search_connections","claims_execution":false}',
        ],
        [
            {
                "action_id": str(uuid4()),
                "rows": [
                    {
                        "principle_number": "082R5001",
                        "start_terminal": "XD3:251",
                        "end_terminal": "+10-MA51:2",
                    }
                ],
                "has_more": True,
            }
        ],
        "查看这个编号的连接",
    )
    assert len(executor.calls) == 1
    text = "".join(event.message or "" for event in events if event.type == "answer_delta")
    assert "+10-MA51:2" in text and "仍有后续记录" in text


def test_internal_router_requires_service_identity_and_never_exposes_turn_token():
    app = FastAPI()
    settings = AgentSettings(internal_token="test-internal")
    app.state.settings = settings
    app.include_router(
        create_assistant_router(
            settings,
            MainAssistant(
                FakeModelGateway(
                    ["你好，请说明需要处理的图纸。", '{"required_tool":null,"claims_execution":false}']
                )
            ),
        )
    )
    body = {"conversation_id": str(uuid4()), "turn_id": str(uuid4()), "message": "你好", "scope": {}}
    with TestClient(app) as client:
        assert client.get("/v1/assistant/capabilities").status_code == 401
        headers = {
            "Authorization": "Bearer test-internal",
            "X-Assistant-Turn-Token": "private-turn-token-" * 3,
        }
        result = client.post("/v1/assistant/turns/stream", json=body, headers=headers)
        assert result.status_code == 200 and "completed" in result.text
        assert "private-turn-token" not in result.text and "test-internal" not in result.text


def test_diagnosis_failure_stops_before_repeated_calls_or_completion_claim():
    _, executor, events = invoke(
        [response(calls=[ModelToolCall("d", "diagnose_profile", '{"question":"检查规则"}')])],
        [{"error": "规则诊断接口异常，请重载服务后重试", "code": "ASSISTANT_TOOL_INTERNAL_ERROR"}],
        "查看一下规则，看看能否更新",
    )
    assert len(executor.calls) == 1
    assert events[-1].data["status"] == "failed"
    error = next(event for event in events if event.type == "error")
    assert "规则诊断接口异常" in error.message
    assert error.data["code"] == "ASSISTANT_TOOL_INTERNAL_ERROR"
    assert not any(event.type == "answer_delta" for event in events)


def test_failed_rule_task_keeps_existing_rescan_receipt_without_repeating():
    _, executor, events = invoke(
        [
            response(calls=[ModelToolCall("r", "start_rescan", "{}")]),
            '{"required_tool":null,"required_tools":["start_rescan","diagnose_profile"],"claims_execution":false}',
            response(calls=[ModelToolCall("d", "diagnose_profile", '{"question":"检查规则"}')]),
        ],
        [
            {
                "action_id": str(uuid4()),
                "run_id": str(uuid4()),
                "kind": "rescan",
                "status": "queued",
                "event": "task_started",
            },
            {"error": "规则助手暂不可用", "code": "AGENT_UNAVAILABLE"},
        ],
        "重扫然后检查规则",
    )
    assert len(executor.calls) == 2
    assert sum(event.type == "task_started" for event in events) == 1
    error = next(event for event in events if event.type == "error")
    assert "规则助手暂不可用" in error.message and "保留" in error.message
    assert events[-1].data["status"] == "failed"


@pytest.mark.parametrize("payload", [None, {"detail": "private-server-error"}, ["private-server-error"]])
def test_remote_tool_nonstructured_error_is_safe(monkeypatch, payload):
    async def post(self, *args, **kwargs):
        return (
            httpx.Response(500, json=payload)
            if payload is not None
            else httpx.Response(500, text="private-server-error")
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    result = asyncio.run(
        RemoteExecutor(AgentSettings(), uuid4(), "private-token").execute(
            AssistantToolCall(name="diagnose_profile", arguments={"question": "检查规则"})
        )
    )
    assert result["code"] == "TOOL_FAILED"
    assert "private" not in json.dumps(result)
