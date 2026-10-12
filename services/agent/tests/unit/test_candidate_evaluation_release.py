from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from agent_service.agents.evaluation_judge import EvaluationJudgeAgent
from agent_service.application.candidate_evaluation import (
    CandidateEvaluationExecutor,
    EvaluationCase,
    binding,
    fixed_cases,
)
from agent_service.application.candidate_release import CandidateReleaseService
from agent_service.application.improvement_workflow import ImprovementWorkflow
from agent_service.domain.enums import AgentStage, EvalCaseKind, ProfileCandidateStatus, RunStatus, RunType
from agent_service.domain.models.correction import CorrectionEvidenceBundle
from agent_service.domain.models.improvement import (
    AcceptedFeedback,
    EvalCaseResult,
    EvalReport,
    ProfileCandidate,
)
from agent_service.domain.models.runs import CreateRunRequest, RunOptions, RunScope
from agent_service.domain.models.stage_persistence import digest
from agent_service.harness import (
    FakeModelGateway,
    InMemoryArtifactRepository,
    InMemoryCandidateRepository,
    InMemoryEvalRepository,
    ProfileSandbox,
)
from agent_service.harness.eval_runner import EvalRunner
from agent_service.harness.release_gate import ReleaseGate
from agent_service.harness.stores import CancellationToken
from agent_service.profiles.package import build_package
from agent_service.profiles.registry import ProfileRegistry

ROOT = Path(__file__).resolve().parents[4]


def report(checksum: str = "checksum") -> EvalReport:
    results = [
        EvalCaseResult(case_id=str(kind), kind=kind, expected={"value": "ok"}, actual={"value": "ok"})
        for kind in (EvalCaseKind.TARGET, EvalCaseKind.PROTECTED, EvalCaseKind.NEGATIVE)
    ]
    return EvalReport(
        eval_run_id="eval-1",
        candidate_id="candidate-1",
        baseline=EvalRunner.metrics(results),
        candidate=EvalRunner.metrics(results),
        baseline_results=results,
        candidate_results=results,
        candidate_checksum=checksum,
        baseline_profile={"key": "zh", "version": "1.0.0"},
        dataset_checksum="dataset",
        evaluated_stages=sorted(
            [
                AgentStage.PAGE_CLASSIFICATION,
                AgentStage.PAGE_SCAN,
                AgentStage.CROSS_PAGE_COMPLETION,
            ]
        ),
    )


def test_gate_rejects_empty_forged_and_incomplete_reports() -> None:
    valid = report()
    assert ReleaseGate().evaluate(valid).passed
    assert not ReleaseGate().evaluate(valid.model_copy(update={"candidate_results": []})).passed
    assert (
        not ReleaseGate()
        .evaluate(valid.model_copy(update={"evaluated_stages": [AgentStage.PAGE_SCAN]}))
        .passed
    )
    bad = valid.candidate.model_copy(update={"field_precision": 0.01})
    assert not ReleaseGate().evaluate(valid.model_copy(update={"candidate": bad})).passed


def test_frozen_fixed_dataset_covers_three_stages_and_negative(tmp_path: Path) -> None:
    registry = ProfileRegistry(
        profile_root=ROOT / "services/agent/profiles", workspace_root=ROOT, allow_legacy_references=True
    )
    registry.load_all()
    snapshot = registry.resolve("zh")
    root = tmp_path / "package"
    build_package(snapshot, root)
    base = binding(root, registry.bind("zh").profile)
    cases = fixed_cases(base)
    assert len(cases) == 7
    assert {case.stage for case in cases} == {
        AgentStage.PAGE_CLASSIFICATION,
        AgentStage.PAGE_SCAN,
        AgentStage.CROSS_PAGE_COMPLETION,
    }
    assert sum(case.kind == EvalCaseKind.NEGATIVE for case in cases) == 1
    assert all(case.page and case.page.image_path.is_file() for case in cases)


def test_real_evaluation_requires_server_and_request_consent(tmp_path: Path) -> None:
    async def run() -> None:
        candidates = Mock()
        executor = CandidateEvaluationExecutor(
            profiles=Mock(),
            packages=None,
            stages=Mock(),
            data=Mock(),
            correction_data=Mock(),
            artifacts=Mock(),
            candidates=candidates,
            evals=Mock(),
            workflow=Mock(),
            runtime_root=tmp_path,
            allow_real_model=False,
        )
        request = CreateRunRequest(
            run_type=RunType.PROFILE_EVALUATION,
            project_id="p",
            source_document_id="d",
            requested_by="u",
            scope=RunScope(type="PROFILE", id="zh"),
            options=RunOptions(profile_candidate_id="c", real_evaluation_authorized=True),
        )
        from agent_service.domain.models.runs import AgentRun

        with pytest.raises(ValueError, match="authorization"):
            await executor.execute(AgentRun.from_request(request, "key"), CancellationToken())
        candidates.get.assert_not_called()

    asyncio.run(run())


