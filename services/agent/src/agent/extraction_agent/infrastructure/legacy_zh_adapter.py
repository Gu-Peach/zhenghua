from __future__ import annotations

from collections.abc import Callable

from src.config import AgentSettings
from src.agent.extraction_agent.domain.models.extraction import (
    ExtractionExecutionResult,
    LegacyExtractionRequest,
)
from src.domain.models.profiles import ProfileBinding

ProgressCallback = Callable[[str], None]


class LegacyZhExtractionAdapter:
    """Compatibility entry point that now delegates to the standalone agent workflow."""

    def __init__(self, settings: AgentSettings) -> None:
        self._settings = settings

    async def run_full(
        self,
        request: LegacyExtractionRequest,
        *,
        progress: ProgressCallback | None = None,
    ) -> ExtractionExecutionResult:
        self._validate_profile(request.profile)
        from src.agent.extraction_agent.application.page_workflow_extraction import (
            run_page_workflow_extraction,
        )

        result = await run_page_workflow_extraction(
            pdf_path=request.pdf_path,
            output_dir=request.output_path,
            profile=request.profile,
            settings=self._settings,
            run_id=request.run_id,
            project_id=request.project_id,
            max_pdf_pages=request.max_pdf_pages,
            progress=progress,
        )
        return result.execution

    @staticmethod
    def _validate_profile(profile: ProfileBinding) -> None:
        if profile.profile.key != "zh" or profile.adapter != "zh_native":
            raise ValueError("The migrated ZH workflow requires the zh_native profile adapter.")
