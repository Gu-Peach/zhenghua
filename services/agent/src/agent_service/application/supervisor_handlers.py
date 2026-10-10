from __future__ import annotations

from ..domain.enums import CorrectionIssueKind, RunType, ScopeType, WorkflowKind
from ..domain.models.result_data import ConnectionSearchQuery, PrepareCorrectionRequest
from ..domain.models.runs import CreateRunRequest, RunScope
from ..domain.models.supervisor import WorkflowCommand
from ..domain.ports import ProposalSink
from ..profiles import ProfileRegistry
from ..tools.result_data import ControlledResultDataTool
from .run_control import RunControlService
from .workflow_registry import WorkflowDispatchReceipt, WorkflowRegistry


class ProcessDocumentWorkflowHandler:
    def __init__(self, run_control: RunControlService) -> None:
        self._runs = run_control

    async def dispatch(self, command: WorkflowCommand) -> WorkflowDispatchReceipt:
        attachments = command.payload.get("attachment_ids") or []
        if not command.project_id or not attachments:
            return _waiting(command, "处理图纸需要 project_id 和 source document。")
        hints = command.payload.get("extracted_hints") or {}
        request = CreateRunRequest(
            run_type=RunType.FULL_EXTRACTION,
            project_id=command.project_id,
            source_document_id=str(attachments[0]),
            requested_by=command.user_id,
            profile_hint=str(hints.get("profile_key")) if hints.get("profile_key") else None,
            expected_result_version=(
                int(hints["expected_result_version"])
                if hints.get("expected_result_version") is not None
                else None
            ),
            scope=RunScope(type=ScopeType.PROJECT, id=command.project_id),
        )
        run = await self._runs.create(request, command.command_id)
        return WorkflowDispatchReceipt(
            command_id=command.command_id,
            workflow=command.workflow,
            status="QUEUED",
            agent_run_id=run.agent_run_id,
            message="图纸处理任务已入队。",
        )


class CorrectionWorkflowHandler:
    def __init__(
        self,
        run_control: RunControlService,
        result_data: ControlledResultDataTool,
        proposals: ProposalSink,
    ) -> None:
        self._runs = run_control
        self._result_data = result_data
        self._proposals = proposals

    async def dispatch(self, command: WorkflowCommand) -> WorkflowDispatchReceipt:
        if command.action == "commit_result_patch":
            return await self._commit_result_patch(command)
        hints = command.payload.get("extracted_hints") or {}
        feedback_id = hints.get("feedback_id")
        project_id = command.project_id
        target_id = command.target.connection_id
        expected_result_version: int | None = None
        source_document_id = str(hints.get("source_document_id") or "server-controlled")
        auto_prepared = False
        if not feedback_id:
            issue_kind = (
                CorrectionIssueKind.DIRECT_VALUE_CHANGE
                if "suggested_value" in hints
                else CorrectionIssueKind.RECOGNITION_ERROR
            )
            try:
                prepared = await self._result_data.prepare_correction(
                    PrepareCorrectionRequest(
                        query=ConnectionSearchQuery(
                            project_id=command.project_id,
                            project_name=command.target.project_name or _text_hint(hints, "project_name"),
                            workspace_id=command.target.workspace_id,
                            workspace_name=command.target.workspace_name
                            or _text_hint(hints, "workspace_name"),
                            workspace_page=command.target.workspace_page
                            or _text_hint(hints, "workspace_page"),
                            result_version_id=command.target.result_version_id,
                            connection_id=command.target.connection_id,
                            wire_number=command.target.wire_number,
                            terminal=command.target.terminal or _text_hint(hints, "terminal"),
                        ),
                        requested_by=command.user_id,
                        field=command.target.field or _text_hint(hints, "field"),
                        observed_problem=str(command.payload.get("user_message") or "用户要求重新检查连接。"),
                        suggested_value_present="suggested_value" in hints,
                        suggested_value=hints.get("suggested_value"),
                        issue_kind=issue_kind,
                    )
                )
            except (LookupError, ValueError) as exc:
                return _waiting(command, str(exc))
            feedback_id = prepared.feedback_id
            project_id = prepared.match.project_id
            target_id = prepared.match.connection_id
            expected_result_version = prepared.expected_result_version
            source_document_id = prepared.match.source_document_id
            auto_prepared = True
        else:
            target_id = (
                command.target.connection_id or command.target.drawing_id or command.target.workspace_id
            )
            expected_hint = hints.get("expected_result_version")
            if expected_hint is not None:
                expected_result_version = int(expected_hint)
        if not project_id or not feedback_id or not target_id or expected_result_version is None:
            return _waiting(command, "修订需要唯一目标、feedback 和预期结果版本。")
        scope_type = (
            ScopeType.CONNECTION
            if command.target.connection_id or auto_prepared
            else ScopeType.DRAWING
            if command.target.drawing_id
            else ScopeType.WORKSPACE
        )
        request = CreateRunRequest(
            run_type=RunType.SCOPED_CORRECTION,
            project_id=project_id,
            source_document_id=source_document_id,
            feedback_id=str(feedback_id),
            requested_by=command.user_id,
            expected_result_version=expected_result_version,
            scope=RunScope(
                type=scope_type,
                id=target_id,
                field=command.target.field,
            ),
        )
        run = await self._runs.create(request, command.command_id)
        return WorkflowDispatchReceipt(
            command_id=command.command_id,
            workflow=command.workflow,
            status="QUEUED",
            agent_run_id=run.agent_run_id,
            message="局部修订任务已入队。",
        )

    async def _commit_result_patch(self, command: WorkflowCommand) -> WorkflowDispatchReceipt:
        hints = command.payload.get("extracted_hints") or {}
        proposal_id = command.target.proposal_id or _text_hint(hints, "proposal_id")
        if not proposal_id:
            return _waiting(command, "提交修订需要 proposal_id。")
        proposal = await self._proposals.get(proposal_id)
        if proposal is None:
            return _waiting(command, "没有找到对应的修订 proposal。")
        if not proposal.validation.schema_valid or not proposal.validation.business_rules_valid:
            return _waiting(command, "该 proposal 未通过确定性校验，不能提交。")
        result = await self._result_data.commit_result_patch(
            proposal,
            confirmed_by=command.user_id,
        )
        improvement_run_id: str | None = None
        if result.accepted_feedback:
            feedback = result.accepted_feedback[0]
            improvement = await self._runs.create(
                CreateRunRequest(
                    run_type=RunType.IMPROVEMENT_CANDIDATE,
                    project_id=result.project_id,
                    source_document_id=feedback.feedback_id,
                    feedback_id=feedback.feedback_id,
                    requested_by=command.user_id,
                    profile_hint=feedback.profile.key,
                    expected_result_version=result.result_version,
                    scope=RunScope(type=ScopeType.PROFILE, id=feedback.profile.key),
                ),
                f"improvement:{proposal_id}:{feedback.feedback_id}",
            )
            improvement_run_id = improvement.agent_run_id
        return WorkflowDispatchReceipt(
            command_id=command.command_id,
            workflow=command.workflow,
            status="QUEUED" if improvement_run_id else "COMPLETED",
            agent_run_id=improvement_run_id,
            message=(f"修订已提交为结果版本 {result.result_version}；已异步启动问题归因。"),
            payload={
                "proposal_id": proposal_id,
                "result_version": result.result_version,
                "result_version_id": result.result_version_id,
                "improvement_run_id": improvement_run_id,
            },
        )


