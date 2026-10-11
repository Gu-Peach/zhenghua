from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from agent_service.application.supervisor_handlers import CorrectionWorkflowHandler
from agent_service.domain.enums import ErrorCode, RunType, ScopeType, WorkflowKind
from agent_service.domain.errors import AgentServiceError
from agent_service.domain.models.improvement import AcceptedFeedback, AffectedScope
from agent_service.domain.models.proposals import ProposalValidation, ResultPatchProposal
from agent_service.domain.models.result_data import ResultCommitResult
from agent_service.domain.models.runs import AgentRun, ModelRef, ProfileRef, RunScope
from agent_service.domain.models.supervisor import SupervisorTargetHint, WorkflowCommand


def test_improvement_launch_failure_does_not_report_committed_correction_as_failed() -> None:
    async def run() -> None:
        profile = ProfileRef(key="zh", version="1.0.0", checksum="sha256:" + "a" * 64)
        proposal = ResultPatchProposal(
            proposal_id="correction:result-proposal",
            agent_run_id="correction",
            project_id="project",
            base_result_version=1,
            profile=profile,
            model=ModelRef(name="fake"),
            scope=RunScope(type=ScopeType.CONNECTION, id="connection"),
            feedback_id="feedback",
            validation=ProposalValidation(schema_valid=True, business_rules_valid=True),
        )
        feedback = AcceptedFeedback(
            feedback_id="feedback",
            project_id="project",
            accepted=True,
            result_version_id="version-2",
            profile=profile,
            model_name="fake",
            target=AffectedScope(type=ScopeType.CONNECTION, ids=["connection"]),
            before={"end_terminal": "999"},
            after={"end_terminal": "2"},
            evidence_ids=["evidence"],
            stage_artifact_ids=["artifact"],
            prompt_checksum=profile.checksum,
        )
        control = AsyncMock()
        control.get_required.return_value = AgentRun(
            agent_run_id="correction",
            idempotency_key="correction",
            run_type=RunType.SCOPED_CORRECTION,
            project_id="project",
            source_document_id="pdf",
            requested_by="user",
            feedback_id="feedback",
            scope=RunScope(type=ScopeType.CONNECTION, id="connection"),
        )
        control.create.side_effect = AgentServiceError(
            ErrorCode.PERSISTENCE_UNAVAILABLE, "Queue unavailable", retryable=True
        )
        proposals = AsyncMock()
        proposals.get.return_value = proposal
        data = AsyncMock()
        data.commit_result_patch.return_value = ResultCommitResult(
            proposal_id=proposal.proposal_id,
            project_id="project",
            previous_result_version=1,
            result_version=2,
            result_version_id="version-2",
            confirmed_by="user",
            accepted_feedback=[feedback],
        )
        handler = CorrectionWorkflowHandler(control, data, proposals)
        receipt = await handler.dispatch(
            WorkflowCommand(
                conversation_id="conversation",
                turn_id="confirmation",
                user_id="user",
                project_id="project",
                workflow=WorkflowKind.CORRECTION,
                action="commit_result_patch",
                target=SupervisorTargetHint(proposal_id=proposal.proposal_id),
            )
        )
        assert receipt.status == "COMPLETED"
        assert receipt.payload["correction_committed"] is True
        assert receipt.payload["result_version"] == 2
        assert receipt.payload["improvement_status"] == "START_FAILED"
        assert receipt.payload["improvement_error"] == {"code": "PERSISTENCE_UNAVAILABLE", "retryable": True}
        request = control.create.call_args.args[0]
        assert request.source_document_id == "pdf"
        assert request.feedback_id == "feedback"
        assert request.profile == profile
        assert "修订已生效" in receipt.message
        data.commit_result_patch.assert_awaited_once()

    asyncio.run(run())