@pytest.mark.parametrize("cross_page", [False, True], ids=["same-page", "cross-page"])
@pytest.mark.parametrize("nested_start", [False, True], ids=["flat-start", "nested-start"])
def test_target_start_is_passed_without_expected_answers(
    tmp_path: Path, cross_page: bool, nested_start: bool
) -> None:
    async def run() -> None:
        registry = ProfileRegistry(
            profile_root=ROOT / "services/agent/profiles", workspace_root=ROOT, allow_legacy_references=True
        )
        registry.load_all()
        package = tmp_path / "base"
        build_package(registry.resolve("zh"), package)
        bound = binding(package, registry.bind("zh").profile)
        page = {
            "pdf_page_number": 1,
            "image_path": str(package / "resources/classification_examples/006m01_identity/page_006m01.png"),
        }
        bundle = CorrectionEvidenceBundle(
            facts={
                "feedback_id": "f",
                "target": {"type": "CONNECTION", "id": "c1", "project_id": "p", "result_version_id": "v"},
                "issue_kind": "DIRECT_VALUE_CHANGE",
                "is_cross_page": "cross_page" if cross_page else "same_page",
            },
            context={
                "feedback_id": "f",
                "observed_problem": "Expected X3:1",
                "suggested_value": "X3:1",
                "constraints": {},
            },
            profile=bound,
            base_result_version=1,
            current_records=[
                {
                    "connection_id": "c1",
                    **(
                        {"start": {"location": "+SRC", "device": "XD3", "terminal": "114"}}
                        if nested_start
                        else {"start_location": "+SRC", "start_device": "XD3", "start_terminal": "XD3:113"}
                    ),
                    "end_terminal": "X3:1",
                    "end": {"terminal": "X3:1"},
                    "source_note": "expected X3:1",
                    "raw_payload": {"correct_answer": "X3:1"},
                }
            ],
            evidence_ids=["e"],
            page_scan_requests=[
                {
                    "run_id": "r",
                    "project_id": "p",
                    "profile": bound,
                    "page": page,
                    "page_context": "answer X3:1",
                }
            ],
        )
        feedback = AcceptedFeedback(
            feedback_id="f",
            project_id="p",
            accepted=True,
            result_version_id="v",
            profile=bound.profile,
            model_name="fake",
            target={"type": "CONNECTION", "ids": ["c1"]},
            before={"c1": {"end_terminal": "999"}},
            after={"c1": {"end_terminal": "X3:1"}},
            evidence_ids=["e"],
            stage_artifact_ids=["a"],
            prompt_checksum="checksum",
        )
        data = AsyncMock()
        data.get_accepted_feedback.return_value = feedback
        data.get_correction_bundle.return_value = bundle
        candidate = Mock(profile=bound.profile, source_feedback_ids=["f"])
        executor = CandidateEvaluationExecutor(
            profiles=registry,
            packages=None,
            stages=Mock(),
            data=data,
            correction_data=Mock(),
            artifacts=Mock(),
            candidates=Mock(),
            evals=Mock(),
            workflow=Mock(),
            runtime_root=tmp_path,
            allow_real_model=True,
        )
        cases = await executor._dataset(candidate, bound)
        target = next(case for case in cases if case.kind == EvalCaseKind.TARGET)
        assert target.expected["end_terminal"] == "X3:1"
        assert "X3:1" not in target.bundle.context.model_dump_json()
        assert "X3:1" not in json.dumps(target.bundle.current_records)
        page_context = target.bundle.page_scan_requests[0].page_context
        assert "X3:1" not in page_context
        locating = json.loads(page_context)["target_connection"]
        assert locating["connection_id"] == "c1"
        assert "end" not in locating and "end_terminal" not in locating
        assert "raw_payload" not in locating and "source_note" not in locating
        if nested_start:
            assert locating["start"] == {"location": "+SRC", "device": "XD3", "terminal": "114"}
        else:
            assert locating["start_location"] == "+SRC"
            assert locating["start_device"] == "XD3"
            assert locating["start_terminal"] == "XD3:113"
        from agent_service.domain.models.extraction_stages import CrossPageCompletionData, PageScanData
        from agent_service.domain.models.runs import AgentRun

        stages = AsyncMock()
        stages.scan_page.return_value = PageScanData.model_validate(
            {
                "units": [
                    {
                        "unit_id": "u1",
                        "connections": [
                            {
                                "local_connection_id": "local",
                                "start": {
                                    "location": "+SRC",
                                    "device": "XD3",
                                    "terminal": "114" if nested_start else "XD3:113",
                                },
                                "end": None if cross_page else {"terminal": "X3:1"},
                                "is_cross_page": "cross_page" if cross_page else "same_page",
                                "references": [{"target_pdf_page": 2}] if cross_page else [],
                            }
                        ],
                    }
                ]
            }
        )
        stages.resolve_cross_page.return_value = CrossPageCompletionData.model_validate(
            {
                "end": {"terminal": "X3:1"},
                "status": "complete",
            }
        )
        executor.stages = stages
        executor.correction_data = AsyncMock()
        executor.correction_data.materialize_page.side_effect = lambda page: page
        target.bundle.available_pages = [
            target.bundle.page_scan_requests[0].page.model_copy(update={"pdf_page_number": 2})
        ]
        agent_run = AgentRun.from_request(
            CreateRunRequest(
                run_type="PROFILE_EVALUATION",
                project_id="p",
                source_document_id="d",
                requested_by="u",
                scope={"type": "PROFILE", "id": "zh"},
            ),
            "key",
        )
        actual = await executor._execute_case(target, bound, agent_run, CancellationToken())
        assert actual == target.expected
        assert stages.scan_page.await_count == 1
        scan_request = stages.scan_page.call_args.args[0]
        assert "X3:1" not in scan_request.page_context
        wrapped = json.loads(scan_request.page_context)
        assert json.loads(wrapped["original_context"])["target_connection"] == locating
        assert scan_request.run_id.startswith(agent_run.agent_run_id + ":evaluation:")
        assert stages.resolve_cross_page.await_count == int(cross_page)
        if cross_page:
            cross_request = stages.resolve_cross_page.call_args.args[0]
            assert "X3:1" not in cross_request.task_context
            assert cross_request.run_id.startswith(agent_run.agent_run_id + ":evaluation:")

        # Also inspect the final multimodal messages, not just the stage DTO.
        from agent_service.application.extraction_stage_dispatcher import ProfileBoundStageDispatcher
        from agent_service.config import AgentSettings
        from agent_service.infrastructure.zh_vlm_stages import ZhVlmExtractionStageAdapter

        responses = [stages.scan_page.return_value.model_dump_json()]
        if cross_page:
            responses.append(stages.resolve_cross_page.return_value.model_dump_json())
        gateway = FakeModelGateway(responses)
        dispatcher = ProfileBoundStageDispatcher()
        dispatcher.register("zh_native", ZhVlmExtractionStageAdapter(AgentSettings(), gateway))
        executor.stages = dispatcher
        model_bound = bound.model_copy(
            update={
                "resolved_resources": {
                    **bound.resolved_resources,
                    "classification_examples": tmp_path / "no-fewshot",
                    "wiring_examples": tmp_path / "no-fewshot",
                }
            }
        )
        assert await executor._execute_case(target, model_bound, agent_run) == target.expected
        assert len(gateway.calls) == 1 + int(cross_page)
        assert all(len(request.messages) == 2 for request in gateway.calls)
        user_content = gateway.calls[0].messages[-1]["content"]
        assert user_content[0]["type"] == "text"
        user_text = user_content[0]["text"]
        assert "target_connection" in user_text
        assert ("114" if nested_start else "XD3:113") in user_text
        assert "+SRC" in user_text and "XD3" in user_text
        assert "X3:1" not in user_text and "999" not in user_text
        assert any(part["type"] == "image_url" for part in user_content)
        if cross_page:
            assert "X3:1" not in gateway.calls[1].messages[-1]["content"][0]["text"]

    asyncio.run(run())


