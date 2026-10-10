from __future__ import annotations

from ..domain.models.extraction_stages import (
    PageClassificationData,
    PageClassificationRequest,
    PageClassificationResult,
)
from ..domain.ports import ExtractionStageAdapter
from ._extraction_stage import require_stage_resources


class PageClassifierAgent:
    """Stage 1: read drawing identity from exactly one rendered page."""

    def __init__(self, *, stages: ExtractionStageAdapter) -> None:
        self._stages = stages

    async def run(self, request: PageClassificationRequest) -> PageClassificationResult:
        require_stage_resources(request.profile, "page_classification")
        page = request.page
        if page.blank:
            result = PageClassificationData(
                plant_function=page.plant_function,
                drawing_page_number=page.drawing_page_number,
                blank=True,
                confidence=1.0,
                reason="blank page provided by renderer",
            )
        else:
            result = await self._stages.classify_page(request)
        return PageClassificationResult(
            run_id=request.run_id,
            project_id=request.project_id,
            profile=request.profile.profile,
            pdf_page_number=page.pdf_page_number,
            plant_function=result.plant_function,
            drawing_page_number=result.drawing_page_number,
            blank=result.blank,
            non_wiring=result.non_wiring,
            confidence=result.confidence,
            needs_review=result.needs_review,
            reason=result.reason,
        )
