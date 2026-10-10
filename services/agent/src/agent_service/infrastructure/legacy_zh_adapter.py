from __future__ import annotations

from collections.abc import Callable

from ..config import AgentSettings
from ..domain.models.extraction import ExtractionExecutionResult, LegacyExtractionRequest
from ..domain.models.profiles import ProfileBinding

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
        from ..application.three_stage_extraction import run_three_stage_extraction

        result = await run_three_stage_extraction(
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
