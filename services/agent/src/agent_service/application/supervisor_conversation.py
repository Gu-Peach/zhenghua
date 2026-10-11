from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..agents.supervisor import SupervisorAgent
from ..domain.enums import ProfileDetectionStatus, RunType, ScopeType
from ..domain.models.imports import ImportedDocument
from ..domain.models.runs import CreateRunRequest, ProfileConfirmation, RunOptions, RunScope
from ..domain.models.supervisor import ConversationTurn, SupervisorUserEvent, WorkflowCommand
from ..domain.ports import ProposalSink
from ..graphs.supervisor.graph import SupervisorGraphResult, run_supervisor_graph
from ..infrastructure.business_imports import SupabaseBusinessImports
from ..infrastructure.conversation_memory import (
    ConversationAttachment,
    ConversationMemory,
    ShortTermConversationStore,
)
from ..infrastructure.document.pdf_runtime import load_pdf_module
from ..infrastructure.source_documents import SourceDocumentProvider
from ..profiles import ProfileRegistry
from ..tools.profile_detection import ProfileDetectionTool
from .profile_assignment import ProfileAssignmentService
from .run_control import RunControlService
from .workflow_registry import WorkflowDispatchReceipt, WorkflowRegistry

EventCallback = Callable[[SupervisorUserEvent], Awaitable[None]]


