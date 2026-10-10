from __future__ import annotations

import pytest

from agent_service.domain.enums import (
    AgentStage,
    CorrectionAction,
    CorrectionIssueKind,
    CrossPageState,
    ScopeType,
)
from agent_service.domain.models.correction import CorrectionFacts, FeedbackTarget
from agent_service.tools.correction_router import CorrectionRoutePlanner


def facts(
    issue_kind: CorrectionIssueKind,
    *,
    cross_page: bool = False,
) -> CorrectionFacts:
    return CorrectionFacts(
        feedback_id="feedback-1",
        target=FeedbackTarget(
            type=ScopeType.CONNECTION,
            id="connection-1",
            field="end_terminal",
            project_id="project-1",
            result_version_id="result-version-1",
        ),
        issue_kind=issue_kind,
        is_cross_page=(CrossPageState.CROSS_PAGE if cross_page else CrossPageState.SAME_PAGE),
        affected_drawing_ids=["drawing-source"],
        target_drawing_ids=["drawing-target"] if cross_page else [],
    )


@pytest.mark.parametrize(
    ("issue_kind", "cross_page", "expected_action", "expected_calls"),
    [
        (CorrectionIssueKind.DIRECT_VALUE_CHANGE, False, CorrectionAction.DIRECT_PATCH, 0),
        (CorrectionIssueKind.FORMAT_OR_ORDER, False, CorrectionAction.DETERMINISTIC_ONLY, 0),
        (CorrectionIssueKind.RECOGNITION_ERROR, False, CorrectionAction.RERUN_STAGE_2, 1),
        (CorrectionIssueKind.RECOGNITION_ERROR, True, CorrectionAction.RERUN_STAGE_2_AND_3, 2),
        (CorrectionIssueKind.SOURCE_INSUFFICIENT, False, CorrectionAction.NO_ACTION, 0),
    ],
)
def test_correction_route_matrix(
    issue_kind: CorrectionIssueKind,
    cross_page: bool,
    expected_action: CorrectionAction,
    expected_calls: int,
) -> None:
    plan = CorrectionRoutePlanner().plan(facts(issue_kind, cross_page=cross_page))
    assert plan.action == expected_action
    assert plan.estimated_model_calls == expected_calls


def test_cross_page_route_reviews_reference_before_stage_3() -> None:
    plan = CorrectionRoutePlanner().plan(facts(CorrectionIssueKind.RECOGNITION_ERROR, cross_page=True))
    assert plan.stages[:3] == [
        AgentStage.PAGE_SCAN,
        AgentStage.BUILD_CROSS_PAGE_TASKS,
        AgentStage.CROSS_PAGE_COMPLETION,
    ]


def test_unknown_cross_page_state_starts_with_stage_2_and_keeps_stage_3_conditional() -> None:
    value = facts(CorrectionIssueKind.RECOGNITION_ERROR)
    value.is_cross_page = CrossPageState.UNKNOWN
    plan = CorrectionRoutePlanner().plan(value)
    assert plan.action == CorrectionAction.RERUN_STAGE_2_AND_3
    assert plan.stages[:3] == [
        AgentStage.PAGE_SCAN,
        AgentStage.BUILD_CROSS_PAGE_TASKS,
        AgentStage.CROSS_PAGE_COMPLETION,
    ]
