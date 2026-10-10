from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from ..agents.evaluation_judge import EvaluationJudgeAgent
from ..agents.improvement_diagnoser import ImprovementDiagnoserAgent
from ..agents.profile_patch_builder import ProfilePatchBuilderAgent
from ..domain.enums import EvalCaseKind, ProfileCandidateStatus
from ..domain.models.improvement import (
    AcceptedFeedback,
    Diagnosis,
    EvalReport,
    EvaluationJudgement,
    ImprovementCase,
    ProfileCandidate,
    ReleaseDecision,
)
from ..domain.ports import CandidateRepository
from ..harness.profile_sandbox import ProfileSandbox
from ..harness.release_gate import ReleaseGate
from ..profiles import ProfileRegistry
from ..tools.improvement_intake import ImprovementIntake


@dataclass(frozen=True, slots=True)
class ImprovementPreparation:
    regression_cases: list[ImprovementCase]
    diagnoses: list[Diagnosis]
    candidate: ProfileCandidate | None
    reason: str
    candidate_recommended: bool = False
    authorization_required: bool = False


@dataclass(frozen=True, slots=True)
class ImprovementEvaluation:
    report: EvalReport
    judgement: EvaluationJudgement
    gate: ReleaseDecision
    candidate: ProfileCandidate


class ImprovementWorkflow:
    def __init__(
        self,
        *,
        profiles: ProfileRegistry,
        diagnoser: ImprovementDiagnoserAgent,
        patch_builder: ProfilePatchBuilderAgent,
        judge: EvaluationJudgeAgent,
        sandbox: ProfileSandbox,
        candidates: CandidateRepository,
        release_gate: ReleaseGate | None = None,
    ) -> None:
        self._profiles = profiles
        self._diagnoser = diagnoser
        self._patch_builder = patch_builder
        self._judge = judge
        self._sandbox = sandbox
        self._candidates = candidates
        self._gate = release_gate or ReleaseGate()
        self._intake = ImprovementIntake()

    async def diagnose(self, feedback: list[AcceptedFeedback]) -> ImprovementPreparation:
        if not feedback:
            raise ValueError("Improvement preparation requires accepted feedback.")
        profile_keys = {(item.profile.key, item.profile.version) for item in feedback}
        if len(profile_keys) != 1:
            raise ValueError("One improvement candidate cannot mix Profile versions.")
        diagnoses: list[Diagnosis] = []
        cases: list[ImprovementCase] = []
        for item in feedback:
            self._intake.validate(item)
            diagnosis = await self._diagnoser.diagnose(item)
            diagnoses.append(diagnosis)
            cases.append(
                ImprovementCase(
                    kind=EvalCaseKind.TARGET,
                    profile=item.profile,
                    input_refs=list(item.evidence_ids),
                    expected=dict(item.after),
                    source_feedback_ids=[item.feedback_id],
                )
            )
        pairs = list(zip(feedback, diagnoses, strict=True))
        groups = self._candidate_groups(pairs)
        if not groups:
            return ImprovementPreparation(
                regression_cases=cases,
                diagnoses=diagnoses,
                candidate=None,
                reason="单个低严重度案例只进入回归集，尚未达到候选生成阈值。",
            )
        return ImprovementPreparation(
            regression_cases=cases,
            diagnoses=diagnoses,
            candidate=None,
            reason="已识别可能的规则问题；创建 Profile 候选前需要用户明确确认。",
            candidate_recommended=True,
            authorization_required=True,
        )

    async def prepare(self, feedback: list[AcceptedFeedback]) -> ImprovementPreparation:
        """Diagnose accepted feedback without modifying a Profile sandbox."""

        return await self.diagnose(feedback)

    async def build_candidate(
        self,
        *,
        feedback: list[AcceptedFeedback],
        diagnoses: list[Diagnosis],
        authorized_by: str,
    ) -> ImprovementPreparation:
        if not authorized_by.strip():
            raise ValueError("Profile candidate creation requires explicit user authorization.")
        if len(feedback) != len(diagnoses):
            raise ValueError("Feedback and diagnoses must align before candidate creation.")
        pairs = list(zip(feedback, diagnoses, strict=True))
        groups = self._candidate_groups(pairs)
        if not groups:
            raise ValueError("Diagnosed feedback does not meet the candidate creation threshold.")
        cases = [
            ImprovementCase(
                kind=EvalCaseKind.TARGET,
                profile=item.profile,
                input_refs=list(item.evidence_ids),
                expected=dict(item.after),
                source_feedback_ids=[item.feedback_id],
            )
            for item in feedback
        ]
        selected = groups[0]
        selected_feedback = [item for item, _ in selected]
        selected_diagnoses = [item for _, item in selected]
        patch = await self._patch_builder.build(
            feedback=selected_feedback,
            diagnoses=selected_diagnoses,
        )
        profile = selected_feedback[0].profile
        snapshot = self._profiles.resolve(profile.key, profile.version, allow_experimental=True)
        candidate_id = str(uuid4())
        sandbox_path = self._sandbox.create(
            candidate_id=candidate_id,
            source_profile=snapshot.profile_root,
        )
        checksum = self._sandbox.apply(sandbox_path, patch.operations)
        candidate = ProfileCandidate(
            candidate_id=candidate_id,
            profile=profile,
            candidate_type=patch.candidate_type,
            summary=patch.summary,
            operations=patch.operations,
            source_feedback_ids=[item.feedback_id for item in selected_feedback],
            diagnoses=selected_diagnoses,
            sandbox_path=str(sandbox_path),
            checksum=checksum,
        )
        await self._candidates.put(candidate)
        return ImprovementPreparation(
            regression_cases=cases,
            diagnoses=diagnoses,
            candidate=candidate,
            reason=(f"用户 {authorized_by} 已授权；候选已写入隔离 Profile 沙箱，尚未评测或发布。"),
            candidate_recommended=True,
            authorization_required=False,
        )

    async def evaluate(self, candidate_id: str, report: EvalReport) -> ImprovementEvaluation:
        if report.candidate_id != candidate_id:
            raise ValueError("Evaluation report candidate_id does not match the target candidate.")
        candidate = await self._candidates.transition(
            candidate_id,
            ProfileCandidateStatus.EVALUATING,
        )
        judgement = await self._judge.judge(report)
        gate = self._gate.evaluate(report)
        await self._candidates.record_gate(candidate_id, gate)
        if not gate.passed:
            candidate = await self._candidates.transition(
                candidate_id,
                ProfileCandidateStatus.REJECTED,
            )
        return ImprovementEvaluation(
            report=report,
            judgement=judgement,
            gate=gate,
            candidate=candidate,
        )

    async def approve(self, candidate_id: str, reviewer_id: str) -> ProfileCandidate:
        if not await self._candidates.gate_passed(candidate_id):
            raise ValueError("Candidate cannot be approved before passing the deterministic gate.")
        candidate = await self._candidates.transition(
            candidate_id,
            ProfileCandidateStatus.APPROVED,
            reviewer_id=reviewer_id,
        )
        return await self._candidates.transition(
            candidate.candidate_id,
            ProfileCandidateStatus.CANARY,
            reviewer_id=reviewer_id,
        )

    async def activate_canary(self, candidate_id: str) -> ProfileCandidate:
        return await self._candidates.transition(candidate_id, ProfileCandidateStatus.ACTIVE)

    async def assess_canary(
        self,
        candidate_id: str,
        *,
        severe_regressions: int,
        reviewer_id: str,
    ) -> ProfileCandidate:
        if severe_regressions > 0:
            return await self.rollback(candidate_id, reviewer_id)
        return await self.activate_canary(candidate_id)

    async def reject(self, candidate_id: str) -> ProfileCandidate:
        candidate = await self._candidates.get(candidate_id)
        if candidate.status == ProfileCandidateStatus.DRAFT:
            return await self._candidates.transition(candidate_id, ProfileCandidateStatus.REJECTED)
        if candidate.status == ProfileCandidateStatus.EVALUATING:
            return await self._candidates.transition(candidate_id, ProfileCandidateStatus.REJECTED)
        raise ValueError("Only draft or evaluating candidates can be rejected.")

    async def rollback(self, candidate_id: str, reviewer_id: str) -> ProfileCandidate:
        return await self._candidates.rollback(candidate_id, reviewer_id)

    def _candidate_groups(
        self,
        pairs: list[tuple[AcceptedFeedback, Diagnosis]],
    ) -> list[list[tuple[AcceptedFeedback, Diagnosis]]]:
        groups = self._intake.candidate_groups(pairs)
        if groups:
            return groups
        if any(diagnosis.profile_candidate_required for _, diagnosis in pairs):
            return [pairs]
        return []


def default_sandbox_root(workspace_root: Path) -> Path:
    return workspace_root / "services" / "agent" / ".profile-sandbox"