def test_worker_persists_results_and_resume_skips_model_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Sub-millisecond mocks otherwise randomly trip the latency-ratio gate.
    from itertools import count

    ticks = count()
    monkeypatch.setattr(
        "agent_service.application.candidate_evaluation.perf_counter", lambda: float(next(ticks))
    )

    async def run() -> None:
        candidates = InMemoryCandidateRepository()
        candidate = ProfileCandidate(
            candidate_id="candidate-1",
            profile={"key": "zh", "version": "1.0.0"},
            candidate_type="PROMPT_PATCH",
            summary="fix",
            operations=[],
            source_feedback_ids=["f"],
            diagnoses=[
                {
                    "category": "PROMPT_RULE_GAP",
                    "confidence": 1,
                    "affected_stage": ["PAGE_SCAN"],
                    "affected_scope": {"type": "CONNECTION", "ids": ["c1"]},
                    "explanation": "rule",
                    "recommended_action": "fix",
                    "profile_candidate_required": True,
                }
            ],
            sandbox_path=str(tmp_path),
            checksum="content",
            resource_package_checksum="checksum",
        )
        await candidates.put(candidate)
        artifacts, evals = InMemoryArtifactRepository(), InMemoryEvalRepository()
        judge = EvaluationJudgeAgent(
            gateway=FakeModelGateway([json.dumps({"recommendation": "APPROVE", "summary": "通过固定回归"})]),
            prompt_path=ROOT / "services/agent/prompts/evaluation_judge.md",
        )
        workflow = ImprovementWorkflow(
            profiles=Mock(),
            diagnoser=Mock(),
            patch_builder=Mock(),
            judge=judge,
            sandbox=ProfileSandbox(tmp_path),
            candidates=candidates,
        )
        bound = Mock()
        bound.profile = candidate.profile
        bound.resolved_resources = {}
        proposed = Mock()
        proposed.profile = candidate.profile.model_copy(update={"checksum": "checksum"})
        proposed.resolved_resources = {}
        cases = [
            EvaluationCase(case_id=str(kind), kind=kind, stage=stage, expected={"value": "ok"})
            for kind, stage in zip(
                (EvalCaseKind.TARGET, EvalCaseKind.PROTECTED, EvalCaseKind.NEGATIVE),
                (AgentStage.PAGE_CLASSIFICATION, AgentStage.PAGE_SCAN, AgentStage.CROSS_PAGE_COMPLETION),
                strict=True,
            )
        ]
        executor = CandidateEvaluationExecutor(
            profiles=Mock(),
            packages=None,
            stages=Mock(),
            data=Mock(),
            correction_data=Mock(),
            artifacts=artifacts,
            candidates=candidates,
            evals=evals,
            workflow=workflow,
            runtime_root=tmp_path,
            allow_real_model=True,
        )
        executor._roots = AsyncMock(return_value=(bound, proposed))
        executor._dataset = AsyncMock(return_value=cases)
        executor._execute_case = AsyncMock(return_value={"value": "ok"})
        from agent_service.domain.models.runs import AgentRun

        request = CreateRunRequest(
            run_type="PROFILE_EVALUATION",
            project_id="p",
            source_document_id="d",
            requested_by="u",
            scope={"type": "PROFILE", "id": "zh"},
            options={"profile_candidate_id": "candidate-1", "real_evaluation_authorized": True},
        )
        agent_run = AgentRun.from_request(request, "key")
        result = await executor.execute(agent_run, CancellationToken())
        assert result.status == RunStatus.NEEDS_REVIEW
        assert executor._execute_case.await_count == 6
        await executor.execute(agent_run, CancellationToken())
        assert executor._execute_case.await_count == 6
        assert (await evals.get(agent_run.agent_run_id)).dataset_checksum
        saved = await artifacts.get(f"{agent_run.agent_run_id}:evaluation-report")
        assert saved and saved["gate"]["passed"]
        packages = AsyncMock()
        packages.client.select.side_effect = lambda table, params: (
            [{"id": "pkg", "base_package_id": "base"}] if "id" in params else [{"id": "base"}]
        )
        workflow._packages = packages
        stored = await candidates.get("candidate-1")
        stored.resource_package_id = "pkg"
        await candidates.put(stored)
        runs = AsyncMock()
        runs.get_required.return_value = agent_run
        release = CandidateReleaseService(
            candidates=candidates,
            evals=evals,
            artifacts=artifacts,
            runs=runs,
            data=Mock(),
            workflow=workflow,
            allow_real_model=True,
        )
        with pytest.raises(ValueError, match="explicit"):
            await release.approve("candidate-1", agent_run.agent_run_id, "u", False)
        reviewed = await release.approve("candidate-1", agent_run.agent_run_id, "u", True)
        assert reviewed.status == ProfileCandidateStatus.CANARY
        packages.client.rpc.assert_not_called()
        with pytest.raises(ValueError, match="separate"):
            await release.publish("candidate-1", agent_run.agent_run_id, "u", False)
        packages.client.rpc.side_effect = [ConnectionError("interrupted publish"), None, None]
        with pytest.raises(ConnectionError):
            await release.publish("candidate-1", agent_run.agent_run_id, "u", True)
        active = await release.publish("candidate-1", agent_run.agent_run_id, "u", True)
        assert active.status == ProfileCandidateStatus.ACTIVE
        await release.publish("candidate-1", agent_run.agent_run_id, "u", True)
        assert executor._execute_case.await_count == 6
        assert packages.load_registry.await_count == 2
        packages.client.select.side_effect = lambda *args, **kwargs: [{"id": "unrelated"}]
        with pytest.raises(ValueError, match="changed"):
            await release.publish("candidate-1", agent_run.agent_run_id, "u", True)

    asyncio.run(run())


