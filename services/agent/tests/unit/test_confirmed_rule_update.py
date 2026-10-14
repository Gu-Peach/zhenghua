from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.application.candidate_release import CandidateReleaseService
from src.application.supervisor_handlers import ResumeWorkflowHandler
from src.domain.enums import RunStatus, WorkflowKind


def test_direct_publication_requires_confirmation_and_source_owner_not_evaluation() -> None:
    async def run() -> None:
        candidate = SimpleNamespace(source_feedback_ids=["f"])
        candidates = AsyncMock()
        candidates.get.return_value = candidate
        data = AsyncMock()
        data.get_accepted_feedback.return_value = SimpleNamespace(correction_run_id="source")
        runs = AsyncMock()
        runs.get_required.return_value = SimpleNamespace(requested_by="owner")
        workflow = AsyncMock()
        service = CandidateReleaseService(
            candidates=candidates,
            data=data,
            runs=runs,
            workflow=workflow,
            evals=AsyncMock(),
            artifacts=AsyncMock(),
            allow_real_model=False,
        )
        with pytest.raises(ValueError, match="explicit"):
            await service.confirm("c", "owner", False)
        with pytest.raises(PermissionError):
            await service.confirm("c", "other", True)
        workflow.publish_confirmed.assert_not_called()
        await service.confirm("c", "owner", True)
        workflow.publish_confirmed.assert_awaited_once_with("c", "owner")
        service.evals.get.assert_not_called()
        candidates.gate_passed.assert_not_called()

    asyncio.run(run())


def test_existing_candidate_confirmation_does_not_resume_or_rebuild_run() -> None:
    async def run() -> None:
        run = SimpleNamespace(agent_run_id="run", project_id="p", status=RunStatus.NEEDS_REVIEW)
        control = Mock()
        control.get_required = AsyncMock(return_value=run)
        control.provide_input = AsyncMock()
        control.artifacts = AsyncMock()
        control.artifacts.list_for_run.return_value = [
            {"kind": "profile_candidate", "candidate": {"candidate_id": "c", "status": "DRAFT"}}
        ]
        control.runs = AsyncMock()
        control.publisher = AsyncMock()
        control.publisher.has_event.return_value = False
        release = AsyncMock()
        release.confirm.return_value = SimpleNamespace(
            candidate_id="c", model_dump=lambda **_: {"candidate_id": "c", "status": "ACTIVE"}
        )
        command = SimpleNamespace(
            target=SimpleNamespace(agent_run_id="run"),
            command_id="cmd",
            user_id="owner",
            action="authorize_profile_candidate",
            payload={},
            workflow=WorkflowKind.RESUME_WAITING_RUN,
        )
        handler = ResumeWorkflowHandler(control, AsyncMock(), release)
        first = await handler.dispatch(command)
        assert first.status == "COMPLETED"
        assert run.status == RunStatus.SUCCEEDED
        await handler.dispatch(command)
        control.provide_input.assert_not_called()
        control.publisher.publish.assert_awaited_once()
        assert release.confirm.await_count == 2  # repository handles the same candidate idempotently

    asyncio.run(run())
