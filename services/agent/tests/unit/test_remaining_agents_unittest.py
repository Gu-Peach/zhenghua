from __future__ import annotations

import asyncio
import json
import tempfile
import threading
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agent_service.agents.supervisor import SupervisorAgent
from agent_service.application.correction_workflow import CorrectionWorkflowExecutor
from agent_service.application.extraction_stage_dispatcher import ProfileBoundStageDispatcher
from agent_service.application.run_control import RunControlService
from agent_service.application.worker import AgentWorker, RunExecutionOutcome
from agent_service.application.workflow_registry import WorkflowDispatchReceipt, WorkflowRegistry
from agent_service.config import AgentSettings
from agent_service.domain.enums import (
    AgentStage,
    EvalCaseKind,
    EventType,
    ProfileCandidateStatus,
    ProfileCandidateType,
    RootCauseCategory,
    RunStatus,
    RunType,
    ScopeType,
    SupervisorIntent,
    WorkflowKind,
)
from agent_service.domain.models.correction import (
    CorrectionConstraints,
    CorrectionContext,
    CorrectionEvidenceBundle,
    CorrectionFacts,
    FeedbackTarget,
)
from agent_service.domain.models.improvement import (
    AffectedScope,
    CandidatePatchOperation,
    Diagnosis,
    EvalCaseResult,
    EvalReport,
    ProfileCandidate,
)
from agent_service.domain.models.runs import AgentEvent, AgentRun, CreateRunRequest, ProfileRef, RunScope
from agent_service.domain.models.supervisor import ConversationTurn
from agent_service.graphs.supervisor import run_supervisor_graph
from agent_service.harness import (
    FakeModelGateway,
    InMemoryArtifactRepository,
    InMemoryCandidateRepository,
    InMemoryEventRepository,
    InMemoryProposalRepository,
    InMemoryRunRepository,
    ProfileSandbox,
    ReleaseGate,
)
from agent_service.harness.eval_runner import EvalRunner
from agent_service.infrastructure.correction_data import InMemoryCorrectionDataProvider
from agent_service.infrastructure.queue import InMemoryRunQueue
from agent_service.main import create_app
from agent_service.profiles import ProfileRegistry
from agent_service.tools.event_presenter import SupervisorEventPresenter
from agent_service.tools.extraction_runner import ScopedExtractionRunner

ROOT = Path(__file__).resolve().parents[4]


class SuccessfulExecutor:
    async def execute(self, run, cancellation):  # type: ignore[no-untyped-def]
        cancellation.raise_if_cancelled()
        return RunExecutionOutcome(status=RunStatus.SUCCEEDED, metrics={"done": True})


class BlockingExecutor:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    async def execute(self, run, cancellation):  # type: ignore[no-untyped-def]
        self.started.set()
        await asyncio.to_thread(self.release.wait, 5)
        cancellation.raise_if_cancelled()
        return RunExecutionOutcome(status=RunStatus.SUCCEEDED)


class CapturingHandler:
    async def dispatch(self, command):  # type: ignore[no-untyped-def]
        return WorkflowDispatchReceipt(
            command_id=command.command_id,
            workflow=command.workflow,
            status="QUEUED",
            agent_run_id="run-supervisor",
        )


def _create_request() -> CreateRunRequest:
    return CreateRunRequest(
        run_type=RunType.FULL_EXTRACTION,
        project_id="project-1",
        source_document_id="document-1",
        requested_by="user-1",
        profile_hint="zh",
        scope=RunScope(type=ScopeType.PROJECT, id="project-1"),
    )