def test_review_publication_receipt_checks_scope_checksum_and_confirmation() -> None:
    async def run() -> None:
        candidates, evals, artifacts, runs = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
        expected = report()
        cases = [
            {
                "case_id": result.case_id,
                "kind": result.kind.value,
                "expected": result.expected,
                "stage": stage.value,
            }
            for result, stage in zip(expected.candidate_results, expected.evaluated_stages, strict=True)
        ]
        expected.dataset_checksum = digest(cases)
        candidate = Mock()
        candidate.resource_package_checksum = "checksum"
        candidate.profile = expected.baseline_profile
        candidates.get.return_value = candidate
        candidates.gate_passed.return_value = True
        run = Mock(
            requested_by="reviewer",
            run_type=RunType.PROFILE_EVALUATION,
            options=Mock(profile_candidate_id="candidate-1"),
        )
        runs.get_required.return_value = run
        evals.get.return_value = expected
        artifacts.get.side_effect = lambda key: (
            {"cases": cases}
            if key.endswith("evaluation-dataset")
            else {"report": expected.model_dump(mode="json"), "gate": {"passed": True}}
        )
        workflow = AsyncMock()
        service = CandidateReleaseService(
            candidates=candidates,
            evals=evals,
            artifacts=artifacts,
            runs=runs,
            data=Mock(),
            workflow=workflow,
            allow_real_model=True,
        )
        with pytest.raises(ValueError, match="explicit"):
            await service.approve("candidate-1", "eval-1", "reviewer", False)
        await service.receipt("candidate-1", "eval-1", "reviewer")
        with pytest.raises(PermissionError):
            await service.receipt("candidate-1", "eval-1", "outsider")
        candidate.resource_package_checksum = "changed"
        with pytest.raises(ValueError, match="different"):
            await service.receipt("candidate-1", "eval-1", "reviewer")
        workflow.activate_canary.assert_not_called()

    asyncio.run(run())


