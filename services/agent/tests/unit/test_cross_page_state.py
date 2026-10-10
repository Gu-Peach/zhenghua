from __future__ import annotations

import asyncio
from pathlib import Path

from agent_service.application.extraction_stage_dispatcher import ProfileBoundStageDispatcher
from agent_service.domain.enums import CorrectionIssueKind, CrossPageState, ScopeType
from agent_service.domain.models.correction import (
    CorrectionConstraints,
    CorrectionContext,
    CorrectionEvidenceBundle,
    CorrectionFacts,
    FeedbackTarget,
)
from agent_service.domain.models.extraction_stages import (
    CrossPageCompletionData,
    CrossPageCompletionRequest,
    DrawingEndpoint,
    DrawingPageInput,
    PageClassificationData,
    PageScanData,
    PageScanRequest,
    ScannedConnection,
    ScannedWireUnit,
)
from agent_service.infrastructure.zh_vlm_stages import _normalize_page_scan
from agent_service.profiles import ProfileRegistry
from agent_service.tools.correction_router import CorrectionRoutePlanner
from agent_service.tools.extraction_runner import ScopedExtractionRunner

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
            profile_root=ROOT / "services" / "agent" / "profiles",
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
