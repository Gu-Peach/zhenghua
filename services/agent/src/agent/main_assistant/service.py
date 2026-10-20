from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid5

import httpx
from pydantic import ValidationError

from src.config import AgentSettings
from src.harness.model_gateway import ModelGateway, ModelRequest, ModelToolCall, OpenAICompatibleModelGateway
from src.harness.retry import RetryPolicy

from .completion import CompletionReview, RescanReceipt, completion_data, has_receipt, review_completion
from .models import AssistantEvent, AssistantInternalTurn, AssistantToolCall
from .progress import ReadProgress
from .tools import TOOL_MODELS, definitions

Sink = Callable[[AssistantEvent], Awaitable[None]]


class Executor(Protocol):
    async def execute(self, call: AssistantToolCall) -> dict[str, Any]: ...


class RemoteExecutor:
    def __init__(self, settings: AgentSettings, turn: UUID, token: str) -> None:
        self.settings, self.turn, self.token = settings, turn, token

    async def execute(self, call: AssistantToolCall) -> dict[str, Any]:
        headers = {"X-Assistant-Turn-Token": self.token}
        if self.settings.internal_token:
            headers["Authorization"] = "Bearer " + self.settings.internal_token
        async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=15)) as client:
            response = await client.post(
                f"{self.settings.server_base_url.rstrip('/')}/api/internal/assistant/turns/{self.turn}/tools",
                headers=headers,
                json=call.model_dump(mode="json"),
            )
            if response.is_error:
                try:
                    payload = response.json()
                    value = payload.get("detail", {}) if isinstance(payload, dict) else {}
                except ValueError:
                    value = {}
                value = value if isinstance(value, dict) else {}
                return {
                    "error": value.get("message", "业务工具执行失败"),
                    "code": value.get("code", "TOOL_FAILED"),
                }
            return dict(response.json())