def test_native_fixed_cases_execute_with_fake_gateway_and_no_fewshot(tmp_path: Path) -> None:
    from agent_service.application.extraction_stage_dispatcher import ProfileBoundStageDispatcher
    from agent_service.config import AgentSettings
    from agent_service.domain.models.runs import AgentRun
    from agent_service.infrastructure.zh_vlm_stages import ZhVlmExtractionStageAdapter

    async def run() -> None:
        registry = ProfileRegistry(
            profile_root=ROOT / "services/agent/profiles", workspace_root=ROOT, allow_legacy_references=True
        )
        registry.load_all()
        package = tmp_path / "base"
        build_package(registry.resolve("zh"), package)
        bound = binding(package, registry.bind("zh").profile)
        cases = fixed_cases(bound)
        empty = tmp_path / "no-fewshot"
        empty.mkdir()
        (empty / "manifest.json").write_text(
            '{"cases":[],"stage2_cases":[],"stage3_cases":[]}', encoding="utf-8"
        )
        bound.resolved_resources.update(classification_examples=empty, wiring_examples=empty)
        gateway = FakeModelGateway([json.dumps(case.expected) for case in cases])
        dispatcher = ProfileBoundStageDispatcher()
        dispatcher.register("zh_native", ZhVlmExtractionStageAdapter(AgentSettings(), gateway))
        executor = CandidateEvaluationExecutor(
            profiles=registry,
            packages=None,
            stages=dispatcher,
            data=Mock(),
            correction_data=Mock(),
            artifacts=Mock(),
            candidates=Mock(),
            evals=Mock(),
            workflow=Mock(),
            runtime_root=tmp_path,
            allow_real_model=True,
        )
        agent_run = AgentRun.from_request(
            CreateRunRequest(
                run_type="PROFILE_EVALUATION",
                project_id="p",
                source_document_id="d",
                requested_by="u",
                scope={"type": "PROFILE", "id": "zh"},
            ),
            "key",
        )
        for case in cases:
            actual = await executor._execute_case(case, bound, agent_run)
            assert actual == case.expected, case.case_id
        assert len(gateway.calls) == 7
        assert all(len(request.messages) == 2 for request in gateway.calls)

    asyncio.run(run())
