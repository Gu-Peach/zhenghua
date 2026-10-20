"""Rescan success requires a receipt from this turn, using only Fake HTTP/model calls."""

import asyncio
import json
from copy import deepcopy
from uuid import uuid4

import httpx
import pytest

from src.agent.explain_agent import ExplainActor, ExplainTurn
from src.agent.explain_agent.models import ExplainError
from src.agent.explain_agent.rescan_receipts import requests_rescan

from .test_explain_agent import OWNER, PROJECT, ROW
from .test_explain_edits import EditBackend, agent, tool

CLAIM = "已按修正后的5个起点端子创建“仅重扫终点”任务。任务状态：queued（已入队，尚未完成）。"
REQUEST = {"scope": {"connection_ids": [str(ROW)]}, "fields": "end", "instructions": "沿线重提终点"}


class RescanBackend(EditBackend):
    def __init__(self):
        super().__init__()
        self.runs = {}
        self.enqueues = []
        self.reject = False

    def request(self, request):
        if request.url.path.endswith("/rpc/enqueue_connection_rescan"):
            value = json.loads(request.content)["value"]
            self.enqueues.append(value)
            if self.reject:
                return httpx.Response(400, json={"message": "invalid scope"})
            run = {
                "id": value["id"],
                "project_id": str(PROJECT),
                "conversation_id": value["conversation_id"],
                "batch_id": "batch-a",
                "request": value["request"],
                "status": "queued",
                "stage": "queued",
                "profile": {"key": "zh", "version": "1.0.0"},
                "created_at": "now",
                "updated_at": "now",
            }
            self.runs[run["id"]] = run
            return httpx.Response(200, json=run)
        if request.url.path.endswith("/connection_rescan_runs"):
            return httpx.Response(200, json=list(self.runs.values()))
        return super().request(request)


@pytest.mark.parametrize(
    "answer", ["[turn 4 tool call]正在读取图纸页 002C06（PDF 52）…", "好的，接下来处理。"]
)
def test_explicit_recognition_cannot_finish_with_only_progress_or_acknowledgement(answer):
    async def run():
        backend = RescanBackend()
        backend.row["evidence"]["record"]["source_note"] = "旧证据长文本" * 20000
        original = deepcopy(backend.row)
        assistant, gateway = agent(backend, [answer, tool("rescan_connections", REQUEST), "已入队。"])
        events = []

        async def emit(event):
            events.append(event)

        result = await assistant.ask(
            ExplainTurn(
                project_id=PROJECT,
                connection_id=ROW,
                message="u2,v2,w2,n这四个起点对应终点找错了，重新识别一下",
            ),
            ExplainActor(user_id=OWNER),
            on_event=emit,
        )
        assert len(backend.enqueues) == 1 and len(gateway.calls) == 3
        assert "正在读取" not in result.answer and str(result.rescans[0].id) in result.answer
        assert len(json.dumps(gateway.calls[0].messages, ensure_ascii=False)) < 25000
        assert any(event.type == "answer_reset" for event in events)
        assert not any(event.type == "answer_delta" and "正在读取" in (event.delta or "") for event in events)
        assert backend.row == original

    asyncio.run(run())


def test_explicit_recognition_without_any_tool_fails_after_one_repair():
    async def run():
        backend = RescanBackend()
        assistant, gateway = agent(backend, ["正在读取图纸页002C06…", "马上处理，请稍等。"])
        with pytest.raises(ExplainError) as error:
            await assistant.ask(
                ExplainTurn(project_id=PROJECT, connection_id=ROW, message="重新识别一下"),
                ExplainActor(user_id=OWNER),
            )
        assert error.value.code == "RESCAN_NOT_CREATED" and len(gateway.calls) == 2
        assert not backend.enqueues

    asyncio.run(run())


def test_readonly_progress_prose_cannot_be_a_completed_answer():
    async def run():
        backend = RescanBackend()
        assistant, _ = agent(backend, ["[turn 4 tool call]正在读取图纸页002C06（PDF 52）…"])
        with pytest.raises(ExplainError) as error:
            await assistant.ask(
                ExplainTurn(
                    project_id=PROJECT, connection_id=ROW, message="看一下原图说明", allow_rescan=False
                ),
                ExplainActor(user_id=OWNER),
            )
        assert error.value.code == "EXPLAIN_TOOL_NOT_EXECUTED" and not backend.enqueues

    asyncio.run(run())


