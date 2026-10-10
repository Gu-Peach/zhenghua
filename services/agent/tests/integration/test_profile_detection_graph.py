from __future__ import annotations

import asyncio
import json
from pathlib import Path

from agent_service.agents.profile_router import ProfileRouterAgent
from agent_service.domain.enums import ProfileDetectionStatus
from agent_service.graphs.profile_detection import ProfileDetectionRuntime, run_profile_detection
from agent_service.harness import FakeModelGateway
from agent_service.profiles import ProfileRegistry
from agent_service.tools.pdf_first_page import PdfFirstPageRenderer
from tests.unit.test_pdf_first_page import FakeBackend, FakeDocument

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def test_profile_detection_graph_renders_then_routes(tmp_path: Path) -> None:
    async def run() -> None:
        profile_registry = ProfileRegistry(
            profile_root=REPOSITORY_ROOT / "services" / "agent" / "profiles",
            workspace_root=REPOSITORY_ROOT,
            allow_legacy_references=True,
        )
        profile_registry.load_all()
        output = json.dumps(
            {
                "recognized": True,
                "selected_profile_key": "zh",
                "confidence": 0.97,
                "candidates": [{"profile_key": "zh", "score": 0.97, "matched_signals": ["ZPMC"]}],
                "observed_signals": ["ZPMC"],
                "reason": "首页存在 ZPMC 标识",
            },
            ensure_ascii=False,
        )
        document = FakeDocument()
        runtime = ProfileDetectionRuntime(
            renderer=PdfFirstPageRenderer(dpi=144, backend=FakeBackend(document)),
            router=ProfileRouterAgent(
                gateway=FakeModelGateway([output]),
                registry=profile_registry,
                prompt_path=REPOSITORY_ROOT / "services" / "agent" / "prompts" / "profile_router.md",
            ),
        )
        pdf_path = tmp_path / "drawing.pdf"
        pdf_path.write_bytes(b"fake-pdf")
        result = await run_profile_detection(
            runtime=runtime,
            run_id="run-graph",
            project_id="project-graph",
            pdf_path=pdf_path,
        )
        assert document.loaded_pages == [0]
        assert result.status == ProfileDetectionStatus.PROFILE_SELECTED
        assert result.assigned_profile is not None
        assert result.assigned_profile.key == "zh"

    asyncio.run(run())