class RemainingAgentsTests(unittest.TestCase):
    def test_run_control_is_idempotent_and_worker_emits_durable_events(self) -> None:
        async def run() -> None:
            runs = InMemoryRunRepository()
            events = InMemoryEventRepository()
            artifacts = InMemoryArtifactRepository()
            proposals = InMemoryProposalRepository()
            queue = InMemoryRunQueue()
            control = RunControlService(runs=runs, events=events, artifacts=artifacts, queue=queue)
            first = await control.create(_create_request(), "same-key")
            second = await control.create(_create_request(), "same-key")
            self.assertEqual(first.agent_run_id, second.agent_run_id)
            self.assertEqual(await queue.size(), 1)
            worker = AgentWorker(
                runs=runs,
                queue=queue,
                publisher=control.publisher,
                artifacts=artifacts,
                proposals=proposals,
            )
            worker.register(RunType.FULL_EXTRACTION, SuccessfulExecutor())
            self.assertTrue(await worker.run_once())
            saved = await runs.get(first.agent_run_id)
            self.assertIsNotNone(saved)
            self.assertEqual(saved.status, RunStatus.SUCCEEDED)  # type: ignore[union-attr]
            durable = await events.list_after(first.agent_run_id)
            self.assertEqual(
                [event.event_type for event in durable],
                [EventType.RUN_CREATED, EventType.RUN_STARTED, EventType.RUN_COMPLETED],
            )

        asyncio.run(run())

    def test_worker_cancel_race_preserves_cancelled_status(self) -> None:
        async def run() -> None:
            runs = InMemoryRunRepository()
            events = InMemoryEventRepository()
            artifacts = InMemoryArtifactRepository()
            proposals = InMemoryProposalRepository()
            queue = InMemoryRunQueue()
            control = RunControlService(runs=runs, events=events, artifacts=artifacts, queue=queue)
            saved = await control.create(_create_request(), "cancel-race")
            worker = AgentWorker(
                runs=runs,
                queue=queue,
                publisher=control.publisher,
                artifacts=artifacts,
                proposals=proposals,
            )
            executor = BlockingExecutor()
            worker.register(RunType.FULL_EXTRACTION, executor)
            task = asyncio.create_task(worker.run_once())
            await asyncio.to_thread(executor.started.wait, 2)
            await control.cancel(saved.agent_run_id)
            worker.cancel(saved.agent_run_id)
            executor.release.set()
            await task
            current = await runs.get(saved.agent_run_id)
            self.assertEqual(current.status, RunStatus.CANCELLED)  # type: ignore[union-attr]
            cancelled = [
                event
                for event in await events.list_after(saved.agent_run_id)
                if event.event_type == EventType.RUN_CANCELLED
            ]
            self.assertEqual(len(cancelled), 1)

        asyncio.run(run())

    def test_event_stream_replays_events_and_closes_for_completed_runs(self) -> None:
        settings = AgentSettings(
            workspace_root=ROOT,
            profile_root=ROOT / "services" / "agent" / "profiles",
            internal_token="stream-token",
        )
        app = create_app(settings=settings)
        run = _create_request()
        with TestClient(app) as client:
            created = client.post(
                "/v1/runs",
                json=run.model_dump(mode="json"),
                headers={"Idempotency-Key": "stream-key", "Authorization": "Bearer stream-token"},
            )
            run_id = created.json()["run"]["agent_run_id"]
            saved = asyncio.run(app.state.run_control.get_required(run_id))
            saved.status = RunStatus.SUCCEEDED
            asyncio.run(app.state.run_control.runs.save(saved))
            response = client.get(
                f"/v1/runs/{run_id}/events/stream",
                headers={"Authorization": "Bearer stream-token"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("event: RUN_CREATED", response.text)
            self.assertIn('"event_type":"RUN_CREATED"', response.text)

    def test_supervisor_graph_dispatches_only_registered_workflow(self) -> None:
        async def run() -> None:
            response = json.dumps(
                {
                    "intent": SupervisorIntent.PROCESS_DOCUMENT.value,
                    "confidence": 0.98,
                    "reason": "document request",
                    "requires_input": False,
                    "question": None,
                    "extracted_hints": {},
                }
            )
            agent = SupervisorAgent(
                gateway=FakeModelGateway([response]),
                prompt_path=ROOT / "services" / "agent" / "prompts" / "supervisor.md",
            )
            workflows = WorkflowRegistry()
            workflows.register(WorkflowKind.PROFILE_DETECTION, CapturingHandler())
            result = await run_supervisor_graph(
                agent=agent,
                workflows=workflows,
                turn=ConversationTurn(
                    conversation_id="conversation-1",
                    user_id="user-1",
                    message="process document",
                    attachment_ids=["document-1"],
                ),
            )
            self.assertEqual(result.decision.agent_run_id, "run-supervisor")
            self.assertEqual(result.user_event.agent_run_id, "run-supervisor")

        asyncio.run(run())

    def test_event_presenter_maps_failure_without_leaking_details(self) -> None:
        event = AgentEvent(
            agent_run_id="run-1",
            seq=1,
            event_type=EventType.STAGE_COMPLETED,
            stage=AgentStage.PAGE_SCAN,
            metrics={"processed": 2, "total": 3},
        )
        presented = SupervisorEventPresenter().present(event, conversation_id="conversation-1")
        self.assertIn("2/3", presented.user_message)

    def test_event_presenter_exposes_safe_improvement_diagnosis(self) -> None:
        event = AgentEvent(
            agent_run_id="run-1",
            seq=2,
            event_type=EventType.HUMAN_INPUT_REQUIRED,
            artifact_refs=["diagnosis-1"],
        )
        presented = SupervisorEventPresenter().present(
            event,
            conversation_id="conversation-1",
            artifact_payloads=[
                {
                    "kind": "improvement_diagnosis",
                    "feedback": {"before": {"secret": "raw-model-context"}},
                    "candidate_recommended": True,
                    "authorization_required": True,
                    "reason": "规则缺口可能重复出现。",
                    "diagnoses": [
                        {
                            "category": "PROMPT_RULE_GAP",
                            "confidence": 0.92,
                            "explanation": "跨页引用规则缺少该格式。",
                            "recommended_action": "补充 Stage 3 引用解析规则。",
                            "profile_candidate_required": True,
                            "evidence_ids": ["private-evidence"],
                        }
                    ],
                }
            ],
        )
        self.assertIn("跨页引用规则缺少该格式", presented.user_message)
        self.assertIn("请确认是否授权", presented.user_message)
        serialized = json.dumps(presented.payload, ensure_ascii=False)
        self.assertNotIn("raw-model-context", serialized)
        self.assertNotIn("private-evidence", serialized)
        self.assertIn("PROMPT_RULE_GAP", serialized)

    def test_event_presenter_marks_profile_candidate_as_unpublished(self) -> None:
        event = AgentEvent(
            agent_run_id="run-1",
            seq=3,
            event_type=EventType.HUMAN_INPUT_REQUIRED,
            artifact_refs=["candidate-1"],
        )
        presented = SupervisorEventPresenter().present(
            event,
            conversation_id="conversation-1",
            artifact_payloads=[
                {
                    "kind": "profile_candidate",
                    "candidate": {
                        "candidate_id": "candidate-1",
                        "summary": "补充跨页规则",
                        "operations": [{"content": "private-prompt-patch"}],
                    },
                    "reason": "authorized",
                }
            ],
        )
        self.assertIn("生产 Profile 未被修改", presented.user_message)
        serialized = json.dumps(presented.payload, ensure_ascii=False)
        self.assertNotIn("private-prompt-patch", serialized)
        self.assertIn("candidate-1", serialized)

    def test_supervisor_event_api_resolves_and_sanitizes_diagnosis_artifact(self) -> None:
        settings = AgentSettings(
            workspace_root=ROOT,
            profile_root=ROOT / "services" / "agent" / "profiles",
            internal_token="event-token",
        )
        app = create_app(settings=settings)
        headers = {"Authorization": "Bearer event-token"}
        with TestClient(app) as client:
            created = client.post(
                "/v1/runs",
                json=_create_request().model_dump(mode="json"),
                headers={**headers, "Idempotency-Key": "diagnosis-event"},
            )
            run_id = created.json()["run"]["agent_run_id"]
            artifact_id = f"{run_id}:diagnosis"
            asyncio.run(
                app.state.run_control.artifacts.put(
                    artifact_id,
                    {
                        "artifact_id": artifact_id,
                        "agent_run_id": run_id,
                        "kind": "improvement_diagnosis",
                        "feedback": {"raw": "private-feedback"},
                        "candidate_recommended": True,
                        "authorization_required": True,
                        "reason": "规则问题",
                        "diagnoses": [
                            {
                                "category": "PROMPT_RULE_GAP",
                                "confidence": 0.9,
                                "explanation": "缺少端子格式规则。",
                                "recommended_action": "补充规则并运行回归。",
                                "profile_candidate_required": True,
                            }
                        ],
                    },
                )
            )
            run = asyncio.run(app.state.run_control.get_required(run_id))
            asyncio.run(
                app.state.run_control.publisher.publish(
                    run,
                    EventType.HUMAN_INPUT_REQUIRED,
                    message="authorization required",
                    artifact_refs=[artifact_id],
                )
            )
            response = client.get(
                f"/v1/supervisor/runs/{run_id}/events",
                params={"conversation_id": "conversation-1"},
                headers=headers,
            )
            self.assertEqual(response.status_code, 200)
            event = response.json()["items"][-1]
            self.assertIn("缺少端子格式规则", event["user_message"])
            self.assertNotIn("private-feedback", json.dumps(event, ensure_ascii=False))

    def test_direct_correction_builds_scoped_patch_without_vlm(self) -> None:
        async def run() -> None:
            registry = ProfileRegistry(
                profile_root=ROOT / "services" / "agent" / "profiles",
                workspace_root=ROOT,
                allow_legacy_references=True,
            )
            registry.load_all()
            bundle = CorrectionEvidenceBundle(
                facts=CorrectionFacts(
                    feedback_id="feedback-1",
                    target=FeedbackTarget(
                        type=ScopeType.CONNECTION,
                        id="connection-1",
                        field="end_terminal",
                        project_id="project-1",
                        result_version_id="result-version-1",
                    ),
                    issue_kind="DIRECT_VALUE_CHANGE",
                    suggested_value_present=True,
                ),
                context=CorrectionContext(
                    feedback_id="feedback-1",
                    field="end_terminal",
                    observed_problem="wrong terminal",
                    suggested_value="FC103:2",
                    constraints=CorrectionConstraints(
                        allowed_connection_ids=["connection-1"],
                        allowed_fields=["end_terminal"],
                    ),
                ),
                profile=registry.bind("zh"),
                base_result_version=3,
                current_records=[
                    {
                        "connection_id": "connection-1",
                        "start": {"terminal": "1"},
                        "end_terminal": "FC103:3",
                    }
                ],
                record_versions={"connection-1": 7},
                evidence_ids=["evidence-1"],
            )
            data = InMemoryCorrectionDataProvider()
            await data.register(bundle)
            executor = CorrectionWorkflowExecutor(
                data=data,
                stages=ScopedExtractionRunner(ProfileBoundStageDispatcher()),
                model_name="fake-vlm",
            )
            request = CreateRunRequest(
                run_type=RunType.SCOPED_CORRECTION,
                project_id="project-1",
                source_document_id="document-1",
                feedback_id="feedback-1",
                requested_by="user-1",
                expected_result_version=3,
                scope=RunScope(type=ScopeType.CONNECTION, id="connection-1"),
            )
            outcome = await executor.execute(
                AgentRun.from_request(request, "correction-key"),
                cancellation=__import__(
                    "agent_service.harness.stores", fromlist=["CancellationToken"]
                ).CancellationToken(),
            )
            self.assertEqual(len(outcome.proposal.operations), 1)  # type: ignore[union-attr]
            operation = outcome.proposal.operations[0]  # type: ignore[union-attr]
            self.assertEqual(operation.after["end_terminal"], "FC103:2")  # type: ignore[index]
            self.assertEqual(operation.expected_version, 7)

        asyncio.run(run())

    def test_eval_gate_and_candidate_lifecycle_require_human_approval(self) -> None:
        async def run() -> None:
            results = [
                EvalCaseResult(
                    case_id="case-1",
                    kind=EvalCaseKind.TARGET,
                    expected={"end": "2"},
                    actual={"end": "2"},
                    duration_seconds=1.0,
                ),
                EvalCaseResult(
                    case_id="case-2",
                    kind=EvalCaseKind.PROTECTED,
                    expected={"end": "3"},
                    actual={"end": "3"},
                    duration_seconds=1.0,
                ),
            ]
            metrics = EvalRunner.metrics(results)
            report = EvalReport(
                candidate_id="candidate-1",
                baseline=metrics,
                candidate=metrics,
                baseline_results=results,
                candidate_results=results,
            )
            self.assertTrue(ReleaseGate().evaluate(report).passed)
            repository = InMemoryCandidateRepository()
            candidate = ProfileCandidate(
                candidate_id="candidate-1",
                profile=ProfileRef(key="zh", version="1.0.0"),
                candidate_type=ProfileCandidateType.PROMPT_PATCH,
                summary="candidate",
                operations=[
                    CandidatePatchOperation(
                        op="replace",
                        relative_path="rules.md",
                        content="new",
                        reason="test",
                    )
                ],
                source_feedback_ids=["feedback-1"],
                diagnoses=[
                    Diagnosis(
                        category=RootCauseCategory.PROMPT_RULE_GAP,
                        confidence=0.9,
                        affected_stage=[AgentStage.PAGE_SCAN],
                        affected_scope=AffectedScope(type=ScopeType.CONNECTION, ids=["connection-1"]),
                        explanation="gap",
                        recommended_action="patch",
                    )
                ],
                sandbox_path="sandbox",
                checksum="sha256:test",
            )
            await repository.put(candidate)
            await repository.transition("candidate-1", ProfileCandidateStatus.EVALUATING)
            with self.assertRaises(ValueError):
                await repository.transition("candidate-1", ProfileCandidateStatus.APPROVED)
            await repository.transition(
                "candidate-1",
                ProfileCandidateStatus.APPROVED,
                reviewer_id="reviewer-1",
            )

        asyncio.run(run())

    def test_profile_sandbox_rejects_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "rules.md").write_text("old", encoding="utf-8")
            sandbox = ProfileSandbox(root / "sandboxes")
            target = sandbox.create(candidate_id="candidate-1", source_profile=source)
            checksum = sandbox.apply(
                target,
                [
                    CandidatePatchOperation(
                        op="replace",
                        relative_path="rules.md",
                        content="new",
                        reason="test",
                    )
                ],
            )
            self.assertTrue(checksum.startswith("sha256:"))
            with self.assertRaises(ValueError):
                sandbox.apply(
                    target,
                    [
                        CandidatePatchOperation(
                            op="replace",
                            relative_path="../outside.md",
                            content="bad",
                            reason="test",
                        )
                    ],
                )

    def test_run_api_requires_internal_token_when_configured(self) -> None:
        settings = AgentSettings(
            workspace_root=ROOT,
            profile_root=ROOT / "services" / "agent" / "profiles",
            internal_token="secret-token",
        )
        with TestClient(create_app(settings=settings)) as client:
            payload = _create_request().model_dump(mode="json")
            unauthorized = client.post("/v1/runs", json=payload, headers={"Idempotency-Key": "key-1"})
            self.assertEqual(unauthorized.status_code, 401)
            accepted = client.post(
                "/v1/runs",
                json=payload,
                headers={
                    "Idempotency-Key": "key-1",
                    "Authorization": "Bearer secret-token",
                },
            )
            self.assertEqual(accepted.status_code, 202)


if __name__ == "__main__":
    unittest.main()