@pytest.mark.parametrize(
    "message,expected",
    [
        ("重新识别一下", True),
        ("这四个起点识别错了重新识别一下", True),
        ("按放线端重新提取终点", True),
        ("请重扫本页", True),
        ("可以帮我重新识别吗", True),
        ("请解释重新识别的流程", False),
        ("为什么没有重新识别成功", False),
        ("是否已经重扫", False),
        ("需要手动重扫吗", False),
        ("不要重新识别，只解释来源", False),
        ("先别重扫", False),
        ("无需再次提取", False),
        ("上轮重扫失败", False),
        ("解释‘重新识别’的意思", False),
        ("如何重新扫描", False),
        ("重新提取怎么做", False),
        ("重扫失败了", False),
        ("不需要重新识别", False),
        ("取消重扫", False),
        ("请勿重新提取", False),
    ],
)
def test_rescan_commands_do_not_include_status_explanations_or_negations(message, expected):
    assert requests_rescan(message) is expected


def test_cached_progress_prose_is_not_replayed_as_completion():
    async def run():
        backend = RescanBackend()
        assistant, gateway = agent(
            backend, ["这是已保存的连接来源。", "未启动任何后台任务，已保存的来源如下。"]
        )
        turn = ExplainTurn(project_id=PROJECT, connection_id=ROW, message="解释来源", allow_rescan=False)
        actor = ExplainActor(user_id=OWNER)
        await assistant.ask(turn, actor)
        session = assistant._sessions[(str(OWNER), str(turn.conversation_id))]
        cached = list(session.responses[str(turn.turn_id)])
        cached[1] = "[turn 4 tool call]正在读取图纸页…"
        session.responses[str(turn.turn_id)] = tuple(cached)
        result = await assistant.ask(turn, actor)
        assert not result.cached and "正在读取" not in result.answer
        assert len(gateway.calls) == 2 and not backend.enqueues

    asyncio.run(run())


def test_action_search_keeps_exact_identity_and_pagination_without_raw_history():
    async def run():
        backend = RescanBackend()
        backend.row["evidence"]["record"]["source_note"] = "旧的重复证据" * 20000
        assistant, gateway = agent(
            backend,
            [
                tool("search_connections", {"connection_id": str(ROW)}),
                tool("rescan_connections", REQUEST),
                "已创建。",
            ],
        )
        result = await assistant.ask(
            ExplainTurn(project_id=PROJECT, connection_id=ROW, message="重新识别终点"),
            ExplainActor(user_id=OWNER),
        )
        messages = json.dumps(gateway.calls[1].messages, ensure_ascii=False)
        assert str(ROW) in messages and "has_more" in messages and len(messages) < 35000
        assert "旧的重复证据" not in messages and len(result.rescans) == 1
        assert backend.row["evidence"]["record"]["source_note"].startswith("旧的重复证据")

    asyncio.run(run())


def test_unbacked_queue_claim_is_retracted_repaired_and_cached_without_duplicate_enqueue():
    async def run():
        backend = RescanBackend()
        original = deepcopy(backend.row)
        assistant, gateway = agent(
            backend, [CLAIM, tool("rescan_connections", REQUEST), "已完成提取，终点是U。"]
        )
        turn = ExplainTurn(project_id=PROJECT, connection_id=ROW, message="沿线重新提取终点")
        events = []

        async def emit(event):
            events.append(event)

        result = await assistant.ask(turn, ExplainActor(user_id=OWNER), on_event=emit)
        assert len(backend.enqueues) == 1
        assert result.rescans[0].status == "queued"
        assert str(result.rescans[0].id) in result.answer and "queued" in result.answer
        assert "终点是U" not in result.answer and "正式线表未改动" in result.answer
        assert any(event.type == "answer_reset" for event in events)
        assert any(event.type == "rescan_started" for event in events)
        assert gateway.calls[1].metadata["operation"] == "repair_unbacked_rescan"
        assert gateway.calls[1].tool_choice == "required"
        assert all("evidence_path" not in str(m.get("content", "")) for m in gateway.calls[1].messages)
        assert backend.row == original
        retry = await assistant.ask(turn, ExplainActor(user_id=OWNER))
        assert retry.cached and len(backend.enqueues) == 1 and len(gateway.calls) == 3

    asyncio.run(run())


@pytest.mark.parametrize("allowed", [True, False])
def test_unbacked_queue_claim_cannot_finish_without_receipt(allowed):
    async def run():
        backend = RescanBackend()
        assistant, gateway = agent(backend, [CLAIM, CLAIM])
        with pytest.raises(ExplainError) as error:
            await assistant.ask(
                ExplainTurn(project_id=PROJECT, connection_id=ROW, message="重新提取", allow_rescan=allowed),
                ExplainActor(user_id=OWNER),
            )
        assert error.value.code == ("RESCAN_NOT_CREATED" if allowed else "RESCAN_NOT_REQUESTED")
        assert len(gateway.calls) == (2 if allowed else 1)
        assert not backend.enqueues and not backend.preparations

    asyncio.run(run())


