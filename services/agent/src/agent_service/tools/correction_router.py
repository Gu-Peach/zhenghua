from __future__ import annotations

from ..domain.enums import AgentStage, CorrectionAction, CorrectionIssueKind, CrossPageState
from ..domain.models.correction import CorrectionFacts, CorrectionPlan


class CorrectionRoutePlanner:
    """Select the minimum correction path from persisted facts; no LLM is used."""

    def plan(self, facts: CorrectionFacts) -> CorrectionPlan:
        if facts.issue_kind == CorrectionIssueKind.SOURCE_INSUFFICIENT:
            return self._plan(facts, CorrectionAction.NO_ACTION, [], 0, "图纸证据不足，不重试猜测。")
        if facts.issue_kind == CorrectionIssueKind.DIRECT_VALUE_CHANGE:
            return self._plan(
                facts,
                CorrectionAction.DIRECT_PATCH,
                [AgentStage.VALIDATION, AgentStage.PROPOSAL],
                0,
                "用户明确给出修订值，生成候选 patch 并校验证据。",
            )
        if facts.issue_kind == CorrectionIssueKind.FORMAT_OR_ORDER:
            return self._plan(
                facts,
                CorrectionAction.DETERMINISTIC_ONLY,
                [AgentStage.VALIDATION, AgentStage.PROPOSAL],
                0,
                "格式、排序或去重问题只运行确定性节点。",
            )
        if facts.issue_kind == CorrectionIssueKind.PAGE_CLASSIFICATION_ERROR:
            stages = [AgentStage.PAGE_CLASSIFICATION, AgentStage.PAGE_SCAN]
            if facts.is_cross_page != CrossPageState.SAME_PAGE:
                stages.extend([AgentStage.BUILD_CROSS_PAGE_TASKS, AgentStage.CROSS_PAGE_COMPLETION])
            stages.extend([AgentStage.VALIDATION, AgentStage.PROPOSAL])
            return self._plan(
                facts,
                CorrectionAction.RERUN_STAGE_1,
                stages,
                2 if facts.is_cross_page != CrossPageState.SAME_PAGE else 1,
                "工作区或业务页错误，重跑受影响页 Stage 1 及后续连接。",
            )
        if facts.is_cross_page == CrossPageState.CROSS_PAGE:
            return self._plan(
                facts,
                CorrectionAction.RERUN_STAGE_2_AND_3,
                [
                    AgentStage.PAGE_SCAN,
                    AgentStage.BUILD_CROSS_PAGE_TASKS,
                    AgentStage.CROSS_PAGE_COMPLETION,
                    AgentStage.VALIDATION,
                    AgentStage.PROPOSAL,
                ],
                2,
                "存在跨页索引，先复核来源引用，再定向补全单连接终点。",
            )
        if facts.is_cross_page == CrossPageState.UNKNOWN:
            return self._plan(
                facts,
                CorrectionAction.RERUN_STAGE_2_AND_3,
                [
                    AgentStage.PAGE_SCAN,
                    AgentStage.BUILD_CROSS_PAGE_TASKS,
                    AgentStage.CROSS_PAGE_COMPLETION,
                    AgentStage.VALIDATION,
                    AgentStage.PROPOSAL,
                ],
                2,
                "跨页状态未知，先由 Stage 2 重新判断；仅在确认跨页后定向运行 Stage 3。",
            )
        return self._plan(
            facts,
            CorrectionAction.RERUN_STAGE_2,
            [AgentStage.PAGE_SCAN, AgentStage.VALIDATION, AgentStage.PROPOSAL],
            1,
            "不存在跨页索引，仅重跑目标图纸 Stage 2。",
        )

    @staticmethod
    def _plan(
        facts: CorrectionFacts,
        action: CorrectionAction,
        stages: list[AgentStage],
        estimated_model_calls: int,
        reason: str,
    ) -> CorrectionPlan:
        return CorrectionPlan(
            feedback_id=facts.feedback_id,
            action=action,
            stages=stages,
            target=facts.target,
            source_drawing_ids=list(facts.affected_drawing_ids),
            target_drawing_ids=list(facts.target_drawing_ids),
            allowed_fields=[facts.target.field] if facts.target.field else [],
            estimated_model_calls=estimated_model_calls,
            reason=reason,
        )
