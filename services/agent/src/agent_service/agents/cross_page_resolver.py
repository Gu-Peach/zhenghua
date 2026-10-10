from __future__ import annotations

from ..domain.models.extraction_stages import (
    CrossPageCompletionData,
    CrossPageCompletionRequest,
    CrossPageCompletionResult,
)
from ..domain.ports import ExtractionStageAdapter
from ._extraction_stage import require_stage_resources


class CrossPageResolverAgent:
    """Stage 3: resolve one terminal connection against exactly one target page."""

    def __init__(self, *, stages: ExtractionStageAdapter) -> None:
        self._stages = stages

    async def run(self, request: CrossPageCompletionRequest) -> CrossPageCompletionResult:
        require_stage_resources(request.profile, "cross_page_completion")
        if request.target_page.blank:
            result = CrossPageCompletionData(
                task_id=request.task_id,
                needs_review=True,
                warnings=["indexed target page is blank or unavailable"],
            )
        else:
            result = await self._stages.resolve_cross_page(request)
        needs_review = (
            result.needs_review
            or result.end is None
            or result.end.terminal in (None, "")
            or result.status != "resolved"
        )
        status = "needs_review" if needs_review else result.status
        return CrossPageCompletionResult(
            run_id=request.run_id,
            project_id=request.project_id,
            profile=request.profile.profile,
            task_id=request.task_id,
            end=result.end,
            intermediate_points=result.intermediate_points,
            current=result.current,
            current_basis=result.current_basis,
            current_source_text=result.current_source_text,
            status=status,
            needs_review=needs_review,
            confidence=result.confidence,
            source_note=result.source_note,
            warnings=result.warnings,
        )