def test_old_conversation_receipt_does_not_back_a_new_turn_claim():
    async def run():
        backend = RescanBackend()
        assistant, _ = agent(backend, [tool("rescan_connections", REQUEST), "已入队", CLAIM, CLAIM])
        turn = ExplainTurn(project_id=PROJECT, connection_id=ROW, message="重新提取终点")
        await assistant.ask(turn, ExplainActor(user_id=OWNER))
        with pytest.raises(ExplainError) as error:
            await assistant.ask(turn.model_copy(update={"turn_id": uuid4()}), ExplainActor(user_id=OWNER))
        assert error.value.code == "RESCAN_NOT_CREATED"
        assert len(backend.enqueues) == 1

    asyncio.run(run())


def test_rejected_enqueue_cannot_be_presented_as_queued():
    async def run():
        backend = RescanBackend()
        backend.reject = True
        assistant, _ = agent(backend, [CLAIM, tool("rescan_connections", REQUEST), CLAIM])
        with pytest.raises(ExplainError) as error:
            await assistant.ask(
                ExplainTurn(project_id=PROJECT, connection_id=ROW, message="重新提取终点"),
                ExplainActor(user_id=OWNER),
            )
        assert error.value.code == "RESCAN_NOT_CREATED"
        assert len(backend.enqueues) == 1 and not backend.runs

    asyncio.run(run())


def test_explicit_readonly_task_status_uses_persisted_receipt_without_creating_task():
    async def run():
        backend = RescanBackend()
        assistant, _ = agent(backend, [tool("rescan_connections", REQUEST), "已入队", CLAIM])
        turn = ExplainTurn(project_id=PROJECT, connection_id=ROW, message="重新提取终点")
        initial = await assistant.ask(turn, ExplainActor(user_id=OWNER))
        task = initial.rescans[0]
        status = await assistant.ask(
            ExplainTurn(
                project_id=PROJECT,
                connection_id=ROW,
                rescan_id=task.id,
                message="查询任务状态",
                allow_rescan=False,
            ),
            ExplainActor(user_id=OWNER),
        )
        assert str(task.id) in status.answer and "queued" in status.answer
        assert len(backend.enqueues) == 1

    asyncio.run(run())


def test_cached_unbacked_claim_is_not_replayed_as_success():
    async def run():
        backend = RescanBackend()
        assistant, gateway = agent(backend, ["没有执行重扫。", CLAIM, CLAIM])
        turn = ExplainTurn(project_id=PROJECT, connection_id=ROW)
        actor = ExplainActor(user_id=OWNER)
        await assistant.ask(turn, actor)
        session = assistant._sessions[(str(OWNER), str(turn.conversation_id))]
        cached = list(session.responses[str(turn.turn_id)])
        cached[1] = CLAIM
        session.responses[str(turn.turn_id)] = tuple(cached)
        with pytest.raises(ExplainError) as error:
            await assistant.ask(turn, actor)
        assert error.value.code == "RESCAN_NOT_CREATED"
        assert len(gateway.calls) == 3 and not backend.enqueues

    asyncio.run(run())


def test_repair_can_retrieve_then_requires_tool_until_receipt_exists():
    async def run():
        backend = RescanBackend()
        assistant, gateway = agent(
            backend,
            [
                CLAIM,
                tool("search_connections", {"connection_id": str(ROW)}),
                tool("rescan_connections", REQUEST),
                "已入队",
            ],
        )
        result = await assistant.ask(
            ExplainTurn(project_id=PROJECT, connection_id=ROW, message="重新提取终点"),
            ExplainActor(user_id=OWNER),
        )
        assert len(backend.enqueues) == 1 and len(result.rescans) == 1
        assert gateway.calls[1].tool_choice == "required" and gateway.calls[2].tool_choice == "required"
        assert gateway.calls[3].tool_choice is None

    asyncio.run(run())


def test_provider_ignoring_required_tools_after_retrieval_fails_without_enqueue():
    async def run():
        backend = RescanBackend()
        assistant, _ = agent(
            backend, [CLAIM, tool("search_connections", {"connection_id": str(ROW)}), "稍后处理"]
        )
        with pytest.raises(ExplainError, match="模型未返回重扫工具调用"):
            await assistant.ask(
                ExplainTurn(project_id=PROJECT, connection_id=ROW, message="重新提取终点"),
                ExplainActor(user_id=OWNER),
            )
        assert not backend.enqueues

    asyncio.run(run())


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (CLAIM, True),
        ("我已经重新提取了这五条终点", True),
        ("任务已提交，正式线表未改动", True),
        ("已开始重新识别终点", True),
        ("任务状态：`queued`", True),
        ("尚未创建重扫任务", False),
        ("不要说已创建重扫任务", False),
        ("历史回答“已提交重扫任务”不能证明本轮执行", False),
        ("用户要求重新提取，尚未执行", False),
        ("请提供需要重新识别的端子范围", False),
    ],
)
def test_rescan_claim_detection_excludes_negations_quotes_and_clarification(text, expected):
    from src.agent.explain_agent.rescan_receipts import claims_rescan_execution

    assert claims_rescan_execution(text) is expected