class ReadOnlyWorkflowHandler:
    def __init__(self, run_control: RunControlService, profiles: ProfileRegistry) -> None:
        self._runs = run_control
        self._profiles = profiles

    async def dispatch(self, command: WorkflowCommand) -> WorkflowDispatchReceipt:
        if command.action == "query_status":
            run_id = command.target.agent_run_id
            if not run_id:
                return _waiting(command, "查询任务状态需要 agent_run_id。")
            run = await self._runs.get_required(run_id)
            current_stage = run.current_stage.value if run.current_stage else "无"
            return WorkflowDispatchReceipt(
                command_id=command.command_id,
                workflow=command.workflow,
                status="COMPLETED",
                agent_run_id=run.agent_run_id,
                message=f"任务状态：{run.status.value}；当前阶段：{current_stage}。",
            )
        if command.action == "view_rules":
            hints = command.payload.get("extracted_hints") or {}
            profile_key = hints.get("profile_key")
            if not profile_key:
                return _waiting(command, "查看规则需要指定 profile_key。")
            binding = self._profiles.bind(str(profile_key), allow_experimental=True)
            summary = (
                f"{binding.rules.display_name} {binding.profile.version}："
                f"{binding.rules.extraction.output_contract}"
            )
            return WorkflowDispatchReceipt(
                command_id=command.command_id,
                workflow=command.workflow,
                status="COMPLETED",
                message=summary,
            )
        return WorkflowDispatchReceipt(
            command_id=command.command_id,
            workflow=command.workflow,
            status="COMPLETED",
            message="只读请求已路由到业务查询层。",
        )


class ResumeWorkflowHandler:
    def __init__(self, run_control: RunControlService) -> None:
        self._runs = run_control

    async def dispatch(self, command: WorkflowCommand) -> WorkflowDispatchReceipt:
        run_id = command.target.agent_run_id
        if not run_id:
            return _waiting(command, "恢复任务需要 agent_run_id。")
        hints = command.payload.get("extracted_hints") or {}
        input_payload = dict(hints)
        if command.action == "authorize_profile_candidate":
            input_payload["approve_profile_candidate"] = True
            input_payload["reviewer_id"] = command.user_id
        run = await self._runs.provide_input(run_id, input_payload)
        return WorkflowDispatchReceipt(
            command_id=command.command_id,
            workflow=command.workflow,
            status="QUEUED",
            agent_run_id=run.agent_run_id,
            message="人工确认已保存，任务已恢复。",
        )


def register_default_supervisor_handlers(
    registry: WorkflowRegistry,
    run_control: RunControlService,
    profiles: ProfileRegistry,
    result_data: ControlledResultDataTool,
    proposals: ProposalSink,
) -> None:
    registry.register(WorkflowKind.PROFILE_DETECTION, ProcessDocumentWorkflowHandler(run_control))
    registry.register(
        WorkflowKind.CORRECTION,
        CorrectionWorkflowHandler(run_control, result_data, proposals),
    )
    registry.register(WorkflowKind.READ_ONLY_QUERY, ReadOnlyWorkflowHandler(run_control, profiles))
    registry.register(WorkflowKind.RESUME_WAITING_RUN, ResumeWorkflowHandler(run_control))


def _waiting(command: WorkflowCommand, message: str) -> WorkflowDispatchReceipt:
    return WorkflowDispatchReceipt(
        command_id=command.command_id,
        workflow=command.workflow,
        status="WAITING_INPUT",
        message=message,
    )


def _text_hint(hints: dict[str, object], key: str) -> str | None:
    value = hints.get(key)
    return str(value) if value not in (None, "") else None
