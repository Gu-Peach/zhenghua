from __future__ import annotations

from pathlib import Path

from ..domain.enums import SupervisorIntent, SupervisorTurnStatus, WorkflowKind
from ..domain.models.supervisor import (
    ConversationTurn,
    SupervisorDecision,
    SupervisorModelOutput,
    WorkflowCommand,
)
from ..harness.model_gateway import ModelGateway, ModelRequest


class SupervisorAgent:
    """Interpret one user turn and produce a constrained workflow command."""

    def __init__(self, *, gateway: ModelGateway, prompt_path: Path) -> None:
        self._gateway = gateway
        self._prompt = prompt_path.read_text(encoding="utf-8")

    async def decide(
        self,
        turn: ConversationTurn,
        *,
        context_summary: str = "",
    ) -> SupervisorDecision:
        response = await self._gateway.invoke(
            ModelRequest(
                agent_name="supervisor",
                run_id=f"turn:{turn.turn_id}",
                output_model=SupervisorModelOutput,
                messages=[
                    {"role": "system", "content": self._prompt},
                    {
                        "role": "user",
                        "content": {
                            "message": turn.message,
                            "project_id": turn.project_id,
                            "target_hint": turn.target_hint.model_dump(mode="json"),
                            "attachment_count": len(turn.attachment_ids),
                            "context_summary": context_summary,
                        },
                    },
                ],
                metadata={
                    "conversation_id": turn.conversation_id,
                    "turn_id": turn.turn_id,
                    "project_id": turn.project_id,
                },
            )
        )
        if not isinstance(response.parsed, SupervisorModelOutput):
            raise TypeError("Supervisor returned an unexpected structured result.")
        return self._apply_policy(turn, response.parsed)

    def _apply_policy(
        self,
        turn: ConversationTurn,
        model_output: SupervisorModelOutput,
    ) -> SupervisorDecision:
        missing_fields = self._missing_fields(turn, model_output.intent)
        if (
            model_output.requires_input
            or model_output.confidence < 0.65
            or missing_fields
            or model_output.intent == SupervisorIntent.UNKNOWN
        ):
            question = model_output.question or self._question_for(model_output.intent, missing_fields)
            return SupervisorDecision(
                turn_id=turn.turn_id,
                conversation_id=turn.conversation_id,
                intent=model_output.intent,
                confidence=model_output.confidence,
                status=SupervisorTurnStatus.WAITING_INPUT,
                reason=model_output.reason,
                user_message=question,
                requires_input=True,
                missing_fields=missing_fields,
            )

        workflow, action = self._workflow_for(model_output.intent)
        command = WorkflowCommand(
            conversation_id=turn.conversation_id,
            turn_id=turn.turn_id,
            user_id=turn.user_id,
            project_id=turn.project_id,
            workflow=workflow,
            action=action,
            target=turn.target_hint,
            payload={
                "attachment_ids": list(turn.attachment_ids),
                "extracted_hints": dict(model_output.extracted_hints),
                "user_message": turn.message,
            },
        )
        return SupervisorDecision(
            turn_id=turn.turn_id,
            conversation_id=turn.conversation_id,
            intent=model_output.intent,
            confidence=model_output.confidence,
            status=SupervisorTurnStatus.DISPATCHED,
            reason=model_output.reason,
            user_message=self._dispatch_message(model_output.intent),
            requires_input=False,
            command=command,
        )

    @staticmethod
    def _missing_fields(turn: ConversationTurn, intent: SupervisorIntent) -> list[str]:
        missing: list[str] = []
        if intent in {SupervisorIntent.PROCESS_DOCUMENT, SupervisorIntent.DETECT_PROFILE}:
            if not turn.attachment_ids:
                missing.append("attachment_ids")
        if intent in {SupervisorIntent.CORRECT_RESULT, SupervisorIntent.QUERY_STATUS}:
            if not turn.project_id and not turn.target_hint.project_name:
                missing.append("project_id")
        if intent == SupervisorIntent.CORRECT_RESULT:
            if not any(
                (
                    turn.target_hint.connection_id,
                    turn.target_hint.drawing_id,
                    turn.target_hint.workspace_id,
                    turn.target_hint.wire_number,
                    turn.target_hint.terminal,
                )
            ):
                missing.append("correction_target")
        if (
            intent in {SupervisorIntent.QUERY_STATUS, SupervisorIntent.CONFIRM_INPUT}
            and not turn.target_hint.agent_run_id
        ):
            missing.append("agent_run_id")
        if intent == SupervisorIntent.CONFIRM_RESULT_PATCH and not turn.target_hint.proposal_id:
            missing.append("proposal_id")
        if intent == SupervisorIntent.AUTHORIZE_PROFILE_CANDIDATE and not turn.target_hint.agent_run_id:
            missing.append("agent_run_id")
        return missing

    @staticmethod
    def _question_for(intent: SupervisorIntent, missing_fields: list[str]) -> str:
        if missing_fields:
            return f"继续处理前还需要：{', '.join(missing_fields)}。"
        if intent == SupervisorIntent.UNKNOWN:
            return "请说明你要处理图纸、修改线表、查询进度，还是查看提取规则。"
        return "请补充完成该操作所需的信息。"

    @staticmethod
    def _workflow_for(intent: SupervisorIntent) -> tuple[WorkflowKind, str]:
        mapping = {
            SupervisorIntent.DETECT_PROFILE: (WorkflowKind.PROFILE_DETECTION, "detect_profile"),
            SupervisorIntent.QUERY_CONTEXT: (WorkflowKind.READ_ONLY_QUERY, "query_context"),
            SupervisorIntent.PROCESS_DOCUMENT: (
                WorkflowKind.PROFILE_DETECTION,
                "detect_profile_then_extract",
            ),
            SupervisorIntent.CORRECT_RESULT: (WorkflowKind.CORRECTION, "route_correction"),
            SupervisorIntent.QUERY_STATUS: (WorkflowKind.READ_ONLY_QUERY, "query_status"),
            SupervisorIntent.VIEW_RULES: (WorkflowKind.READ_ONLY_QUERY, "view_rules"),
            SupervisorIntent.CONFIRM_INPUT: (
                WorkflowKind.RESUME_WAITING_RUN,
                "resume_with_user_input",
            ),
            SupervisorIntent.CONFIRM_RESULT_PATCH: (
                WorkflowKind.CORRECTION,
                "commit_result_patch",
            ),
            SupervisorIntent.AUTHORIZE_PROFILE_CANDIDATE: (
                WorkflowKind.RESUME_WAITING_RUN,
                "authorize_profile_candidate",
            ),
        }
        try:
            return mapping[intent]
        except KeyError as exc:
            raise ValueError(f"Intent {intent.value} cannot be dispatched.") from exc

    @staticmethod
    def _dispatch_message(intent: SupervisorIntent) -> str:
        messages = {
            SupervisorIntent.DETECT_PROFILE: "我会读取 PDF 首页识别图纸类型，然后请你确认。",
            SupervisorIntent.QUERY_CONTEXT: "我会查看本会话此前的图纸类型和确认状态。",
            SupervisorIntent.PROCESS_DOCUMENT: "已开始识别图纸类型，后续阶段会持续反馈。",
            SupervisorIntent.CORRECT_RESULT: "已开始定位目标连接并选择最小修订范围。",
            SupervisorIntent.QUERY_STATUS: "正在查询任务状态。",
            SupervisorIntent.VIEW_RULES: "正在读取当前 Profile 的公开规则。",
            SupervisorIntent.CONFIRM_INPUT: "已收到确认，正在恢复对应任务。",
            SupervisorIntent.CONFIRM_RESULT_PATCH: "已收到结果修订确认，正在提交新结果版本。",
            SupervisorIntent.AUTHORIZE_PROFILE_CANDIDATE: "已确认创建规则候选，正在恢复改进任务。",
        }
        return messages[intent]
