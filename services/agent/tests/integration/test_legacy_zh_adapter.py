from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agent_service.config import AgentSettings
from agent_service.domain.models.extraction import ExtractionExecutionResult, LegacyExtractionRequest
from agent_service.infrastructure.legacy_zh_adapter import LegacyZhExtractionAdapter
from agent_service.profiles import ProfileRegistry

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PROFILE_ROOT = REPOSITORY_ROOT / "services" / "agent" / "profiles"


def test_compatibility_adapter_delegates_to_native_agent_workflow(tmp_path: Path) -> None:
    async def run() -> None:
        registry = ProfileRegistry(
            profile_root=PROFILE_ROOT,
            workspace_root=REPOSITORY_ROOT,
            allow_legacy_references=True,
        )
        registry.load_all()
        profile = registry.bind("zh")
        request = LegacyExtractionRequest(
            run_id="run-1",
            project_id="project-1",
            pdf_path=tmp_path / "input.pdf",
            output_path=tmp_path / "output",
            profile=profile,
            max_pdf_pages=5,
        )
        execution = ExtractionExecutionResult(
            run_id="run-1",
            state={"table_headers": ["页码"]},
            adapter="langgraph_three_stage",
        )
        adapter = LegacyZhExtractionAdapter(AgentSettings())
        with patch(
            "agent_service.application.three_stage_extraction.run_three_stage_extraction",
            new=AsyncMock(return_value=SimpleNamespace(execution=execution)),
        ) as workflow:
            result = await adapter.run_full(request)

        assert result.adapter == "langgraph_three_stage"
        assert result.state == {"table_headers": ["页码"]}
        workflow.assert_awaited_once()
        assert workflow.await_args.kwargs["profile"] == profile
        assert workflow.await_args.kwargs["max_pdf_pages"] == 5

    asyncio.run(run())
