from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from agent_service.agents.evaluation_judge import EvaluationJudgeAgent
from agent_service.agents.improvement_diagnoser import ImprovementDiagnoserAgent
from agent_service.agents.profile_patch_builder import ProfilePatchBuilderAgent
from agent_service.agents.supervisor import SupervisorAgent
from agent_service.application.correction_workflow import CorrectionWorkflowExecutor
from agent_service.application.extraction_stage_dispatcher import ProfileBoundStageDispatcher
from agent_service.application.improvement_run_executor import ImprovementRunExecutor
from agent_service.application.improvement_workflow import ImprovementWorkflow
from agent_service.application.run_control import RunControlService
from agent_service.application.supervisor_handlers import register_default_supervisor_handlers
from agent_service.application.worker import AgentWorker
from agent_service.application.workflow_registry import WorkflowRegistry
from agent_service.domain.enums import (
    CorrectionIssueKind,
    CrossPageState,
    EvalCaseKind,
    EventType,
    RunStatus,
    RunType,
    ScopeType,
    SupervisorIntent,
)
from agent_service.domain.models.correction import (
    CorrectionConstraints,
    CorrectionContext,
    CorrectionEvidenceBundle,
    CorrectionFacts,
    FeedbackTarget,
)
from agent_service.domain.models.improvement import EvalCaseResult, EvalReport
from agent_service.domain.models.result_data import ConnectionSearchResult
from agent_service.domain.models.supervisor import ConversationTurn, SupervisorTargetHint
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
from agent_service.infrastructure.result_data import InMemoryResultDataRepository
from agent_service.profiles import ProfileRegistry
from agent_service.tools.extraction_runner import ScopedExtractionRunner
from agent_service.tools.result_data import ControlledResultDataTool

ROOT = Path(__file__).resolve().parents[4]


