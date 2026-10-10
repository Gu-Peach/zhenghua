from __future__ import annotations

import asyncio
from pathlib import Path

from agent_service.application.extraction_dispatcher import ProfileBoundExtractionDispatcher
from agent_service.domain.models.extraction import ExtractionExecutionResult, LegacyExtractionRequest
from agent_service.profiles import ProfileRegistry

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


class FakeExtractionAdapter:
    def __init__(self) -> None:
        self.calls: list[LegacyExtractionRequest] = []

    async def run_full(self, request: LegacyExtractionRequest) -> ExtractionExecutionResult:
        self.calls.append(request)
        return ExtractionExecutionResult(
            run_id=request.run_id,
            state={"profile": request.profile.profile.key},
            adapter=request.profile.adapter,
        )


def test_dispatcher_uses_adapter_from_profile_binding(tmp_path: Path) -> None:
    async def run() -> None:
        registry = ProfileRegistry(
            profile_root=REPOSITORY_ROOT / "services" / "agent" / "profiles",
            workspace_root=REPOSITORY_ROOT,
            allow_legacy_references=True,
        )
        registry.load_all()
        binding = registry.bind("zh")
        request = LegacyExtractionRequest(
            run_id="run-1",
            project_id="project-1",
            pdf_path=tmp_path / "drawing.pdf",
            output_path=tmp_path / "output",
            profile=binding,
        )
        adapter = FakeExtractionAdapter()
        dispatcher = ProfileBoundExtractionDispatcher()
        dispatcher.register("zh_native", adapter)

        result = await dispatcher.run_full(request)

        assert result.state == {"profile": "zh"}
        assert adapter.calls == [request]

    asyncio.run(run())
