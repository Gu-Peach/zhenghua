from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph

from ...agents.profile_router import ProfileRouterAgent
from ...domain.models.profile_detection import ProfileDetectionResult
from ...tools.pdf_first_page import PdfFirstPageRenderer
from .state import ProfileDetectionState


@dataclass(frozen=True, slots=True)
class ProfileDetectionRuntime:
    renderer: PdfFirstPageRenderer
    router: ProfileRouterAgent


def build_profile_detection_graph(runtime: ProfileDetectionRuntime) -> Any:
    async def render_first_page(state: ProfileDetectionState) -> dict[str, Any]:
        return {"first_page": await asyncio.to_thread(runtime.renderer.render, Path(state["pdf_path"]))}

    async def route_profile(state: ProfileDetectionState) -> dict[str, Any]:
        return {
            "result": await runtime.router.detect(
                first_page=state["first_page"],
                run_id=state["run_id"],
                project_id=state["project_id"],
            )
        }

    graph = StateGraph(ProfileDetectionState)
    graph.add_node("render_pdf_first_page", render_first_page)
    graph.add_node("profile_router", route_profile)
    graph.add_edge(START, "render_pdf_first_page")
    graph.add_edge("render_pdf_first_page", "profile_router")
    graph.add_edge("profile_router", END)
    return graph.compile()


async def run_profile_detection(
    *,
    runtime: ProfileDetectionRuntime,
    run_id: str,
    project_id: str,
    pdf_path: Path,
) -> ProfileDetectionResult:
    graph = build_profile_detection_graph(runtime)
    final_state = await graph.ainvoke(
        {
            "run_id": run_id,
            "project_id": project_id,
            "pdf_path": pdf_path,
        }
    )
    return ProfileDetectionResult.model_validate(final_state["result"])
