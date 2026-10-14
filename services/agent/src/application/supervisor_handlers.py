from __future__ import annotations

import logging

from src.domain.enums import CorrectionIssueKind, EventType, RunStatus, RunType, ScopeType, WorkflowKind
from src.domain.errors import AgentServiceError
from src.domain.models.result_data import ConnectionSearchQuery, PrepareCorrectionRequest
from src.domain.models.runs import CreateRunRequest, RunOptions, RunScope
from src.domain.models.supervisor import WorkflowCommand
from src.domain.ports import ProposalSink
from src.profiles import ProfileRegistry
from src.tools.result_data import ControlledResultDataTool
from src.application.candidate_release import CandidateReleaseService
from src.application.run_control import RunControlService
from src.application.workflow_registry import WorkflowDispatchReceipt, WorkflowRegistry

logger = logging.getLogger(__name__)


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
        if command.payload.get("correction_items"):
            return await self._dispatch_batch(command)
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
                            start_terminal=command.target.start_terminal
                            or _text_hint(hints, "start_terminal"),
                            end_terminal=command.target.end_terminal or _text_hint(hints, "end_terminal"),
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

    async def _dispatch_batch(self, command: WorkflowCommand) -> WorkflowDispatchReceipt:
        items = [
            PrepareCorrectionRequest.model_validate(value) for value in command.payload["correction_items"]
        ]
        prepared_items = []
        try:
            for index, item in enumerate(items):
                item.requested_by = command.user_id
                item.item_id = f"{command.conversation_id}:{command.turn_id}:{index}"
                if command.project_id:
                    if item.query.project_id and item.query.project_id != command.project_id:
                        raise ValueError("一个纠错批次不能跨项目。")
                    item.query.project_id = command.project_id
                prepared_items.append(await self._result_data.prepare_correction(item))
            identities = {(item.match.project_id, item.match.result_version_id) for item in prepared_items}
            if len(identities) != 1:
                raise ValueError("一个纠错批次必须使用同一项目的同一结果版本。")
        except (LookupError, ValueError) as exc:
            return _waiting(command, str(exc))
        first = prepared_items[0]
        paths = []
        if any(item.issue_kind == CorrectionIssueKind.DIRECT_VALUE_CHANGE for item in items):
            paths.append("直接修订（不调用识别模型）")
        reextract = [
            prepared.match.is_cross_page.value
            for item, prepared in zip(items, prepared_items, strict=True)
            if item.issue_kind != CorrectionIssueKind.DIRECT_VALUE_CHANGE
        ]
        if "same_page" in reextract:
            paths.append("Stage 2 同页重新识别")
        if any(value != "same_page" for value in reextract):
            paths.append("Stage 2 复核，再按实际引用决定 Stage 3")
        run = await self._runs.create(
            CreateRunRequest(
                run_type=RunType.SCOPED_CORRECTION,
                project_id=first.match.project_id,
                source_document_id=first.match.source_document_id,
                feedback_id=first.feedback_id,
                requested_by=command.user_id,
                expected_result_version=first.expected_result_version,
                scope=RunScope(type=ScopeType.PROJECT, id=first.match.project_id),
                options=RunOptions(correction_feedback_ids=[item.feedback_id for item in prepared_items]),
            ),
            f"correction:{command.user_id}:{command.conversation_id}:{command.turn_id}",
        )
        return WorkflowDispatchReceipt(
            command_id=command.command_id,
            workflow=command.workflow,
            status="QUEUED",
            agent_run_id=run.agent_run_id,
            message=f"已定位 {len(prepared_items)} 项纠错；本批涉及：{'；'.join(paths)}。",
            payload={"feedback_ids": run.options.correction_feedback_ids},
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
        correction_run = await self._runs.get_required(proposal.agent_run_id)
        if correction_run.project_id != proposal.project_id:
            raise ValueError("Correction proposal and source run belong to different projects.")
        result = await self._result_data.commit_result_patch(
            proposal,
            confirmed_by=command.user_id,
        )
        improvement_run_id: str | None = None
        improvement_error: dict[str, object] | None = None
        if result.accepted_feedback:
            feedback = result.accepted_feedback[0]
            try:
                improvement = await self._runs.create(
                    CreateRunRequest(
                        run_type=RunType.IMPROVEMENT_CANDIDATE,
                        project_id=result.project_id,
                        source_document_id=correction_run.source_document_id,
                        feedback_id=feedback.feedback_id,
                        requested_by=command.user_id,
                        profile_hint=feedback.profile.key,
                        profile=feedback.profile,
                        expected_result_version=result.result_version,
                        scope=RunScope(type=ScopeType.PROFILE, id=feedback.profile.key),
                        options=RunOptions(
                            correction_feedback_ids=[item.feedback_id for item in result.accepted_feedback]
                        ),
                    ),
                    f"improvement:{proposal_id}:{feedback.feedback_id}",
                )
                improvement_run_id = improvement.agent_run_id
            except AgentServiceError as exc:
                # Business correction is already committed. Never report it as a failed write.
                improvement_error = {"code": exc.code.value, "retryable": exc.retryable}
                logger.warning(
                    "Correction %s committed; improvement launch failed (%s).", proposal_id, exc.code.value
                )
        message = (
            f"已原位更新结果，修订号 {result.result_revision}；连接 ID 和线号保持不变。"
            if result.update_mode == "in_place"
            else f"修订已提交为结果版本 {result.result_version}。"
        )
        if improvement_run_id:
            message += "已异步启动问题归因。"
        elif improvement_error:
            message += (
                "问题归因启动失败，修订已生效；可重试同一 proposal 的确认以补启动，不会重复创建结果版本。"
            )
        return WorkflowDispatchReceipt(
            command_id=command.command_id,
            workflow=command.workflow,
            status="QUEUED" if improvement_run_id else "COMPLETED",
            agent_run_id=improvement_run_id,
            message=message,
            payload={
                "proposal_id": proposal_id,
                "result_version": result.result_version,
                "result_version_id": result.result_version_id,
                "result_revision": result.result_revision,
                "update_mode": result.update_mode,
                "updated_connection_ids": result.updated_connection_ids,
                "improvement_run_id": improvement_run_id,
                "correction_committed": True,
                "improvement_status": "QUEUED"
                if improvement_run_id
                else "START_FAILED"
                if improvement_error
                else "NOT_REQUIRED",
                "improvement_error": improvement_error,
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
    def __init__(
        self,
        run_control: RunControlService,
        result_data: ControlledResultDataTool,
        candidate_release: CandidateReleaseService | None = None,
    ) -> None:
        self._runs = run_control
        self._result_data = result_data
        self._candidate_release = candidate_release

    async def dispatch(self, command: WorkflowCommand) -> WorkflowDispatchReceipt:
        run_id = command.target.agent_run_id
        if not run_id:
            return _waiting(command, "恢复任务需要 agent_run_id。")
        hints = command.payload.get("extracted_hints") or {}
        input_payload = dict(hints)
        run = await self._runs.get_required(run_id)
        await self._result_data.authorize_project(run.project_id, command.user_id)
        artifacts = await self._runs.artifacts.list_for_run(run_id)
        candidate = next(
            (
                a
                for a in artifacts
                if a.get("kind") in {"profile_rule_update", "profile_candidate", "profile_candidate_pending"}
            ),
            None,
        )
        if candidate and command.action == "authorize_profile_candidate":
            if self._candidate_release is None:
                return _waiting(command, "规则发布服务未配置，尚未修改规则。")
            published = await self._candidate_release.confirm(
                str(candidate["candidate"]["candidate_id"]),
                command.user_id,
                True,
            )
            artifact_id = f"{run_id}:profile-rule-update"
            await self._runs.artifacts.put(
                artifact_id,
                {
                    "artifact_id": artifact_id,
                    "agent_run_id": run_id,
                    "kind": "profile_rule_update",
                    "candidate": published.model_dump(mode="json"),
                    "authorized_by": command.user_id,
                    "evaluation_required": False,
                    "reason": "用户确认后规则修改已落地并启用；旧项目未自动切换规则版本。",
                },
            )
            if run.status in {RunStatus.NEEDS_REVIEW, RunStatus.WAITING_INPUT}:
                run.status = RunStatus.SUCCEEDED
                await self._runs.runs.save(run)
                if not await self._runs.publisher.has_event(run_id, EventType.RUN_COMPLETED):
                    await self._runs.publisher.publish(
                        run,
                        EventType.RUN_COMPLETED,
                        message="规则修改已确认并启用。",
                        artifact_refs=[artifact_id],
                        metrics={"rules_updated": True},
                    )
            return WorkflowDispatchReceipt(
                command_id=command.command_id,
                workflow=command.workflow,
                status="COMPLETED",
                agent_run_id=run_id,
                message="规则修改已落地并启用，无需评测或再次审核。",
                payload={"candidate_id": published.candidate_id, "rules_updated": True},
            )
        if run.status != RunStatus.WAITING_INPUT:
            return WorkflowDispatchReceipt(
                command_id=command.command_id,
                workflow=command.workflow,
                status="COMPLETED",
                agent_run_id=run_id,
                message=f"任务当前为 {run.status.value}，没有等待中的确认，不会重复执行。",
            )
        if str(input_payload.get("approve_profile_candidate", "")).lower() == "false":
            input_payload["approve_profile_candidate"] = False
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
    candidate_release: CandidateReleaseService | None = None,
) -> None:
    registry.register(WorkflowKind.PROFILE_DETECTION, ProcessDocumentWorkflowHandler(run_control))
    registry.register(
        WorkflowKind.CORRECTION,
        CorrectionWorkflowHandler(run_control, result_data, proposals),
    )
    registry.register(WorkflowKind.READ_ONLY_QUERY, ReadOnlyWorkflowHandler(run_control, profiles))
    registry.register(
        WorkflowKind.RESUME_WAITING_RUN, ResumeWorkflowHandler(run_control, result_data, candidate_release)
    )


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
