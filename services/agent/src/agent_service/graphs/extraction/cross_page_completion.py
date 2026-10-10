from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from ...agents.cross_page_resolver import CrossPageResolverAgent
from ...domain.models.extraction_stages import (
    CrossPageCompletionRequest,
    CrossPageCompletionResult,
)


class CrossPageCompletionState(TypedDict, total=False):
    request: CrossPageCompletionRequest
    result: CrossPageCompletionResult


def build_cross_page_completion_graph(agent: CrossPageResolverAgent) -> Any:
    async def resolve(state: CrossPageCompletionState) -> dict[str, Any]:
        return {"result": await agent.run(state["request"])}

    graph = StateGraph(CrossPageCompletionState)
    graph.add_node("cross_page_resolver", resolve)
    graph.add_edge(START, "cross_page_resolver")
    graph.add_edge("cross_page_resolver", END)
    return graph.compile()


async def run_cross_page_completion(
    *,
    agent: CrossPageResolverAgent,
    request: CrossPageCompletionRequest,
) -> CrossPageCompletionResult:
    final_state = await build_cross_page_completion_graph(agent).ainvoke({"request": request})
    return CrossPageCompletionResult.model_validate(final_state["result"])
