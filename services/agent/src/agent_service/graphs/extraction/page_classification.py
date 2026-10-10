from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from ...agents.page_classifier import PageClassifierAgent
from ...domain.models.extraction_stages import PageClassificationRequest, PageClassificationResult


class PageClassificationState(TypedDict, total=False):
    request: PageClassificationRequest
    result: PageClassificationResult


def build_page_classification_graph(agent: PageClassifierAgent) -> Any:
    async def classify(state: PageClassificationState) -> dict[str, Any]:
        return {"result": await agent.run(state["request"])}

    graph = StateGraph(PageClassificationState)
    graph.add_node("page_classifier", classify)
    graph.add_edge(START, "page_classifier")
    graph.add_edge("page_classifier", END)
    return graph.compile()


async def run_page_classification(
    *,
    agent: PageClassifierAgent,
    request: PageClassificationRequest,
) -> PageClassificationResult:
    final_state = await build_page_classification_graph(agent).ainvoke({"request": request})
    return PageClassificationResult.model_validate(final_state["result"])