class SupervisorAgentChainTests(unittest.TestCase):
    def test_direct_patch_confirmation_runs_diagnosis_then_authorized_candidate(self) -> None:
        async def run() -> None:
            registry = ProfileRegistry(
                profile_root=ROOT / "services" / "agent" / "profiles",
                workspace_root=ROOT,
                allow_legacy_references=True,
            )
            registry.load_all()
            binding = registry.bind("zh")
            bundle = CorrectionEvidenceBundle(
                facts=CorrectionFacts(
                    feedback_id="template-feedback",
                    target=FeedbackTarget(
                        type=ScopeType.CONNECTION,
                        id="connection-1",
                        field="end_terminal",
                        project_id="project-1",
                        result_version_id="project-1:v3",
                    ),
                    issue_kind=CorrectionIssueKind.RECOGNITION_ERROR,
                    is_cross_page=CrossPageState.CROSS_PAGE,
                    affected_drawing_ids=["drawing-1"],
                    target_drawing_ids=["drawing-2"],
                ),
                context=CorrectionContext(
                    feedback_id="template-feedback",
                    field="end_terminal",
                    observed_problem="终点端子错误",
                    constraints=CorrectionConstraints(
                        allowed_connection_ids=["connection-1"],
                        allowed_fields=["end_terminal"],
                    ),
                ),
                profile=binding,
                base_result_version=3,
                current_records=[
                    {
                        "connection_id": "connection-1",
                        "start": {"terminal": "XD21:7"},
                        "end_terminal": "X21:1",
                        "is_cross_page": "cross_page",
                    }
                ],
                record_versions={"connection-1": 4},
                evidence_ids=["evidence-1"],
            )
            result_repository = InMemoryResultDataRepository()
            await result_repository.register(
                ConnectionSearchResult(
                    connection_id="connection-1",
                    project_id="project-1",
                    project_name="测试项目",
                    workspace_id="workspace-1",
                    workspace_name="电气房",
                    workspace_page="006M01",
                    result_version_id="project-1:v3",
                    result_version=3,
                    record_version=4,
                    source_document_id="document-1",
                    wire_number="1000",
                    terminal_strip="X21",
                    start_terminal="XD21:7",
                    end_terminal="X21:1",
                    is_cross_page=CrossPageState.CROSS_PAGE,
                ),
                bundle,
            )
            runs = InMemoryRunRepository()
            events = InMemoryEventRepository()
            artifacts = InMemoryArtifactRepository()
            proposals = InMemoryProposalRepository()
            queue = InMemoryRunQueue()
            control = RunControlService(runs=runs, events=events, artifacts=artifacts, queue=queue)
            correction_data = InMemoryCorrectionDataProvider()
            result_tool = ControlledResultDataTool(
                repository=result_repository,
                correction_data=correction_data,
            )
            worker = AgentWorker(
                runs=runs,
                queue=queue,
                publisher=control.publisher,
                artifacts=artifacts,
                proposals=proposals,
            )
            worker.register(
                RunType.SCOPED_CORRECTION,
                CorrectionWorkflowExecutor(
                    data=correction_data,
                    stages=ScopedExtractionRunner(ProfileBoundStageDispatcher()),
                    model_name="fake-vlm",
                ),
            )
            supervisor_gateway = FakeModelGateway(
                [
                    json.dumps(
                        {
                            "intent": SupervisorIntent.CORRECT_RESULT.value,
                            "confidence": 0.99,
                            "reason": "用户给出了明确端子答案",
                            "requires_input": False,
                            "question": None,
                            "extracted_hints": {"suggested_value": "X21:2"},
                        }
                    ),
                    json.dumps(
                        {
                            "intent": SupervisorIntent.CONFIRM_RESULT_PATCH.value,
                            "confidence": 0.99,
                            "reason": "用户确认结果 diff",
                            "requires_input": False,
                            "question": None,
                            "extracted_hints": {},
                        }
                    ),
                    json.dumps(
                        {
                            "intent": SupervisorIntent.AUTHORIZE_PROFILE_CANDIDATE.value,
                            "confidence": 0.99,
                            "reason": "用户授权创建规则候选",
                            "requires_input": False,
                            "question": None,
                            "extracted_hints": {},
                        }
                    ),
                ]
            )
            supervisor = SupervisorAgent(
                gateway=supervisor_gateway,
                prompt_path=ROOT / "services" / "agent" / "prompts" / "supervisor.md",
            )
            improvement_gateway = FakeModelGateway(
                [
                    json.dumps(
                        {
                            "category": "PROMPT_RULE_GAP",
                            "confidence": 0.92,
                            "affected_stage": ["PAGE_SCAN"],
                            "affected_scope": {
                                "type": "CONNECTION",
                                "ids": ["connection-1"],
                            },
                            "evidence_ids": ["evidence-1"],
                            "explanation": "Stage 2 对该端子模式缺少明确规则。",
                            "recommended_action": "补充端子模式规则和回归案例。",
                            "profile_candidate_required": True,
                            "needs_human_input": False,
                        }
                    ),
                    json.dumps(
                        {
                            "candidate_type": "PROMPT_PATCH",
                            "summary": "补充端子识别规则",
                            "operations": [
                                {
                                    "op": "replace",
                                    "relative_path": "rules.json",
                                    "content": '{"candidate": true}',
                                    "reason": "覆盖已确认的端子模式",
                                }
                            ],
                            "expected_benefit": "减少同类端子误识别",
                            "risks": ["需要保护既有案例"],
                        }
                    ),
                    json.dumps(
                        {
                            "recommendation": "APPROVE",
                            "summary": "目标与保护案例均通过。",
                            "improvements": ["目标端子修复"],
                            "regressions": [],
                            "risks": [],
                            "requires_human_review": True,
                        }
                    ),
                ]
            )
            with tempfile.TemporaryDirectory() as temporary:
                candidates = InMemoryCandidateRepository()
                improvement = ImprovementWorkflow(
                    profiles=registry,
                    diagnoser=ImprovementDiagnoserAgent(
                        gateway=improvement_gateway,
                        prompt_path=ROOT / "services" / "agent" / "prompts" / "improvement_diagnosis.md",
                    ),
                    patch_builder=ProfilePatchBuilderAgent(
                        gateway=improvement_gateway,
                        prompt_path=ROOT / "services" / "agent" / "prompts" / "profile_patch_builder.md",
                    ),
                    judge=EvaluationJudgeAgent(
                        gateway=improvement_gateway,
                        prompt_path=ROOT / "services" / "agent" / "prompts" / "evaluation_judge.md",
                    ),
                    sandbox=ProfileSandbox(Path(temporary) / "sandbox"),
                    candidates=candidates,
                    release_gate=ReleaseGate(),
                )
                worker.register(
                    RunType.IMPROVEMENT_CANDIDATE,
                    ImprovementRunExecutor(
                        result_data=result_repository,
                        workflow=improvement,
                        artifacts=artifacts,
                    ),
                )
                workflows = WorkflowRegistry()
                register_default_supervisor_handlers(
                    workflows,
                    control,
                    registry,
                    result_tool,
                    proposals,
                )

                correction_turn = ConversationTurn(
                    conversation_id="conversation-1",
                    user_id="user-1",
                    project_id="project-1",
                    message="把连接终点改成 X21:2",
                    target_hint=SupervisorTargetHint(
                        connection_id="connection-1",
                        result_version_id="project-1:v3",
                        field="end_terminal",
                    ),
                )
                correction_result = await run_supervisor_graph(
                    agent=supervisor,
                    workflows=workflows,
                    turn=correction_turn,
                )
                self.assertIsNotNone(correction_result.receipt)
                self.assertTrue(await worker.run_once())
                correction_run_id = correction_result.receipt.agent_run_id  # type: ignore[union-attr]
                correction_run = await runs.get(correction_run_id)  # type: ignore[arg-type]
                self.assertEqual(correction_run.status, RunStatus.NEEDS_REVIEW)  # type: ignore[union-attr]
                proposal_id = f"{correction_run_id}:result-proposal"
                proposal = await proposals.get(proposal_id)
                self.assertEqual(proposal.operations[0].after["end_terminal"], "X21:2")  # type: ignore[union-attr,index]

                commit_result = await run_supervisor_graph(
                    agent=supervisor,
                    workflows=workflows,
                    turn=ConversationTurn(
                        conversation_id="conversation-1",
                        user_id="user-1",
                        project_id="project-1",
                        message="确认提交这个修改",
                        target_hint=SupervisorTargetHint(proposal_id=proposal_id),
                    ),
                )
                improvement_run_id = commit_result.receipt.agent_run_id  # type: ignore[union-attr]
                self.assertEqual(commit_result.receipt.payload["result_version"], 4)  # type: ignore[union-attr]
                self.assertTrue(await worker.run_once())
                improvement_run = await runs.get(improvement_run_id)  # type: ignore[arg-type]
                self.assertEqual(improvement_run.status, RunStatus.WAITING_INPUT)  # type: ignore[union-attr]
                diagnosis_artifacts = await artifacts.list_for_run(improvement_run_id)  # type: ignore[arg-type]
                diagnosis = next(
                    item for item in diagnosis_artifacts if item.get("kind") == "improvement_diagnosis"
                )
                self.assertTrue(diagnosis["candidate_recommended"])

                await run_supervisor_graph(
                    agent=supervisor,
                    workflows=workflows,
                    turn=ConversationTurn(
                        conversation_id="conversation-1",
                        user_id="reviewer-1",
                        project_id="project-1",
                        message="确认创建规则候选",
                        target_hint=SupervisorTargetHint(agent_run_id=improvement_run_id),
                    ),
                )
                self.assertTrue(await worker.run_once())
                candidate_artifacts = await artifacts.list_for_run(improvement_run_id)  # type: ignore[arg-type]
                candidate_payload = next(
                    item for item in candidate_artifacts if item.get("kind") == "profile_candidate"
                )
                candidate_id = candidate_payload["candidate"]["candidate_id"]
                candidate = await candidates.get(candidate_id)
                self.assertEqual(candidate.status.value, "DRAFT")

                results = [
                    EvalCaseResult(
                        case_id="case-1",
                        kind=EvalCaseKind.TARGET,
                        expected={"end_terminal": "X21:2"},
                        actual={"end_terminal": "X21:2"},
                    )
                ]
                report = EvalReport(
                    candidate_id=candidate_id,
                    baseline=EvalRunner.metrics(results),
                    candidate=EvalRunner.metrics(results),
                    baseline_results=results,
                    candidate_results=results,
                )
                evaluated = await improvement.evaluate(candidate_id, report)
                self.assertTrue(evaluated.gate.passed)
                self.assertEqual(evaluated.judgement.recommendation.value, "APPROVE")
                run_events = await events.list_after(improvement_run_id)  # type: ignore[arg-type]
                self.assertTrue(
                    any(event.event_type == EventType.HUMAN_INPUT_REQUIRED for event in run_events)
                )

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