class SupervisorConversationService:
    """Remember recent turns and expose detection/confirmation through the normal Supervisor Graph."""

    def __init__(
        self,
        *,
        agent: SupervisorAgent,
        workflows: WorkflowRegistry,
        profiles: ProfileRegistry,
        detection: ProfileDetectionTool,
        memory: ShortTermConversationStore,
        attachment_root: Path,
        model_name: str = "unknown",
        business_imports: SupabaseBusinessImports | None = None,
        documents: SourceDocumentProvider | None = None,
        run_control: RunControlService | None = None,
        proposals: ProposalSink | None = None,
    ) -> None:
        self._agent = agent
        self._workflows = workflows
        self._profiles = profiles
        self._detection = detection
        self._memory = memory
        self._attachment_root = attachment_root.resolve()
        self._model_name = model_name
        self._imports, self._documents, self._runs = business_imports, documents, run_control
        self._proposals = proposals

    async def import_pdf(
        self,
        *,
        conversation_id: str,
        user_id: str,
        key: str,
        project_name: str,
        filename: str,
        content: bytes,
    ) -> ImportedDocument:
        if self._imports is None or self._documents is None:
            raise ValueError("Business imports require Supabase persistence.")
        memory = self._memory.get(conversation_id, user_id)
        async with memory.lock:
            if memory.project_id and memory.import_key != key:
                raise ValueError("Use a new conversation for a new PDF, or reattach the same import.")
            page_count = await asyncio.to_thread(_validate_pdf, content)
            imported = await self._imports.import_pdf(
                user_id=user_id,
                key=key,
                name=project_name,
                filename=Path(filename.replace("\\", "/")).name,
                content=content,
                page_count=page_count,
            )
            access = await self._documents.get(imported.source_document_id, imported.project_id)
            memory.attachments[imported.attachment_id] = ConversationAttachment(
                attachment_id=imported.attachment_id,
                filename=imported.filename,
                path=access.local_path,
                size=imported.size,
            )
            memory.imports[imported.attachment_id] = imported
            if memory.import_key is None:
                # A temporary stage-0 attachment is not a confirmation of this business source.
                memory.pending_detection = None
                memory.last_detection = None
                memory.assignment = None
                memory.confirmed_attachment_ids = []
                memory.full_extraction_requested = False
            memory.import_key = key
            memory.project_id = imported.project_id
            memory.current_attachment_ids = [imported.attachment_id]
            return imported

    async def upload_attachment(
        self,
        *,
        conversation_id: str,
        user_id: str,
        filename: str,
        content: bytes,
    ) -> dict[str, Any]:
        memory = self._memory.get(conversation_id, user_id)
        if not content.startswith(b"%PDF-"):
            raise ValueError("Attachment must be a PDF.")
        async with memory.lock:
            if len(memory.attachments) >= 8:
                raise ValueError("A conversation accepts at most eight PDF attachments.")
            attachment_id = str(uuid4())
            folder = hashlib.sha256(f"{user_id}\0{conversation_id}".encode()).hexdigest()
            path = self._attachment_root / folder / f"{attachment_id}.pdf"
            await asyncio.to_thread(_write_pdf, path, content)
            attachment = ConversationAttachment(
                attachment_id=attachment_id,
                filename=Path(filename).name[:200],
                path=path,
                size=len(content),
            )
            memory.attachments[attachment_id] = attachment
            return {"attachment_id": attachment_id, "filename": attachment.filename, "size": attachment.size}

    def snapshot(self, conversation_id: str, user_id: str) -> dict[str, Any]:
        memory = self._memory.get(conversation_id, user_id)
        return {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "memory_backend": "process_short_term",
            "model_name": self._model_name,
            "survives_restart": False,
            "history": list(memory.history),
            "attachment_ids": list(memory.current_attachment_ids),
            "pending_detection": memory.pending_detection.model_dump(mode="json")
            if memory.pending_detection
            else None,
            "profile_assignment": memory.assignment.model_dump(mode="json") if memory.assignment else None,
            "agent_run_id": memory.agent_run_id,
            "project_id": memory.project_id,
            "full_extraction_requested": memory.full_extraction_requested,
        }

    async def turn(
        self, turn: ConversationTurn, *, on_event: EventCallback | None = None
    ) -> SupervisorGraphResult:
        memory = self._memory.get(turn.conversation_id, turn.user_id)
        async with memory.lock:
            digest = hashlib.sha256(turn.model_dump_json(exclude={"occurred_at"}).encode()).hexdigest()
            cached = memory.responses.get(turn.turn_id)
            if cached:
                if cached[0] != digest:
                    raise ValueError("turn_id cannot be reused for different input.")
                return cached[1]
            if memory.project_id and turn.project_id and memory.project_id != turn.project_id:
                raise ValueError("A conversation cannot silently switch projects.")
            if turn.project_id:
                memory.project_id = turn.project_id
            attachments = list(turn.attachment_ids or memory.current_attachment_ids)
            if memory.pending_detection and attachments != memory.pending_attachment_ids:
                raise ValueError("A pending confirmation cannot switch PDF attachments.")
            hint = turn.target_hint.model_copy(deep=True)
            if not hint.agent_run_id:
                hint.agent_run_id = (
                    memory.pending_detection.run_id
                    if memory.pending_detection
                    else memory.agent_run_id or (memory.assignment.run_id if memory.assignment else None)
                )
            enriched = turn.model_copy(
                update={
                    "attachment_ids": attachments,
                    "target_hint": hint,
                    "project_id": turn.project_id or memory.project_id,
                }
            )
            context = self.snapshot(turn.conversation_id, turn.user_id)
            if memory.agent_run_id and self._runs is not None and not memory.pending_detection:
                pending_run = await self._runs.get_required(memory.agent_run_id)
                pending_artifacts = await self._runs.artifacts.list_for_run(memory.agent_run_id)
                context["pending_task"] = {
                    "run_id": pending_run.agent_run_id,
                    "status": pending_run.status.value,
                    "artifacts": [
                        {
                            "kind": item.get("kind"),
                            "proposal_id": item.get("proposal_id"),
                            "diagnoses": item.get("diagnoses"),
                            "candidate_recommended": item.get("candidate_recommended"),
                        }
                        for item in pending_artifacts
                        if item.get("kind") in {"result_proposal", "improvement_diagnosis"}
                    ],
                }
                if self._proposals and pending_run.status.value == "NEEDS_REVIEW":
                    for artifact in pending_artifacts:
                        if artifact.get("kind") == "result_proposal":
                            proposal = await self._proposals.get(str(artifact["proposal_id"]))
                            if proposal:
                                context["pending_task"]["result_proposal"] = proposal.model_dump(mode="json")
            summary = json.dumps(context, ensure_ascii=False)
            contextual = _ConversationWorkflows(self, memory, self._workflows)
            result = await run_supervisor_graph(
                agent=self._agent,
                workflows=contextual,
                turn=enriched,
                context_summary=summary,
                on_event=on_event,
            )
            memory.current_attachment_ids = attachments
            if result.receipt and result.receipt.agent_run_id:
                memory.agent_run_id = result.receipt.agent_run_id
            memory.history.extend(
                [
                    {"role": "user", "content": turn.message[:2000]},
                    {"role": "assistant", "content": result.user_event.user_message[:2000]},
                ]
            )
            memory.history = memory.history[-24:]
            memory.responses[turn.turn_id] = (digest, result)
            while len(memory.responses) > 12:
                memory.responses.popitem(last=False)
            return result

    async def detect(self, command: WorkflowCommand, memory: ConversationMemory) -> WorkflowDispatchReceipt:
        attachment_ids = command.payload.get("attachment_ids") or []
        if len(attachment_ids) != 1:
            raise ValueError("Type detection requires exactly one PDF attachment.")
        attachment = memory.attachments.get(str(attachment_ids[0]))
        if attachment is None:
            raise PermissionError("Attachment is not registered in this conversation.")
        result = await self._detection.detect(
            run_id=f"detection:{uuid4()}",
            project_id=command.project_id or f"conversation:{memory.conversation_id}",
            pdf_path=attachment.path,
        )
        candidate = result.detected_profile or result.assigned_profile
        if candidate:
            display_name = self._profiles.bind(
                candidate.key, candidate.version, allow_experimental=True
            ).rules.display_name
            question = (
                f"首页识别为{display_name}（{candidate.key}），置信度 {result.confidence:.0%}。"
                "请确认，或说明正确类型。"
            )
        else:
            question = result.user_question or "首页无法确认图纸类型，请明确选择 zh 或 abb。"
        result = result.model_copy(
            update={
                "status": ProfileDetectionStatus.WAITING_INPUT,
                "assigned_profile": None,
                "detected_profile": candidate,
                "needs_user_confirmation": True,
                "user_question": question,
            }
        )
        memory.pending_detection = result
        memory.last_detection = result
        memory.pending_attachment_ids = list(attachment_ids)
        memory.assignment = None
        return WorkflowDispatchReceipt(
            command_id=command.command_id,
            workflow=command.workflow,
            status="WAITING_INPUT",
            message=question,
            payload={"profile_detection": result.model_dump(mode="json"), "detection_only": True},
        )

    async def confirm(self, command: WorkflowCommand, memory: ConversationMemory) -> WorkflowDispatchReceipt:
        pending = memory.pending_detection
        if pending is None:
            raise ValueError("No Profile confirmation is pending.")
        if command.target.agent_run_id != pending.run_id:
            raise ValueError("Confirmation does not match the pending detection.")
        if command.payload.get("attachment_ids") != memory.current_attachment_ids:
            raise ValueError("Confirmation cannot change the pending PDF attachment.")
        hints = command.payload.get("extracted_hints") or {}
        key = str(
            hints.get("profile_key") or (pending.detected_profile.key if pending.detected_profile else "")
        )
        if not key:
            return WorkflowDispatchReceipt(
                command_id=command.command_id,
                workflow=command.workflow,
                status="WAITING_INPUT",
                message="原检测没有可靠类型，请明确选择 zh 或 abb。",
            )
        assignment = memory.assignment
        if assignment is None or assignment.binding.profile.key != key:
            assignment = ProfileAssignmentService(self._profiles).confirm(
                pending, profile_key=key, confirmed_by=command.user_id
            )
        memory.assignment = assignment
        memory.confirmed_attachment_ids = list(memory.pending_attachment_ids)
        if memory.full_extraction_requested:
            receipt = await self.start_extraction(command, memory)
            memory.pending_detection = None
            return receipt
        memory.pending_detection = None
        name = assignment.binding.rules.display_name
        return WorkflowDispatchReceipt(
            command_id=command.command_id,
            workflow=command.workflow,
            status="COMPLETED",
            message=f"已确认图纸类型为{name}（{key}）。本轮类型识别完成，未启动三阶段提取。",
            payload={"profile_assignment": assignment.model_dump(mode="json"), "detection_only": True},
        )

    async def start_extraction(
        self,
        command: WorkflowCommand,
        memory: ConversationMemory,
    ) -> WorkflowDispatchReceipt:
        if self._runs is None or memory.assignment is None or self._imports is None:
            raise ValueError("Full extraction requires a business import and confirmed Profile.")
        assignment = memory.assignment
        # Experimental templates remain detection-only until their extraction release gate passes.
        self._profiles.bind(assignment.binding.profile.key, assignment.binding.profile.version)
        attachment_ids = command.payload.get("attachment_ids") or []
        if len(attachment_ids) != 1 or attachment_ids[0] not in memory.imports:
            raise ValueError("Full extraction requires exactly the imported source PDF.")
        imported = memory.imports[attachment_ids[0]]
        if assignment.project_id != imported.project_id or memory.confirmed_attachment_ids != attachment_ids:
            raise ValueError("Profile confirmation belongs to a different PDF or project.")
        await self._imports.require_owner(imported.project_id, command.user_id)
        existing_id = await self._imports.existing_extraction(
            imported.project_id,
            imported.source_document_id,
        )
        pending = memory.pending_detection
        detected = pending or memory.last_detection
        if existing_id or (pending is None and memory.agent_run_id):
            run = await self._runs.get_required(existing_id or memory.agent_run_id or "")
            if run.profile != assignment.binding.profile or run.requested_by != command.user_id:
                raise ValueError("This import already has a differently confirmed task; create a new import.")
        else:
            confirmation = ProfileConfirmation(
                profile=assignment.binding.profile,
                confirmed_by=command.user_id,
                source_checksum=imported.checksum,
                detection_run_id=assignment.run_id,
                detected_profile=assignment.detected_profile,
                confidence=detected.confidence if detected else 0,
                confirmed_at=assignment.assigned_at,
            )
            run = await self._runs.create(
                CreateRunRequest(
                    run_type=RunType.FULL_EXTRACTION,
                    project_id=imported.project_id,
                    source_document_id=imported.source_document_id,
                    requested_by=command.user_id,
                    profile_hint=assignment.binding.profile.key,
                    profile=assignment.binding.profile,
                    expected_result_version=0,
                    scope=RunScope(type=ScopeType.PROJECT, id=imported.project_id),
                    options=RunOptions(profile_confirmation=confirmation),
                ),
                f"full-extraction:{imported.source_document_id}",
            )
        memory.agent_run_id = run.agent_run_id
        return WorkflowDispatchReceipt(
            command_id=command.command_id,
            workflow=command.workflow,
            status=run.status.value
            if run.status.value in {"QUEUED", "RUNNING", "WAITING_INPUT"}
            else "COMPLETED",
            agent_run_id=run.agent_run_id,
            message="类型已确认，三阶段提取任务已登记；进度以持久事件为准。",
            payload={
                "profile_assignment": assignment.model_dump(mode="json"),
                "project_id": imported.project_id,
                "detection_only": False,
                "run_status": run.status.value,
            },
        )


