from __future__ import annotations

import asyncio
import logging
import traceback
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Protocol

from src.domain.enums import AgentStage, ErrorCode, EventType, RunStatus, RunType
from src.domain.errors import AgentServiceError
from src.domain.models.proposals import ResultProposal
from src.domain.models.runs import AgentRun, EventError
from src.domain.models.stage_persistence import RunLease
from src.domain.ports import (
    ArtifactRepository,
    ProposalSink,
    ResultDataRepository,
    RunQueue,
    RunRepository,
)
from src.harness.stores import CancellationToken
from src.infrastructure.run_lease_context import current_run_lease
from src.infrastructure.supabase_stage_repository import SupabaseStageRepository
from src.application.run_control import RunEventPublisher

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RunExecutionOutcome:
    status: RunStatus = RunStatus.SUCCEEDED
    proposal: ResultProposal | None = None
    artifact_ids: list[str] = field(default_factory=list)
    metrics: dict[str, int | float | str | bool | None] = field(default_factory=dict)


class RunExecutor(Protocol):
    async def execute(self, run: AgentRun, cancellation: CancellationToken) -> RunExecutionOutcome: ...


class AgentWorker:
    """Queue consumer kept separate from FastAPI request handling."""

    def __init__(
        self,
        *,
        runs: RunRepository,
        queue: RunQueue,
        publisher: RunEventPublisher,
        artifacts: ArtifactRepository,
        proposals: ProposalSink,
        result_data: ResultDataRepository | None = None,
        durable_stages: SupabaseStageRepository | None = None,
    ) -> None:
        self._runs = runs
        self._queue = queue
        self._publisher = publisher
        self._artifacts = artifacts
        self._proposals = proposals
        self._result_data = result_data
        self._durable_stages = durable_stages
        self._executors: dict[RunType, RunExecutor] = {}
        self._tokens: dict[str, CancellationToken] = {}
        self._stop_event = asyncio.Event()

    def register(self, run_type: RunType, executor: RunExecutor) -> None:
        if run_type in self._executors:
            raise ValueError(f"Executor for {run_type.value} is already registered.")
        self._executors[run_type] = executor

    def cancel(self, agent_run_id: str) -> None:
        token = self._tokens.get(agent_run_id)
        if token is not None:
            token.cancel()

    def request_stop(self) -> None:
        self._stop_event.set()

    async def run_forever(self, *, idle_poll_seconds: float = 0.25) -> None:
        if idle_poll_seconds <= 0:
            raise ValueError("idle_poll_seconds must be positive.")
        while not self._stop_event.is_set():
            processed = await self.run_once()
            if not processed:
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=idle_poll_seconds)
                except TimeoutError:
                    pass

    async def run_once(self) -> bool:
        if self._durable_stages is not None:
            lease = await self._durable_stages.claim()
            if lease is not None:
                return await self._run_durable(lease)
        run_id = await self._queue.dequeue()
        if run_id is None:
            return False
        run = await self._runs.get(run_id)
        if run is None or run.status != RunStatus.QUEUED:
            await self._queue.acknowledge(run_id)
            return True
        executor = self._executors.get(run.run_type)
        if executor is None:
            await self._fail(run, ErrorCode.INVALID_REQUEST, f"No executor for {run.run_type.value}.")
            await self._queue.acknowledge(run_id)
            return True
        token = self._tokens.setdefault(run_id, CancellationToken())
        try:
            token.raise_if_cancelled()
            run.status = RunStatus.RUNNING
            await self._runs.save(run)
            await self._publisher.publish(run, EventType.RUN_STARTED, message="run started")
            outcome = await executor.execute(run, token)
            artifact_ids = list(outcome.artifact_ids)
            metrics = dict(outcome.metrics)
            token.raise_if_cancelled()
            latest = await self._runs.get(run.agent_run_id)
            if latest is None or latest.status == RunStatus.CANCELLED:
                token.cancel()
                token.raise_if_cancelled()
            if outcome.proposal is not None:
                proposal_id = await self._proposals.submit(outcome.proposal)
                await self._artifacts.put(
                    proposal_id,
                    {
                        "artifact_id": proposal_id,
                        "agent_run_id": run.agent_run_id,
                        "kind": "result_proposal",
                        "proposal_id": proposal_id,
                        "proposal": outcome.proposal.model_dump(mode="json"),
                    },
                )
                await self._publisher.publish(
                    run,
                    EventType.PROPOSAL_CREATED,
                    stage=AgentStage.PROPOSAL,
                    message="proposal created",
                    artifact_refs=[proposal_id],
                )
                if run.run_type == RunType.FULL_EXTRACTION and self._result_data is not None:
                    committed = await self._result_data.persist_extraction_proposal(
                        outcome.proposal,
                        run.requested_by,
                    )
                    commit_artifact_id = f"{run.agent_run_id}:result-version"
                    await self._artifacts.put(
                        commit_artifact_id,
                        {
                            "artifact_id": commit_artifact_id,
                            "agent_run_id": run.agent_run_id,
                            "kind": "result_version",
                            "proposal_id": proposal_id,
                            "result_version_id": committed.result_version_id,
                            "result_version": committed.result_version,
                        },
                    )
                    artifact_ids.append(commit_artifact_id)
                    metrics["result_version"] = committed.result_version
            run.status = outcome.status
            await self._runs.save(run)
            final_type = (
                EventType.HUMAN_INPUT_REQUIRED
                if outcome.status in {RunStatus.WAITING_INPUT, RunStatus.NEEDS_REVIEW}
                else EventType.RUN_COMPLETED
            )
            await self._publisher.publish(
                run,
                final_type,
                message="run completed" if final_type == EventType.RUN_COMPLETED else "human input required",
                metrics=metrics,
                artifact_refs=artifact_ids,
            )
        except AgentServiceError as exc:
            if exc.code == ErrorCode.RUN_CANCELLED:
                run.status = RunStatus.CANCELLED
                await self._runs.save(run)
                if not await self._publisher.has_event(run.agent_run_id, EventType.RUN_CANCELLED):
                    await self._publisher.publish(run, EventType.RUN_CANCELLED, message=exc.message)
            else:
                await self._fail(run, exc.code, exc.message, retryable=exc.retryable)
        except Exception as exc:  # worker boundary: normalize unexpected failures
            # Frame locations and type are useful diagnostics; exception messages,
            # source lines and locals may contain credentials or model/private data.
            frames = [
                {
                    "file": frame.filename.replace("\\", "/").rsplit("/", 1)[-1],
                    "line": frame.lineno,
                    "function": frame.name,
                }
                for frame in traceback.extract_tb(exc.__traceback__)
            ]
            logger.error(
                "Worker run %s failed (%s); stage=%s; frames=%s",
                run.agent_run_id,
                type(exc).__name__,
                run.current_stage,
                frames,
            )
            await self._fail(run, ErrorCode.INTERNAL_ERROR, "Unexpected worker failure.")
        finally:
            self._tokens.pop(run_id, None)
            await self._queue.acknowledge(run_id)
        return True

    async def _run_durable(self, lease: RunLease) -> bool:
        """Recover RUNNING leases; a committed result only needs finalization."""
        repository = self._durable_stages
        assert repository is not None
        context = current_run_lease.set(lease)
        token = self._tokens.setdefault(lease.run_id, CancellationToken())

        async def heartbeat() -> None:
            while True:
                await asyncio.sleep(max(0.2, repository.lease_seconds / 3))
                try:
                    await repository.action(lease, "renew", {"seconds": repository.lease_seconds})
                except Exception:
                    token.cancel()
                    return

        renewal = asyncio.create_task(heartbeat())
        try:
            if lease.mode == "cleanup":
                await repository.action(lease, "ack")
                return True
            receipt = await repository.final_receipt(lease.run_id)
            if receipt:
                await repository.finalize(lease.run_id)
                await repository.action(lease, "ack")
                return True
            run = await self._runs.get(lease.run_id)
            if run is None:
                raise ValueError("Missing leased run.")
            executor = self._executors[run.run_type]
            outcome = await executor.execute(run, token)
            token.raise_if_cancelled()
            if outcome.proposal is None:
                await repository.action(lease, "pause", {"status": outcome.status.value})
                await repository.action(lease, "ack")
                return True
            if self._result_data is None:
                raise ValueError("Durable extraction requires result persistence.")
            await self._proposals.submit(outcome.proposal)
            await self._result_data.persist_extraction_proposal(outcome.proposal, run.requested_by)
            await repository.finalize(lease.run_id)
            await repository.action(lease, "ack")
        except Exception as exc:
            logger.error(
                "Durable run %s failed (%s): %s",
                lease.run_id,
                type(exc).__name__,
                exc.details if isinstance(exc, AgentServiceError) else str(exc),
            )
            # Unknown commit outcome: query first. If even that query fails,
            # leave RUNNING and let lease expiry recover; never guess failure.
            try:
                receipt = await repository.final_receipt(lease.run_id)
                if receipt is None:
                    current = await self._runs.get(lease.run_id)
                    await repository.record_attempt(
                        lease.run_id,
                        current.current_stage if current and current.current_stage else AgentStage.RENDER,
                        "run-recovery",
                        {
                            "error_type": type(exc).__name__,
                            "retryable": isinstance(exc, AgentServiceError) and exc.retryable,
                        },
                    )
                    await repository.action(
                        lease,
                        "fail",
                        {
                            "retryable": isinstance(exc, AgentServiceError) and exc.retryable,
                            "error": {
                                "code": exc.code.value
                                if isinstance(exc, AgentServiceError)
                                else ErrorCode.INTERNAL_ERROR.value,
                                "message": "Durable extraction failed; inspect stage history.",
                                "retryable": isinstance(exc, AgentServiceError) and exc.retryable,
                            },
                        },
                    )
            except Exception:
                pass  # Loss of lease is not permission to write FAILED or ack.
        finally:
            renewal.cancel()
            with suppress(asyncio.CancelledError):
                await renewal
            self._tokens.pop(lease.run_id, None)
            current_run_lease.reset(context)
        return True

    async def _fail(
        self,
        run: AgentRun,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool = False,
    ) -> None:
        error = EventError(code=code.value, message=message, retryable=retryable)
        run.status = RunStatus.FAILED
        run.error = error
        await self._runs.save(run)
        await self._publisher.publish(
            run,
            EventType.RUN_FAILED,
            message=message,
            error=error,
        )
