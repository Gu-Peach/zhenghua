from __future__ import annotations

from ..domain.models.extraction_stages import (
    PageScanData,
    PageScanRequest,
    PageScanResult,
)
from ..domain.ports import ExtractionStageAdapter
from ._extraction_stage import require_stage_resources


class PageScannerAgent:
    """Stage 2: scan one source page; target-page images are not accepted here."""

    def __init__(self, *, stages: ExtractionStageAdapter) -> None:
        self._stages = stages

    async def run(self, request: PageScanRequest) -> PageScanResult:
        require_stage_resources(request.profile, "page_scan")
        page = request.page
        if page.blank or page.non_wiring:
            result = PageScanData(
                pdf_page_number=page.pdf_page_number,
                drawing_function=page.plant_function,
                drawing_page_number=page.drawing_page_number,
                drawing_object_location=page.object_location,
                blank=page.blank,
            )
        else:
            result = await self._stages.scan_page(request)
        return PageScanResult(
            run_id=request.run_id,
            project_id=request.project_id,
            profile=request.profile.profile,
            pdf_page_number=page.pdf_page_number,
            drawing_function=page.plant_function or result.drawing_function,
            drawing_page_number=page.drawing_page_number or result.drawing_page_number,
            drawing_object_location=page.object_location or result.drawing_object_location,
            blank=result.blank,
            needs_review=result.needs_review,
            units=[] if result.blank else result.units,
            page_references=result.page_references,
            warnings=result.warnings,
        )
