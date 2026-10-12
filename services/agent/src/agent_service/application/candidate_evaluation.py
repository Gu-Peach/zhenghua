from __future__ import annotations

import asyncio
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from pydantic import Field

from ..domain.enums import (
    AgentStage,
    CorrectionAction,
    EvalCaseKind,
    EventType,
    ProfileCandidateStatus,
    RunStatus,
)
from ..domain.errors import AgentServiceError
from ..domain.models.common import StrictModel
from ..domain.models.correction import CorrectionEvidenceBundle, CorrectionPlan
from ..domain.models.extraction_stages import (
    CrossPageCompletionData,
    CrossPageCompletionRequest,
    DrawingPageInput,
    PageClassificationData,
    PageClassificationRequest,
    PageScanData,
    PageScanRequest,
)
from ..domain.models.improvement import EvalCaseResult, EvalReport, ProfileCandidate
from ..domain.models.profiles import ProfileBinding, ProfileManifest, ProfileRuleSet
from ..domain.models.runs import AgentRun, ProfileRef
from ..domain.models.stage_persistence import digest
from ..domain.ports import ArtifactRepository, CandidateRepository, EvalRepository, ResultDataRepository
from ..harness.eval_runner import EvalRunner
from ..harness.stores import CancellationToken
from ..infrastructure.correction_data import CorrectionDataRepository
from ..infrastructure.supabase_profile_packages import SupabaseProfilePackageRepository
from ..infrastructure.zh_vlm_stages import (
    _filter_schema,
    _normalize_classification,
    _normalize_cross_page,
    _normalize_page_scan,
)
from ..profiles import ProfileRegistry
from ..profiles.package import PackageManifest, build_package, safe_path, verify_package
from ..tools.extraction_runner import ScopedExtractionRunner
from .extraction_stage_dispatcher import ProfileBoundStageDispatcher
from .improvement_workflow import ImprovementWorkflow
from .run_control import RunEventPublisher
from .worker import RunExecutionOutcome


class EvaluationCase(StrictModel):
    case_id: str
    kind: EvalCaseKind
    stage: AgentStage
    expected: dict[str, Any]
    page: DrawingPageInput | None = None
    task_context: str = ""
    bundle: CorrectionEvidenceBundle | None = None
    fields: list[str] = Field(default_factory=list)


def projection(value: dict[str, Any]) -> dict[str, Any]:
    """Compare business fields, not model confidence/explanations or generated local IDs."""
    ignored = {
        "confidence",
        "reason",
        "source_note",
        "warnings",
        "task_id",
        "unit_id",
        "connection_id",
        "local_connection_id",
        "origin_pdf_page",
        "source_pages",
        "source_pdf_pages",
        "source_drawing_pages",
        "pdf_page_number",
        "unit_identity_confidence",
    }

    def clean(item: Any) -> Any:
        if isinstance(item, dict):
            return {key: clean(val) for key, val in item.items() if key not in ignored}
        if isinstance(item, list):
            return [clean(val) for val in item]
        return item

    return dict(clean(value))


def binding(root: Path, ref: ProfileRef) -> ProfileBinding:
    manifest = ProfileManifest.model_validate_json((root / "profile.json").read_text(encoding="utf-8"))
    resources = {key: root / safe_path(path) for key, path in manifest.resources.items()}
    return ProfileBinding(
        profile=ref,
        status=manifest.status,
        adapter=manifest.adapter,
        rules=ProfileRuleSet.model_validate_json(resources["routing_rules"].read_text(encoding="utf-8")),
        resolved_resources=resources,
    )