class _ConversationWorkflows(WorkflowRegistry):
    def __init__(
        self, service: SupervisorConversationService, memory: ConversationMemory, base: WorkflowRegistry
    ) -> None:
        super().__init__()
        self._service, self._memory, self._base = service, memory, base

    async def dispatch(self, command: WorkflowCommand) -> WorkflowDispatchReceipt:
        if command.action == "query_context":
            assignment = self._memory.assignment
            pending = self._memory.pending_detection
            if assignment:
                message = (
                    f"本会话已由你确认图纸类型为{assignment.binding.rules.display_name}"
                    f"（{assignment.binding.profile.key}）。"
                )
            elif pending:
                message = pending.user_question or "图纸类型尚待确认。"
            else:
                message = "本会话还没有已确认的图纸类型。"
            return WorkflowDispatchReceipt(
                command_id=command.command_id,
                workflow=command.workflow,
                status="COMPLETED",
                message=message,
                payload={"memory_context": True},
            )
        if command.action == "detect_profile":
            self._memory.full_extraction_requested = False
            return await self._service.detect(command, self._memory)
        if command.action == "resume_with_user_input" and self._memory.pending_detection:
            return await self._service.confirm(command, self._memory)
        if command.action == "resume_with_user_input" and self._memory.assignment:
            if self._memory.full_extraction_requested:
                return await self._service.start_extraction(command, self._memory)
            return WorkflowDispatchReceipt(
                command_id=command.command_id,
                workflow=command.workflow,
                status="COMPLETED",
                message="类型已经确认，本轮只检测任务已完成。",
                payload={"profile_assignment": self._memory.assignment.model_dump(mode="json")},
            )
        attachments = command.payload.get("attachment_ids") or []
        if (
            command.action == "detect_profile_then_extract"
            and len(attachments) == 1
            and (str(attachments[0]) in self._memory.imports)
        ):
            self._memory.full_extraction_requested = True
            if self._memory.assignment and self._memory.confirmed_attachment_ids == attachments:
                return await self._service.start_extraction(command, self._memory)
            return await self._service.detect(command, self._memory)
        if command.action == "detect_profile_then_extract" and any(
            str(item) in self._memory.attachments for item in attachments
        ):
            return WorkflowDispatchReceipt(
                command_id=command.command_id,
                workflow=command.workflow,
                status="WAITING_INPUT",
                message=(
                    "当前附件用于类型识别。完整提取需业务项目和已登记的 source document；请先只识别类型。"
                ),
            )
        return await self._base.dispatch(command)


def _write_pdf(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(content)


def _validate_pdf(content: bytes) -> int:
    if not content.startswith(b"%PDF-"):
        raise ValueError("Upload must be a valid PDF.")
    try:
        with load_pdf_module().open(stream=content, filetype="pdf") as document:
            if document.needs_pass or document.page_count < 1:
                raise ValueError("Encrypted or empty PDF cannot be imported.")
            return int(document.page_count)
    except Exception as exc:
        raise ValueError("Upload must be a readable, unencrypted PDF.") from exc
