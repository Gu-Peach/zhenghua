from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from src.agent.extraction_agent.application.extraction_stage_dispatcher import ProfileBoundStageDispatcher
from src.domain.enums import CorrectionIssueKind, CrossPageState, ScopeType
from src.domain.models.correction import (
    CorrectionConstraints,
    CorrectionContext,
    CorrectionEvidenceBundle,
    CorrectionFacts,
    FeedbackTarget,
)
from src.agent.extraction_agent.domain.models.extraction_stages import (
    CrossPageCompletionData,
    CrossPageCompletionRequest,
    DrawingEndpoint,
    DrawingPageInput,
    DrawingReference,
    PageClassificationData,
    PageScanData,
    PageScanRequest,
    ScannedConnection,
    ScannedWireUnit,
)
from src.agent.extraction_agent.infrastructure.zh_vlm_stages import _normalize_page_scan
from src.profiles import ProfileRegistry
from src.tools.correction_router import CorrectionRoutePlanner
from src.agent.extraction_agent.tools.extraction_runner import ScopedExtractionRunner

ROOT = Path(__file__).resolve().parents[4]


def test_page_scan_normalizes_cross_page_state_from_visible_evidence() -> None:
    cross_page = _normalize_page_scan(
        {
            "units": [
                {
                    "unit_id": "unit-1",
                    "connections": [
                        {
                            "connection_id": "connection-1",
                            "references": [{"raw": "=.C/1.3"}],
                        }
                    ],
                }
            ]
        },
        1,
    )
    same_page = _normalize_page_scan(
        {
            "units": [
                {
                    "unit_id": "unit-1",
                    "connections": [
                        {
                            "connection_id": "connection-1",
                            "end": {"terminal": "X21:1"},
                        }
                    ],
                }
            ]
        },
        1,
    )
    unknown = _normalize_page_scan(
        {
            "units": [
                {
                    "unit_id": "unit-1",
                    "connections": [{"connection_id": "connection-1"}],
                }
            ]
        },
        1,
    )
    assert cross_page["units"][0]["connections"][0]["is_cross_page"] == "cross_page"
    assert same_page["units"][0]["connections"][0]["is_cross_page"] == "same_page"
    assert unknown["units"][0]["connections"][0]["is_cross_page"] == "unknown"


def test_page_scan_normalizes_numeric_source_drawing_pages() -> None:
    result = _normalize_page_scan(
        {
            "units": [
                {
                    "unit_id": "u1",
                    "source_drawing_pages": [432],
                    "connections": [
                        {
                            "line_number": "1015",
                            "source_drawing_pages": [205, 432],
                            "start": {"terminal": "X1:1"},
                            "end": {"terminal": "X2:1"},
                        }
                    ],
                }
            ]
        },
        1,
    )
    assert result["units"][0]["source_drawing_pages"] == ["432"]
    assert result["units"][0]["connections"][0]["source_drawing_pages"] == ["205", "432"]
    PageScanData.model_validate(result)


class Stage2ChangesToSamePage:
    def __init__(self) -> None:
        self.stage3_calls = 0

    async def classify_page(self, request):  # type: ignore[no-untyped-def]
        return PageClassificationData()

    async def scan_page(self, request):  # type: ignore[no-untyped-def]
        return PageScanData(
            pdf_page_number=request.page.pdf_page_number,
            units=[
                ScannedWireUnit(
                    unit_id="unit-1",
                    connections=[
                        ScannedConnection(
                            connection_id="connection-1",
                            start=DrawingEndpoint(terminal="XD21:7"),
                            end=DrawingEndpoint(terminal="X21:2"),
                            is_cross_page=CrossPageState.SAME_PAGE,
                        )
                    ],
                )
            ],
        )

    async def resolve_cross_page(self, request):  # type: ignore[no-untyped-def]
        self.stage3_calls += 1
        return CrossPageCompletionData(
            task_id=request.task_id,
            end=DrawingEndpoint(terminal="X21:3"),
        )


