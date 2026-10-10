from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from ...agents.supervisor import SupervisorAgent
from ...application.workflow_registry import WorkflowDispatchReceipt, WorkflowRegistry
from ...domain.enums import SupervisorTurnStatus
from ...domain.models.supervisor import ConversationTurn, SupervisorDecision, SupervisorUserEvent


class SupervisorGraphState(TypedDict, total=False):
    turn: ConversationTurn
    context_summary: str
    decision: SupervisorDecision
    receipt: WorkflowDispatchReceipt
    user_event: SupervisorUserEvent


@dataclass(frozen=True, slots=True)
class SupervisorGraphResult:
    decision: SupervisorDecision
    receipt: WorkflowDispatchReceipt | None
    user_event: SupervisorUserEvent


def build_supervisor_graph(
    agent: SupervisorAgent,
    workflows: WorkflowRegistry,
    on_event: Callable[[SupervisorUserEvent], Awaitable[None]] | None = None,
) -> Any:
    async def decide(state: SupervisorGraphState) -> dict[str, Any]:
        decision = await agent.decide(
            state["turn"],
            context_summary=state.get("context_summary", ""),
        )
        if on_event:
            await on_event(
                SupervisorUserEvent(
                    conversation_id=decision.conversation_id,
                    turn_id=decision.turn_id,
                    event_type="SUPERVISOR_PLAN",
                    user_message=decision.reason,
                    payload={"intent": decision.intent.value},
                )
            )
        return {"decision": decision}

    def route(state: SupervisorGraphState) -> Literal["dispatch", "present"]:
        return "dispatch" if state["decision"].status == SupervisorTurnStatus.DISPATCHED else "present"

    async def dispatch(state: SupervisorGraphState) -> dict[str, Any]:
        command = state["decision"].command
        if command is None:
            raise ValueError("A dispatched Supervisor decision requires a command.")
        if on_event:
            await on_event(
                SupervisorUserEvent(
                    conversation_id=command.conversation_id,
                    turn_id=command.turn_id,
                    event_type="WORKFLOW_DISPATCHED",
                    user_message=(
                        "正在调用 ProfileDetection 读取首页、识别图纸类型。"
                        if command.action == "detect_profile"
                        else state["decision"].user_message
                    ),
                    payload={"workflow": command.workflow.value, "action": command.action},
                )
            )
        receipt = await workflows.dispatch(command)
        if receipt.status == "WAITING_INPUT":
            decision = state["decision"].model_copy(
                update={
                    "status": SupervisorTurnStatus.WAITING_INPUT,
                    "requires_input": True,
                    "user_message": receipt.message,
                    "command": None,
                    "agent_run_id": None,
                }
            )
        elif receipt.status == "COMPLETED" and (
            receipt.payload.get("profile_assignment") or receipt.payload.get("memory_context")
        ):
            decision = state["decision"].model_copy(
                update={
                    "status": SupervisorTurnStatus.ANSWERED,
                    "requires_input": False,
                    "user_message": receipt.message,
                    "command": None,
                }
            )
        else:
            decision = state["decision"].model_copy(update={"agent_run_id": receipt.agent_run_id})
        return {"receipt": receipt, "decision": decision}

    def present(state: SupervisorGraphState) -> dict[str, Any]:
        decision = state["decision"]
        receipt = state.get("receipt")
        suffix = (
            f" {receipt.message}"
            if receipt and receipt.message and receipt.message != decision.user_message
            else ""
        )
        event = SupervisorUserEvent(
            conversation_id=decision.conversation_id,
            turn_id=decision.turn_id,
            agent_run_id=receipt.agent_run_id if receipt else decision.agent_run_id,
            event_type=decision.status.value,
            user_message=f"{decision.user_message}{suffix}".strip(),
            requires_input=decision.requires_input,
            payload={
                "intent": decision.intent.value,
                "missing_fields": decision.missing_fields,
                **(receipt.payload if receipt else {}),
            },
        )
        return {"user_event": event}

    graph = StateGraph(SupervisorGraphState)
    graph.add_node("classify_intent", decide)
    graph.add_node("dispatch_workflow", dispatch)
    graph.add_node("present_result", present)
    graph.add_edge(START, "classify_intent")
    graph.add_conditional_edges(
        "classify_intent", route, {"dispatch": "dispatch_workflow", "present": "present_result"}
    )
    graph.add_edge("dispatch_workflow", "present_result")
    graph.add_edge("present_result", END)
    return graph.compile()


async def run_supervisor_graph(
    *,
    agent: SupervisorAgent,
    workflows: WorkflowRegistry,
    turn: ConversationTurn,
    context_summary: str = "",
    on_event: Callable[[SupervisorUserEvent], Awaitable[None]] | None = None,
) -> SupervisorGraphResult:
    state = await build_supervisor_graph(agent, workflows, on_event).ainvoke(
        {"turn": turn, "context_summary": context_summary}
    )
    return SupervisorGraphResult(
        decision=SupervisorDecision.model_validate(state["decision"]),
        receipt=(
            WorkflowDispatchReceipt.model_validate(state["receipt"])
            if state.get("receipt") is not None
            else None
        ),
        user_event=SupervisorUserEvent.model_validate(state["user_event"]),
    )
