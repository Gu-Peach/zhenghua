from __future__ import annotations

from src.domain.enums import ErrorCode
from src.domain.errors import AgentServiceError
from src.agent.extraction_agent.domain.models.extraction_stages import (
    CrossPageCompletionRequest,
    CrossPageCompletionResult,
    PageScanData,
    PageScanRequest,
    PageScanResult,
)
from src.domain.ports import ExtractionStageAdapter
from src.agent.extraction_agent.agents._extraction_stage import require_stage_resources


class PageScannerAgent:
    """Stage 2 model operations used by the page extraction workflow."""

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
        for unit in result.units:
            unit.connections = [item for item in unit.connections if item.endpoint_role != "receiver"]
            for item in unit.connections:
                if item.endpoint_role == "unknown":
                    item.status = "needs_review"
                    result.needs_review = True
        result.units = [unit for unit in result.units if unit.connections]
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

    async def complete(self, request: CrossPageCompletionRequest) -> CrossPageCompletionResult:
        """Complete only the frozen connection, using its source and target images."""
        resources = request.profile.rules.extraction.dynamic_resources
        try:
            require_stage_resources(
                request.profile,
                "page_completion" if "page_completion" in resources else "cross_page_completion",
            )
        except ValueError as exc:
            raise AgentServiceError(
                ErrorCode.PROFILE_INVALID, "Stage 2 completion resources are invalid."
            ) from exc
        if request.target_page.blank or request.target_page.non_wiring:
            from src.agent.extraction_agent.domain.models.extraction_stages import CrossPageCompletionData

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
        return CrossPageCompletionResult(
            run_id=request.run_id,
            project_id=request.project_id,
            profile=request.profile.profile,
            **{
                **result.model_dump(mode="python"),
                "task_id": request.task_id,
                "needs_review": needs_review,
                "status": "needs_review" if needs_review else "resolved",
            },
        )
