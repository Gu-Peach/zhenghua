from __future__ import annotations

import asyncio
import logging

import pytest

from agent_service.application.run_control import RunControlService
from agent_service.application.worker import AgentWorker, RunExecutionOutcome
from agent_service.domain.enums import RunStatus, RunType, ScopeType
from agent_service.domain.models.runs import AgentRun, RunScope
from agent_service.harness import (
    InMemoryArtifactRepository,
    InMemoryEventRepository,
    InMemoryProposalRepository,
    InMemoryRunRepository,
)
from agent_service.harness.stores import CancellationToken
from agent_service.infrastructure.queue import InMemoryRunQueue


class FailingExecutor:
    async def execute(self, run: AgentRun, cancellation: CancellationToken) -> RunExecutionOutcome:
        raise ValueError("Bearer secret-test-token; private-model-content")


def test_worker_logs_failure_location_without_secret_or_model_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def execute() -> None:
        runs, events = InMemoryRunRepository(), InMemoryEventRepository()
        artifacts, queue = InMemoryArtifactRepository(), InMemoryRunQueue()
        control = RunControlService(runs=runs, events=events, artifacts=artifacts, queue=queue)
        worker = AgentWorker(
            runs=runs,
            queue=queue,
            publisher=control.publisher,
            artifacts=artifacts,
            proposals=InMemoryProposalRepository(),
        )
        worker.register(RunType.SCOPED_CORRECTION, FailingExecutor())
        run = AgentRun(
            idempotency_key="failure-test",
            run_type=RunType.SCOPED_CORRECTION,
            project_id="project",
            source_document_id="pdf",
            requested_by="user",
            scope=RunScope(type=ScopeType.CONNECTION, id="connection"),
        )
        await runs.save(run)
        await queue.enqueue(run.agent_run_id)
        with caplog.at_level(logging.ERROR, logger="agent_service.application.worker"):
            assert await worker.run_once()
        result = await runs.get(run.agent_run_id)
        assert result is not None and result.status == RunStatus.FAILED
        assert result.error is not None and result.error.code == "INTERNAL_ERROR"
        assert run.agent_run_id in caplog.text
        assert "ValueError" in caplog.text and "test_worker_failure_logging.py" in caplog.text
        assert "secret-test-token" not in caplog.text
        assert "private-model-content" not in caplog.text
        assert "secret-test-token" not in result.error.message

    asyncio.run(execute())