def fixed_cases(base: ProfileBinding) -> list[EvaluationCase]:
    """Freeze human expected JSON from the baseline package, never from candidate edits."""
    cases: list[EvaluationCase] = []
    classification = base.resource("classification_examples")
    manifest = json.loads((classification / "manifest.json").read_text(encoding="utf-8"))
    for case in manifest.get("cases", []):
        expected = classification / safe_path(case.get("expected") or f"{case['id']}/expected.json")
        image = classification / safe_path(case["images"][0]["path"])
        classified = PageClassificationData.model_validate(
            _filter_schema(
                PageClassificationData,
                _normalize_classification(json.loads(expected.read_text(encoding="utf-8"))),
            )
        )
        cases.append(
            EvaluationCase(
                case_id="fixed:classification:" + case["id"],
                kind=EvalCaseKind.PROTECTED,
                stage=AgentStage.PAGE_CLASSIFICATION,
                page=DrawingPageInput(pdf_page_number=1, image_path=image),
                expected=projection(classified.model_dump(mode="json")),
            )
        )
    wiring = base.resource("wiring_examples")
    manifest = json.loads((wiring / "manifest.json").read_text(encoding="utf-8"))
    # The versioned manifest image index also covers fixed positive/negative files
    # which are deliberately not selected as in-context examples.
    for path in sorted((wiring / "stage2").glob("*.expected.json")):
        image_name = path.name.split(".expected.json")[0]
        image_ref = manifest.get("images", {}).get(image_name)
        if not image_ref:
            raise ValueError("Fixed Stage 2 expected file has no explicit manifest image mapping.")
        scanned = PageScanData.model_validate(
            _filter_schema(
                PageScanData, _normalize_page_scan(json.loads(path.read_text(encoding="utf-8")), 1)
            )
        )
        cases.append(
            EvaluationCase(
                case_id="fixed:scan:" + image_name,
                kind=EvalCaseKind.NEGATIVE if not scanned.units else EvalCaseKind.PROTECTED,
                stage=AgentStage.PAGE_SCAN,
                page=DrawingPageInput(
                    pdf_page_number=scanned.pdf_page_number or 1, image_path=wiring / safe_path(image_ref)
                ),
                expected=projection(scanned.model_dump(mode="json")),
            )
        )
    for case in manifest.get("stage3_cases", []):
        context = json.loads((wiring / safe_path(case["input"])).read_text(encoding="utf-8"))
        completed = CrossPageCompletionData.model_validate(
            _filter_schema(
                CrossPageCompletionData,
                _normalize_cross_page(
                    json.loads((wiring / safe_path(case["expected"])).read_text(encoding="utf-8")), case["id"]
                ),
            )
        )
        images = [item for item in case["images"] if item.get("role") == "target_page"]
        if len(images) != 1:
            raise ValueError("Stage 3 regression requires exactly one declared target image.")
        cases.append(
            EvaluationCase(
                case_id="fixed:cross:" + case["id"],
                kind=EvalCaseKind.PROTECTED,
                stage=AgentStage.CROSS_PAGE_COMPLETION,
                page=DrawingPageInput(
                    pdf_page_number=context["target_pdf_page"],
                    image_path=wiring / safe_path(images[0]["path"]),
                ),
                task_context=json.dumps(context, ensure_ascii=False),
                expected=projection(completed.model_dump(mode="json")),
            )
        )
    if not cases or not any(case.kind == EvalCaseKind.NEGATIVE for case in cases):
        raise ValueError("Baseline package requires fixed positive and negative regression cases.")
    for case in cases:
        if not case.page or not case.page.image_path.is_file():
            raise ValueError("Fixed regression input image is missing.")
    return cases


