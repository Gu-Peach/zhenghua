from __future__ import annotations

from pathlib import Path

from src.domain.enums import ProfileCandidateStatus, RunType, ScopeType
from src.domain.models.improvement import EvalReport, ProfileCandidate
from src.domain.models.runs import AgentRun, CreateRunRequest, RunOptions, RunScope
from src.domain.models.stage_persistence import digest
from src.domain.ports import ArtifactRepository, CandidateRepository, EvalRepository, ResultDataRepository
from src.harness.release_gate import ReleaseGate
from src.profiles.package import PackageManifest, verify_package
from src.application.improvement_workflow import ImprovementWorkflow
from src.application.run_control import RunControlService


class CandidateReleaseService:
    """Server-owned evaluation receipts, explicit review and explicit package publication."""

    def __init__(
        self,
        *,
        candidates: CandidateRepository,
        evals: EvalRepository,
        artifacts: ArtifactRepository,
        runs: RunControlService,
        data: ResultDataRepository,
        workflow: ImprovementWorkflow,
        allow_real_model: bool,
    ) -> None:
        self.candidates, self.evals, self.artifacts, self.runs = candidates, evals, artifacts, runs
        self.data, self.workflow, self.allow_real = data, workflow, allow_real_model

    async def start(self, candidate_id: str, reviewer_id: str, authorized: bool) -> AgentRun:
        if not self.allow_real or not authorized:
            raise ValueError("Set AGENT_ALLOW_REAL_EVALUATION=true and explicitly authorize real evaluation.")
        candidate = await self.candidates.get(candidate_id)
        if candidate.status not in {ProfileCandidateStatus.DRAFT, ProfileCandidateStatus.EVALUATING}:
            raise ValueError("Candidate is not draft/evaluating; do not rebuild an accepted correction.")
        if not candidate.source_feedback_ids:
            raise ValueError("Candidate has no accepted feedback provenance.")
        feedback = await self.data.get_accepted_feedback(candidate.source_feedback_ids[0])
        if not feedback.correction_run_id:
            raise ValueError("Candidate feedback lacks its source correction run.")
        source = await self.runs.get_required(feedback.correction_run_id)
        if source.requested_by != reviewer_id:
            raise PermissionError("Only the source feedback owner may start this evaluation.")
        return await self.runs.create(
            CreateRunRequest(
                run_type=RunType.PROFILE_EVALUATION,
                project_id=feedback.project_id,
                source_document_id=source.source_document_id,
                requested_by=reviewer_id,
                profile=candidate.profile,
                profile_hint=candidate.profile.key,
                scope=RunScope(type=ScopeType.PROFILE, id=candidate.profile.key),
                options=RunOptions(profile_candidate_id=candidate_id, real_evaluation_authorized=True),
            ),
            "candidate-evaluation:"
            + candidate_id
            + ":"
            + (candidate.resource_package_checksum or candidate.checksum),
        )

    async def confirm(self, candidate_id: str, reviewer_id: str, confirmed: bool) -> ProfileCandidate:
        """Explicit, provenance-authorized publication with no evaluation receipt."""
        if not confirmed:
            raise ValueError("Rule modification requires explicit human confirmation.")
        candidate = await self.candidates.get(candidate_id)
        if not candidate.source_feedback_ids:
            raise ValueError("Candidate has no accepted feedback provenance.")
        for key in candidate.source_feedback_ids:
            feedback = await self.data.get_accepted_feedback(key)
            if not feedback.correction_run_id:
                raise ValueError("Candidate feedback lacks its source correction run.")
            source = await self.runs.get_required(feedback.correction_run_id)
            if source.requested_by != reviewer_id:
                raise PermissionError("Only the source feedback owner may confirm rule modification.")
        return await self.workflow.publish_confirmed(candidate_id, reviewer_id)

    async def receipt(self, candidate_id: str, run_id: str, reviewer_id: str) -> EvalReport:
        run = await self.runs.get_required(run_id)
        if run.requested_by != reviewer_id:
            raise PermissionError("Evaluation receipt belongs to another reviewer.")
        if run.run_type != RunType.PROFILE_EVALUATION or run.options.profile_candidate_id != candidate_id:
            raise ValueError("Evaluation run is outside the candidate scope.")
        artifact = await self.artifacts.get(f"{run_id}:evaluation-report")
        if artifact is None:
            raise ValueError("Evaluation has not completed; no reviewable report exists.")
        report = await self.evals.get(run_id)
        if report.eval_run_id != run_id or report.candidate_id != candidate_id:
            raise ValueError("Evaluation report identity differs from the requested receipt.")
        if report.model_dump(mode="json") != artifact["report"]:
            raise ValueError("Evaluation report receipt differs from the persisted Worker artifact.")
        dataset = await self.artifacts.get(f"{run_id}:evaluation-dataset")
        if dataset is None or report.dataset_checksum != digest(dataset["cases"]):
            raise ValueError("Evaluation dataset receipt is missing or changed.")
        cases = dataset["cases"]
        if report.evaluated_stages != sorted({case["stage"] for case in cases}):
            raise ValueError("Evaluation stage coverage differs from the frozen dataset.")
        for results in (report.baseline_results, report.candidate_results):
            if len(results) != len(cases) or any(
                result.case_id != case["case_id"]
                or result.kind != case["kind"]
                or result.expected != case["expected"]
                for result, case in zip(results, cases, strict=True)
            ):
                raise ValueError("Evaluation results do not match the frozen dataset.")
        candidate = await self.candidates.get(candidate_id)
        checksum = candidate.resource_package_checksum
        if not checksum:
            root = Path(candidate.sandbox_path)
            manifest = PackageManifest.model_validate_json(
                (root / "manifest.json").read_text(encoding="utf-8")
            )
            verify_package(root, manifest)
            if manifest.source_profile_checksum != candidate.checksum:
                raise ValueError("Local candidate package checksum changed.")
            checksum = manifest.package_checksum
        if report.candidate_checksum != checksum or report.baseline_profile != candidate.profile:
            raise ValueError("Evaluation report is bound to a different candidate package/Profile.")
        if not artifact["gate"]["passed"] or not ReleaseGate().evaluate(report).passed:
            raise ValueError("The server-generated evaluation gate did not pass.")
        if not await self.candidates.gate_passed(candidate_id):
            raise ValueError("Candidate has no persisted passing release gate.")
        return report

    async def approve(
        self, candidate_id: str, run_id: str, reviewer_id: str, confirmed: bool
    ) -> ProfileCandidate:
        if not confirmed:
            raise ValueError(
                "Human review requires explicit confirmation after reading the evaluation report."
            )
        await self.receipt(candidate_id, run_id, reviewer_id)
        candidate = await self.candidates.get(candidate_id)
        if candidate.status in {ProfileCandidateStatus.CANARY, ProfileCandidateStatus.ACTIVE}:
            audit = await self.candidates.audit_log(candidate_id)
            if not any(item.get("reviewer_id") == reviewer_id for item in audit):
                raise PermissionError("Reviewer does not match the audited approval.")
            return candidate
        return await self.workflow.approve(candidate_id, reviewer_id)

    async def publish(
        self, candidate_id: str, run_id: str, reviewer_id: str, confirmed: bool
    ) -> ProfileCandidate:
        if not confirmed:
            raise ValueError("Publishing requires a separate explicit human confirmation.")
        await self.receipt(candidate_id, run_id, reviewer_id)
        candidate = await self.candidates.get(candidate_id)
        if candidate.status not in {ProfileCandidateStatus.CANARY, ProfileCandidateStatus.ACTIVE}:
            raise ValueError("Candidate must first be approved by a human reviewer.")
        audit = await self.candidates.audit_log(candidate_id)
        if not any(item.get("reviewer_id") == reviewer_id for item in audit):
            raise PermissionError("Publication reviewer does not match the audited approval.")
        return await self.workflow.activate_canary(candidate_id)