def test_unknown_route_skips_stage3_when_stage2_confirms_same_page() -> None:
    async def run() -> None:
        registry = ProfileRegistry(
            profile_root=ROOT / "services" / "agent" / "src/agent/extraction_agent/profiles",
            workspace_root=ROOT,
            allow_legacy_references=True,
        )
        registry.load_all()
        binding = registry.bind("zh")
        stages = Stage2ChangesToSamePage()
        dispatcher = ProfileBoundStageDispatcher()
        dispatcher.register(binding.adapter, stages)
        page = DrawingPageInput(pdf_page_number=1, image_path=Path("source.png"))
        target = DrawingPageInput(pdf_page_number=2, image_path=Path("target.png"))
        bundle = CorrectionEvidenceBundle(
            facts=CorrectionFacts(
                feedback_id="feedback-1",
                target=FeedbackTarget(
                    type=ScopeType.CONNECTION,
                    id="connection-1",
                    project_id="project-1",
                    result_version_id="project-1:v1",
                ),
                issue_kind=CorrectionIssueKind.RECOGNITION_ERROR,
                is_cross_page=CrossPageState.UNKNOWN,
            ),
            context=CorrectionContext(
                feedback_id="feedback-1",
                observed_problem="需要重新判断是否跨页",
                constraints=CorrectionConstraints(
                    allowed_connection_ids=["connection-1"],
                ),
            ),
            profile=binding,
            base_result_version=1,
            current_records=[
                {
                    "connection_id": "connection-1",
                    "is_cross_page": "unknown",
                }
            ],
            evidence_ids=["evidence-1"],
            page_scan_requests=[
                PageScanRequest(
                    run_id="run-1",
                    project_id="project-1",
                    profile=binding,
                    page=page,
                )
            ],
            cross_page_requests=[
                CrossPageCompletionRequest(
                    run_id="run-1",
                    project_id="project-1",
                    profile=binding,
                    task_id="task-1",
                    target_page=target,
                    task_context="复核连接 connection-1",
                )
            ],
            cross_page_task_targets={"task-1": "connection-1"},
        )
        plan = CorrectionRoutePlanner().plan(bundle.facts)
        records = await ScopedExtractionRunner(dispatcher).run(plan, bundle)
        assert records[0]["is_cross_page"] == "same_page"
        assert stages.stage3_calls == 0

    asyncio.run(run())


class ScopedCrossPageStages(Stage2ChangesToSamePage):
    async def scan_page(self, request: Any) -> PageScanData:
        return PageScanData(
            units=[
                ScannedWireUnit(
                    unit_id="local-unit",
                    connections=[
                        ScannedConnection(
                            local_connection_id="local-source",
                            start=DrawingEndpoint(device="-XD3", location="+01F11.3", terminal="XD3:113"),
                            is_cross_page=CrossPageState.CROSS_PAGE,
                            references=[DrawingReference(target_function="006.C", target_drawing_page=1)],
                        )
                    ],
                )
            ]
        )

    async def resolve_cross_page(self, request: Any) -> CrossPageCompletionData:
        self.stage3_calls += 1
        assert request.target_page.pdf_page_number == 4
        assert '"connection_id": "connection-1"' in request.task_context
        return CrossPageCompletionData(
            task_id=request.task_id,
            end=DrawingEndpoint(terminal="X3:1"),
            status="complete",
        )


def test_scoped_cross_page_matches_fresh_source_and_reaches_stage3() -> None:
    async def run() -> None:
        registry = ProfileRegistry(
            profile_root=ROOT / "services/agent/src/agent/extraction_agent/profiles", workspace_root=ROOT, allow_legacy_references=True
        )
        registry.load_all()
        binding = registry.bind("zh")
        stages = ScopedCrossPageStages()
        dispatcher = ProfileBoundStageDispatcher()
        dispatcher.register(binding.adapter, stages)
        original = {
            "connection_id": "connection-1",
            "start_code": "+01F11.3",
            "start_device": "-XD3",
            "start_location": "+01F11.3",
            "start_terminal": "XD3:113",
            "start": {"device": "+01F11.3", "terminal": "XD3:113"},
            "end_terminal": "999",
            "is_cross_page": "cross_page",
        }
        bundle = CorrectionEvidenceBundle(
            facts=CorrectionFacts(
                feedback_id="feedback-1",
                issue_kind=CorrectionIssueKind.RECOGNITION_ERROR,
                is_cross_page=CrossPageState.CROSS_PAGE,
                target=FeedbackTarget(
                    type=ScopeType.CONNECTION,
                    id="connection-1",
                    project_id="project",
                    result_version_id="version",
                ),
            ),
            context=CorrectionContext(
                feedback_id="feedback-1",
                observed_problem="重新识别跨页终点",
                constraints=CorrectionConstraints(
                    allowed_connection_ids=["connection-1"], allowed_fields=["end_terminal"]
                ),
            ),
            profile=binding,
            base_result_version=1,
            current_records=[original],
            evidence_ids=["evidence"],
            page_scan_requests=[
                PageScanRequest(
                    run_id="run",
                    project_id="project",
                    profile=binding,
                    page=DrawingPageInput(pdf_page_number=3, image_path=Path("source.png")),
                )
            ],
            available_pages=[
                DrawingPageInput(
                    pdf_page_number=4,
                    image_path=Path("target.png"),
                    plant_function="006.C",
                    drawing_page_number=1,
                )
            ],
        )
        records = await ScopedExtractionRunner(dispatcher).run(
            CorrectionRoutePlanner().plan(bundle.facts), bundle
        )
        assert stages.stage3_calls == 1
        assert records[0]["connection_id"] == "connection-1"
        assert records[0]["end_terminal"] == "X3:1"
        assert records[0]["start"] == original["start"]
        assert original["end_terminal"] == "999"

    asyncio.run(run())