class CandidateEvaluationExecutor:
    """Read-only re-extraction; no ResultProposal or business-result write is generated."""

    def __init__(
        self,
        *,
        profiles: ProfileRegistry,
        packages: SupabaseProfilePackageRepository | None,
        stages: ProfileBoundStageDispatcher,
        data: ResultDataRepository,
        correction_data: CorrectionDataRepository,
        artifacts: ArtifactRepository,
        candidates: CandidateRepository,
        evals: EvalRepository,
        workflow: ImprovementWorkflow,
        runtime_root: Path,
        allow_real_model: bool,
        publisher: RunEventPublisher | None = None,
    ) -> None:
        self.profiles, self.packages, self.stages, self.data = profiles, packages, stages, data
        self.correction_data, self.artifacts, self.candidates, self.evals = (
            correction_data,
            artifacts,
            candidates,
            evals,
        )
        self.workflow, self.root, self.allow_real = workflow, runtime_root, allow_real_model
        self.publisher = publisher

    async def _roots(self, candidate: ProfileCandidate) -> tuple[ProfileBinding, ProfileBinding]:
        if self.packages:
            base_root, _ = await self.packages.resolve(candidate.profile)
            candidate_root, manifest = await self.packages.candidate_package(candidate)
        else:
            snapshot = self.profiles.resolve(
                candidate.profile.key, candidate.profile.version, allow_experimental=True
            )
            if snapshot.checksum != candidate.profile.checksum:
                raise ValueError("Baseline Profile checksum changed.")
            base_root = self.root / "evaluation-inputs" / str(candidate.profile.checksum)[7:]
            if not base_root.exists():
                await asyncio.to_thread(build_package, snapshot, base_root)
            candidate_root = Path(candidate.sandbox_path)
            manifest = PackageManifest.model_validate_json(
                (candidate_root / "manifest.json").read_text(encoding="utf-8")
            )
            await asyncio.to_thread(verify_package, candidate_root, manifest)
        if manifest.source_profile_checksum != candidate.checksum:
            raise ValueError("Candidate manifest does not match its frozen content digest.")
        return binding(base_root, candidate.profile), binding(
            candidate_root,
            ProfileRef(
                key=manifest.profile_key, version=manifest.profile_version, checksum=manifest.package_checksum
            ),
        )

    async def _dataset(self, candidate: ProfileCandidate, base: ProfileBinding) -> list[EvaluationCase]:
        cases = await asyncio.to_thread(fixed_cases, base)
        fields_allowed = {
            "end_terminal",
            "end_code",
            "end_description",
            "current_value",
            "principle_number",
            "remark",
            "color_mark",
        }
        for feedback_id in candidate.source_feedback_ids:
            feedback = await self.data.get_accepted_feedback(feedback_id)
            if feedback.profile != candidate.profile:
                raise ValueError("Target feedback belongs to a different frozen Profile.")
            for connection_id in feedback.target.ids:
                bundle = await self.data.get_correction_bundle(connection_id)
                before = feedback.before.get(connection_id, feedback.before)
                after = feedback.after.get(connection_id, feedback.after)
                if not isinstance(before, dict) or not isinstance(after, dict):
                    raise ValueError("Target feedback lacks field-level before/after.")
                fields = sorted(
                    key for key in fields_allowed if key in after and before.get(key) != after[key]
                )
                if not fields:
                    raise ValueError("Target feedback has no measurable changed business field.")
                bundle.context.suggested_value = None
                bundle.context.observed_problem = "Re-read the specified connection from drawing evidence."
                bundle.context.evidence = {}
                bundle.context.constraints.allowed_fields = fields
                bundle.context.constraints.allowed_connection_ids = [connection_id]
                bundle.current_records = [
                    r for r in bundle.current_records if r.get("connection_id") == connection_id
                ]
                if len(bundle.current_records) != 1:
                    raise ValueError("Target case does not identify one frozen source connection.")
                original = bundle.current_records[0]
                expected = {
                    "start_terminal": after.get("start_terminal", original.get("start_terminal")),
                    **{key: after[key] for key in fields},
                }
                # Only source identity reaches re-extraction. Raw payload/notes can
                # otherwise leak an accepted destination through the Stage 3 context.
                bundle.current_records = [
                    {
                        key: value
                        for key, value in original.items()
                        if key.startswith("start_")
                        or key
                        in {
                            "start",
                            "connection_id",
                            "unit_id",
                            "wire_number",
                            "core_number",
                            "is_cross_page",
                        }
                    }
                ]
                bundle.context.instruction = "Evaluate from the images only; no corrected answer is supplied."
                bundle.page_scan_requests = [
                    req.model_copy(
                        update={"page_context": "Evaluation: identify the source connection from this image."}
                    )
                    for req in bundle.page_scan_requests
                ]
                bundle.cross_page_requests = []
                bundle.cross_page_task_targets = {}
                bundle.page_classification_requests = []
                bundle.unaffected_records = []
                cases.append(
                    EvaluationCase(
                        case_id=f"target:{feedback_id}:{connection_id}",
                        kind=EvalCaseKind.TARGET,
                        stage=AgentStage.CROSS_PAGE_COMPLETION
                        if bundle.facts.is_cross_page.value == "cross_page"
                        else AgentStage.PAGE_SCAN,
                        bundle=bundle,
                        fields=fields,
                        expected=expected,
                    )
                )
        if len({case.case_id for case in cases}) != len(cases):
            raise ValueError("Evaluation case IDs are not unique.")
        return cases

    async def _execute_case(
        self,
        case: EvaluationCase,
        profile: ProfileBinding,
        run: AgentRun,
        cancellation: CancellationToken | None = None,
    ) -> dict[str, Any]:
        req_id = f"{run.agent_run_id}:evaluation:{profile.profile.checksum}:{case.case_id}"
        common: dict[str, Any] = {"run_id": req_id, "project_id": run.project_id, "profile": profile}
        if case.bundle:
            bundle = case.bundle.model_copy(deep=True)
            bundle.profile = profile
            bundle.facts.feedback_id = req_id
            bundle.context.feedback_id = req_id
            bundle.page_scan_requests = [
                req.model_copy(update={"run_id": req_id, "profile": profile})
                for req in bundle.page_scan_requests
            ]
            bundle.available_pages = [
                await self.correction_data.materialize_page(page) for page in bundle.available_pages
            ]
            bundle.page_scan_requests = [
                req.model_copy(update={"page": await self.correction_data.materialize_page(req.page)})
                for req in bundle.page_scan_requests
            ]
            cross = case.stage == AgentStage.CROSS_PAGE_COMPLETION
            plan = CorrectionPlan(
                feedback_id=bundle.facts.feedback_id,
                target=bundle.facts.target,
                action=CorrectionAction.RERUN_STAGE_2_AND_3 if cross else CorrectionAction.RERUN_STAGE_2,
                allowed_fields=case.fields,
                estimated_model_calls=2 if cross else 1,
                reason="Frozen candidate evaluation",
            )
            records = await ScopedExtractionRunner(
                self.stages, materialize=self.correction_data.materialize_page
            ).run(plan, bundle, cancellation=cancellation)
            if len(records) != 1:
                raise ValueError("Target evaluation did not return exactly one scoped connection.")
            return {key: records[0].get(key) for key in case.expected}
        if case.page is None:
            raise ValueError("Regression input page missing.")
        result: PageClassificationData | PageScanData | CrossPageCompletionData
        if case.stage == AgentStage.PAGE_CLASSIFICATION:
            result = await self.stages.classify_page(PageClassificationRequest(**common, page=case.page))
        elif case.stage == AgentStage.PAGE_SCAN:
            result = await self.stages.scan_page(PageScanRequest(**common, page=case.page))
        else:
            result = await self.stages.resolve_cross_page(
                CrossPageCompletionRequest(
                    **common, task_id=case.case_id, target_page=case.page, task_context=case.task_context
                )
            )
        return projection(result.model_dump(mode="json"))

    async def execute(self, run: AgentRun, cancellation: CancellationToken) -> RunExecutionOutcome:
        if not self.allow_real or not run.options.real_evaluation_authorized:
            raise ValueError("Real candidate evaluation requires explicit server and request authorization.")
        candidate_id = run.options.profile_candidate_id
        if not candidate_id:
            raise ValueError("Candidate evaluation run lacks candidate_id.")
        candidate = await self.candidates.get(candidate_id)
        finished_id = f"{run.agent_run_id}:evaluation-report"
        finished = await self.artifacts.get(finished_id)
        if finished:
            passed = bool(finished["gate"]["passed"])
            return RunExecutionOutcome(
                status=RunStatus.NEEDS_REVIEW if passed else RunStatus.SUCCEEDED,
                artifact_ids=[finished_id],
                metrics={"candidate_id": candidate_id, "gate_passed": passed},
            )
        if candidate.status not in {
            ProfileCandidateStatus.DRAFT,
            ProfileCandidateStatus.EVALUATING,
            ProfileCandidateStatus.REJECTED,
        }:
            raise ValueError("Only draft/evaluating candidates can be evaluated.")
        base, proposed = await self._roots(candidate)
        if self.publisher:
            await self.publisher.publish(
                run,
                EventType.STAGE_STARTED,
                stage=AgentStage.EVALUATION,
                message="候选评测开始：冻结图片/人工 expected，对基线和候选分别运行。",
            )
        data_id = f"{run.agent_run_id}:evaluation-dataset"
        saved = await self.artifacts.get(data_id)
        if saved:
            if saved["candidate_checksum"] != proposed.profile.checksum or saved[
                "baseline_profile"
            ] != base.profile.model_dump(mode="json"):
                raise ValueError("Frozen evaluation inputs changed.")
            cases = [EvaluationCase.model_validate(c) for c in saved["cases"]]
        else:
            cases = await self._dataset(candidate, base)
            await self.artifacts.put(
                data_id,
                {
                    "artifact_id": data_id,
                    "agent_run_id": run.agent_run_id,
                    "kind": "evaluation_dataset",
                    "candidate_id": candidate_id,
                    "candidate_checksum": proposed.profile.checksum,
                    "baseline_profile": base.profile.model_dump(mode="json"),
                    "cases": [c.model_dump(mode="json") for c in cases],
                },
            )
        # Test images/expected never serve as the model's own few-shot answers.
        empty = self.root / "evaluation-inputs" / "no-fewshot"
        empty.mkdir(parents=True, exist_ok=True)
        (empty / "manifest.json").write_text(
            '{"cases":[],"stage2_cases":[],"stage3_cases":[]}', encoding="utf-8"
        )
        all_results: dict[str, list[EvalCaseResult]] = {"baseline": [], "candidate": []}
        for variant, bound in (("baseline", base), ("candidate", proposed)):
            resources = {
                **bound.resolved_resources,
                "classification_examples": empty,
                "wiring_examples": empty,
            }
            profile = bound.model_copy(update={"resolved_resources": resources})
            for case in cases:
                cancellation.raise_if_cancelled()
                item_id = f"{run.agent_run_id}:evaluation:{variant}:{case.case_id}"
                cached = await self.artifacts.get(item_id)
                if cached:
                    result = EvalCaseResult.model_validate(cached["result"])
                    if (
                        result.case_id != case.case_id
                        or result.kind != case.kind
                        or result.expected != case.expected
                    ):
                        raise ValueError("Cached evaluation result differs from the frozen case.")
                else:
                    started = perf_counter()
                    try:
                        actual = await self._execute_case(case, profile, run, cancellation)
                        result = EvalCaseResult(
                            case_id=case.case_id,
                            kind=case.kind,
                            expected=case.expected,
                            actual=actual,
                            duration_seconds=perf_counter() - started,
                        )
                    except AgentServiceError as exc:
                        if exc.retryable:
                            raise
                        result = EvalCaseResult(
                            case_id=case.case_id,
                            kind=case.kind,
                            expected=case.expected,
                            actual={},
                            schema_valid=False,
                            error=exc.code.value,
                            duration_seconds=perf_counter() - started,
                        )
                    cancellation.raise_if_cancelled()
                    await self.artifacts.put(
                        item_id,
                        {
                            "artifact_id": item_id,
                            "agent_run_id": run.agent_run_id,
                            "kind": "evaluation_case",
                            "candidate_id": candidate_id,
                            "variant": variant,
                            "stage": case.stage.value,
                            "result": result.model_dump(mode="json"),
                        },
                    )
                all_results[variant].append(result)
                if self.publisher:
                    await self.publisher.publish(
                        run,
                        EventType.ITEM_COMPLETED,
                        stage=AgentStage.EVALUATION,
                        message=f"{variant} / {case.case_id} 已保存字段级结果。",
                        metrics={
                            "variant": variant,
                            "case_id": case.case_id,
                            "passed": EvalRunner._passes(result),
                        },
                        artifact_refs=[item_id],
                    )
        report = EvalReport(
            eval_run_id=run.agent_run_id,
            candidate_id=candidate_id,
            baseline=EvalRunner.metrics(all_results["baseline"]),
            candidate=EvalRunner.metrics(all_results["candidate"]),
            baseline_results=all_results["baseline"],
            candidate_results=all_results["candidate"],
            candidate_checksum=proposed.profile.checksum,
            baseline_profile=base.profile,
            dataset_checksum=digest([c.model_dump(mode="json") for c in cases]),
            evaluated_stages=sorted({c.stage for c in cases}, key=lambda stage: stage.value),
        )
        try:
            persisted = await self.evals.get(run.agent_run_id)
        except KeyError:
            await self.evals.put(report)
        else:
            if (
                persisted.dataset_checksum != report.dataset_checksum
                or persisted.candidate_checksum != report.candidate_checksum
            ):
                raise ValueError("Persisted evaluation receipt differs from frozen inputs.")
            report = persisted
        evaluation = await self.workflow.evaluate(candidate_id, report)
        artifact_id = f"{run.agent_run_id}:evaluation-report"
        await self.artifacts.put(
            artifact_id,
            {
                "artifact_id": artifact_id,
                "agent_run_id": run.agent_run_id,
                "kind": "evaluation_report",
                "report": report.model_dump(mode="json"),
                "judgement": evaluation.judgement.model_dump(mode="json"),
                "gate": evaluation.gate.model_dump(mode="json"),
            },
        )
        if self.publisher:
            await self.publisher.publish(
                run,
                EventType.STAGE_COMPLETED,
                stage=AgentStage.EVALUATION,
                message="评测报告和门禁结果已持久化；等待人工审核。"
                if evaluation.gate.passed
                else "评测未通过，候选不得发布。",
                artifact_refs=[artifact_id],
            )
        return RunExecutionOutcome(
            status=RunStatus.NEEDS_REVIEW if evaluation.gate.passed else RunStatus.SUCCEEDED,
            artifact_ids=[artifact_id],
            metrics={
                "candidate_id": candidate_id,
                "gate_passed": evaluation.gate.passed,
                "evaluation_cases": len(cases),
                "human_review_required": evaluation.gate.passed,
            },
        )