class MainAssistant:
    def __init__(self, gateway: ModelGateway, max_tokens: int = 2500) -> None:
        self.gateway, self.max_tokens = gateway, max_tokens

    async def ask(self, turn: AssistantInternalTurn, executor: Executor, emit: Sink) -> None:
        prompt = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": prompt},
            *turn.history,
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "message": turn.message,
                        "scope": turn.scope.model_dump(mode="json"),
                        "attachments": turn.attachments,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        sequence = 0
        receipts: list[tuple[str, dict[str, Any]]] = []
        repair_used = False
        checked: CompletionReview | None = None
        required_tools: list[str] = []
        progress = ReadProgress()
        forced_calls: list[AssistantToolCall] = []
        delegated_answers: dict[str, str] = {}
        candidate_tools = {
            "start_rescan",
            "diagnose_profile",
            "propose_connection_edit",
            "start_document_extraction",
        }

        async def send(kind: Any, message: str | None = None, data: dict[str, Any] | None = None) -> None:
            nonlocal sequence
            sequence += 1
            await emit(
                AssistantEvent(
                    id=uuid5(turn.turn_id, f"event:{sequence}"),
                    turn_id=turn.turn_id,
                    type=kind,
                    message=message,
                    data=data or {},
                )
            )

        async def answer(text: str) -> None:
            for offset in range(0, len(text), 48):
                await send("answer_delta", text[offset : offset + 48])

        async def fail(message: str, code: str = "ASSISTANT_EXECUTION_UNVERIFIED") -> None:
            await send("error", message, {"code": code})
            await send("completed", data={"status": "failed"})

        def matched(name: str) -> dict[str, Any] | None:
            return next(
                (result for actual, result in reversed(receipts) if actual == name and has_receipt(result)),
                None,
            )

        def remaining() -> list[str]:
            return [name for name in required_tools if matched(name) is None]

        async def assess(candidate: str) -> None:
            nonlocal checked, required_tools
            if checked is None:
                checked = await review_completion(self.gateway, turn, candidate, receipts)
                required_tools = checked.tools()

        async def finish(text: str) -> None:
            primary = required_tools[0] if required_tools else None
            if delegated_answers:
                text = "\n\n".join(dict.fromkeys(delegated_answers.values()))
            await answer(text)
            await send(
                "completed",
                data=completion_data(
                    primary,
                    matched(primary) if primary else None,
                    required_tools=required_tools,
                    receipts=receipts,
                ),
            )

        for _ in range(8):
            if forced_calls:
                calls = tuple(
                    ModelToolCall(
                        f"handoff-{turn.turn_id}-{index}",
                        call.name,
                        json.dumps(call.arguments, ensure_ascii=False),
                    )
                    for index, call in enumerate(forced_calls)
                )
                forced_calls = []
                response_text = ""
            else:
                response = await self.gateway.invoke(
                    ModelRequest(
                        agent_name="main_assistant",
                        run_id=f"assistant:{turn.turn_id}",
                        messages=messages,
                        tools=[
                            tool for tool in definitions() if tool["function"]["name"] not in progress.blocked
                        ],
                        max_tokens=self.max_tokens,
                        metadata={"conversation_id": str(turn.conversation_id), "turn_id": str(turn.turn_id)},
                    )
                )
                if response.finish_reason == "length":
                    raise ValueError("主助手回答被截断，请缩小请求范围后重试")
                calls, response_text = response.tool_calls, response.content
            if not calls:
                text = response_text.strip() or "请说明需要查询的项目、工作区或图纸。"
                await assess(text)
                pending = remaining()
                if pending:
                    selection = next(
                        (
                            r
                            for _, r in reversed(receipts)
                            if has_receipt(r)
                            and (r.get("event") == "selection_required" or r.get("targets") == [])
                        ),
                        None,
                    )
                    if selection:
                        await answer(
                            "当前目标尚未唯一定位，请选择检索候选或补充项目/页码。本轮尚未启动重扫或修改数据。"
                        )
                        await send(
                            "completed", data=completion_data(pending[0], selection, clarification=True)
                        )
                        return
                    if not repair_used:
                        repair_used = True
                        messages.append(
                            {
                                "role": "system",
                                "content": (
                                    f"执行核验发现尚需完成{pending}，本轮缺少对应真实回执。上一份文字答复已丢弃。"
                                    "现在必须调用业务工具；需要定位目标时先find_targets，不猜ID。"
                                    "不能再次用口头状态或自造任务编号代替工具。工具失败如实报告，不绕过权限。"
                                ),
                            }
                        )
                        continue
                    state = "重扫未启动" if "start_rescan" in pending else f"尚缺{pending}的执行回执"
                    await fail(f"本轮未取得真实执行回执，{state}。请重新发送明确的项目和图纸范围。")
                    return
                if checked and checked.claims_execution and not required_tools:
                    await fail("本轮没有对应业务执行回执，不能确认任务已启动或数据已提交。")
                    return
                if any(word in text for word in ("已发布", "已修改线表", "已替换线表")) and not any(
                    result.get("status") == "applied" for _, result in receipts
                ):
                    text = "本轮没有正式提交回执。修改方案需要先查看差异，再点击确认按钮执行。"
                await finish(text)
                return
            messages.append(
                {
                    "role": "assistant",
                    "content": response_text or None,
                    "tool_calls": [call.as_message() for call in calls],
                }
            )
            for index, call in enumerate(calls):
                if checked is not None and call.name in candidate_tools and call.name not in required_tools:
                    # A batched model response may invent another task after the real goal returned.
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": json.dumps(
                                {
                                    "code": "ASSISTANT_OUTSIDE_CURRENT_GOAL",
                                    "error": "该操作不属于本轮已核验目标，未执行",
                                },
                                ensure_ascii=False,
                            ),
                        }
                    )
                    continue
                await send("tool_started", f"正在调用 {call.name}", {"name": call.name})
                try:
                    if index >= 6:
                        raise ValueError("单轮工具数超过限制")
                    if call.name not in TOOL_MODELS:
                        raise ValueError("工具未开放")
                    arguments = TOOL_MODELS[call.name].model_validate_json(call.arguments)
                    params = arguments.model_dump(mode="json")
                    result = progress.recall(call.name, params)
                    if result is None:
                        result = await executor.execute(AssistantToolCall(name=call.name, arguments=params))
                        progress.remember(call.name, params, result)
                except (ValueError, ValidationError):
                    result = {"error": "工具参数无效，请明确范围或对象", "code": "TOOL_INPUT_INVALID"}
                receipts.append((call.name, result))
                await send(
                    "tool_completed",
                    result.get("error") or f"{call.name} 已返回",
                    {
                        "name": call.name,
                        "action_id": result.get("action_id"),
                        "error": result.get("error"),
                        "sources": result.get("sources", []),
                        "repeat_guard": result.get("repeat_guard"),
                    },
                )
                if result.get("error") and result.get("code") not in {
                    "TOOL_INPUT_INVALID",
                    "ASSISTANT_TOOL_INPUT",
                }:
                    retained = (
                        " 本轮已返回的任务或候选仍保留，请在会话中查看；本轮尚未全部完成。"
                        if delegated_answers
                        else " 本轮未完成，请排查后重试。"
                    )
                    await fail(
                        f"{call.name} 执行失败：{result['error']}" + retained,
                        str(result.get("code") or "TOOL_FAILED"),
                    )
                    return
                event = result.get("event")
                if call.name == "start_rescan":
                    try:
                        receipt = RescanReceipt.model_validate(
                            {key: result[key] for key in RescanReceipt.model_fields}
                        )
                        delegated_answers[str(result["action_id"])] = receipt.answer()
                    except (KeyError, ValidationError):
                        await fail(
                            "重扫未启动或未取得有效任务回执。"
                            + str(result.get("error") or "请重试并检查工具状态。")
                        )
                        return
                if event in {"navigate", "selection_required", "task_started", "proposal_ready"}:
                    await send(event, data=result)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
                if result.get("delegated") and result.get("answer"):
                    if not has_receipt(result):
                        await fail("专业Agent未返回有效业务回执，请重试。")
                        return
                    delegated_answers[str(result["action_id"])] = str(result["answer"])
                if result.get("repeat_guard") or call.name == "start_rescan" or result.get("delegated"):
                    # Child diagnostic prose must not broaden the user's original goals.
                    await assess("")
                    if not required_tools and (call.name == "start_rescan" or result.get("delegated")):
                        required_tools = [call.name]
                if result.get("repeat_guard"):
                    pending = remaining()
                    forced_calls = progress.handoffs(
                        turn.message, pending, checked.propose_profile_changes if checked else False
                    )
                    messages.append(
                        {
                            "role": "system",
                            "content": (
                                f"相同检索已完成，禁止继续空转；尚需{pending}。"
                                "请调用后续专业Agent，或如实说明证据缺口。"
                            ),
                        }
                    )
                    if progress.repeats > 1 and not forced_calls and pending:
                        await fail(
                            f"相同检索没有新增证据，已停止重复调用。尚需{pending}；请补充正确端子值或明确修改范围。",
                            "ASSISTANT_NO_PROGRESS",
                        )
                        return
                elif checked is not None and remaining():
                    messages.append(
                        {
                            "role": "system",
                            "content": (
                                f"已完成的工具不能代替后续任务。用户尚需{remaining()}，"
                                "请继续调用；候选分别等待用户确认。"
                            ),
                        }
                    )
            if checked is not None and not remaining():
                primary = required_tools[0] if required_tools else None
                result = matched(primary) if primary else None
                await finish(
                    progress.summary(primary, result)
                    if primary and result
                    else "已完成请求的业务处理，请查看实际回执。"
                )
                return
        await fail("本轮已达到工具处理上限，未确认请求执行完成。已创建的候选可在会话中查看。")


def create_main_assistant(settings: AgentSettings, gateway: ModelGateway | None = None) -> MainAssistant:
    if gateway is None:
        if not settings.model_configured:
            raise ValueError("主助手模型尚未配置")
        gateway = OpenAICompatibleModelGateway(
            base_url=settings.model_base_url or settings.model_chat_completions_url or "",
            chat_completions_url=settings.model_chat_completions_url,
            default_model=settings.default_model or "",
            api_key=settings.model_api_key,
            timeout_seconds=settings.model_timeout_seconds,
            retry_policy=RetryPolicy(max_retries=settings.model_max_retries),
        )
    return MainAssistant(gateway, settings.model_max_tokens or 2500)
