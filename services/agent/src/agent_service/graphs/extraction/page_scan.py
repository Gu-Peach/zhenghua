from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from ...agents.page_scanner import PageScannerAgent
from ...domain.models.extraction_stages import PageScanRequest, PageScanResult


class PageScanState(TypedDict, total=False):
    request: PageScanRequest
    result: PageScanResult


def build_page_scan_graph(agent: PageScannerAgent) -> Any:
    async def scan(state: PageScanState) -> dict[str, Any]:
        return {"result": await agent.run(state["request"])}

    graph = StateGraph(PageScanState)
    graph.add_node("page_scanner", scan)
    graph.add_edge(START, "page_scanner")
    graph.add_edge("page_scanner", END)
    return graph.compile()


async def run_page_scan(*, agent: PageScannerAgent, request: PageScanRequest) -> PageScanResult:
    final_state = await build_page_scan_graph(agent).ainvoke({"request": request})
    return PageScanResult.model_validate(final_state["result"])
