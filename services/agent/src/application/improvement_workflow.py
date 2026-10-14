from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from src.agents.evaluation_judge import EvaluationJudgeAgent
from src.agents.improvement_diagnoser import ImprovementDiagnoserAgent
from src.agents.profile_patch_builder import ProfilePatchBuilderAgent
from src.domain.enums import EvalCaseKind, ProfileCandidateStatus, ProfileStatus
from src.domain.models.improvement import (
    AcceptedFeedback,
    Diagnosis,
    EvalReport,
    EvaluationJudgement,
    ImprovementCase,
    ProfileCandidate,
    ReleaseDecision,
)
from src.domain.models.profiles import ProfileManifest, ProfileSnapshot
from src.domain.ports import CandidateRepository
from src.harness.profile_sandbox import ProfileSandbox
from src.harness.release_gate import ReleaseGate
from src.infrastructure.supabase_profile_packages import SupabaseProfilePackageRepository
from src.profiles import ProfileRegistry
from src.profiles.package import PackageManifest, build_package, safe_path, seal_package, verify_package
from src.tools.improvement_intake import ImprovementIntake


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
        profile_packages: SupabaseProfilePackageRepository | None = None,
    ) -> None:
        self._profiles = profiles
        self._diagnoser = diagnoser
        self._patch_builder = patch_builder
        self._judge = judge
        self._sandbox = sandbox
        self._candidates = candidates
        self._gate = release_gate or ReleaseGate()
        self._intake = ImprovementIntake()
        self._packages = profile_packages

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
            if self._packages:
                root, manifest = await self._packages.resolve(item.profile)
                item.context["package_checksum"] = manifest.package_checksum
            else:
                snapshot = self._profiles.resolve(
                    item.profile.key, item.profile.version, allow_experimental=True
                )
                if snapshot.checksum != item.profile.checksum:
                    raise ValueError("Improvement Profile checksum no longer matches feedback.")
                root = self._sandbox.root / "inputs" / snapshot.checksum[7:]
                if not root.exists():
                    await asyncio.to_thread(build_package, snapshot, root)
            item.context["profile_files"] = {
                path.relative_to(root).as_posix(): await asyncio.to_thread(path.read_text, encoding="utf-8")
                for path in root.rglob("*")
                if path.is_file() and path.suffix in {".md", ".json", ".txt"}
            }
            item.context["profile_root"] = str(root)
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
        candidate_id: str | None = None,
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
        candidate_id = candidate_id or str(uuid4())
        try:
            existing = await self._candidates.get(candidate_id)
        except KeyError:
            existing = None
        if existing is not None:
            if (
                existing.source_feedback_ids != [item.feedback_id for item in selected_feedback]
                or existing.profile != selected_feedback[0].profile
            ):
                raise ValueError("Candidate retry differs from its frozen feedback.")
            if self._packages:
                source_root, _ = await self._packages.resolve(existing.profile)
                await self._packages.upload(
                    Path(existing.sandbox_path),
                    created_by=authorized_by,
                    candidate_id=candidate_id,
                    base_package_id=source_root.name,
                )
            return ImprovementPreparation(
                regression_cases=cases,
                diagnoses=diagnoses,
                candidate=existing,
                reason="复用本轮已构建的规则修改包。",
                candidate_recommended=True,
            )
        patch = await self._patch_builder.build(
            feedback=selected_feedback,
            diagnoses=selected_diagnoses,
        )
        profile = selected_feedback[0].profile
        if self._packages:
            source_root, _ = await self._packages.resolve(profile)
        else:
            snapshot = self._profiles.resolve(profile.key, profile.version, allow_experimental=True)
            source_root = self._sandbox.root / "inputs" / snapshot.checksum[7:]
            if not source_root.exists():
                await asyncio.to_thread(build_package, snapshot, source_root)
        sandbox_path = self._sandbox.create(
            candidate_id=candidate_id,
            source_profile=source_root,
        )
        checksum = self._sandbox.apply(sandbox_path, patch.operations)
        profile_json = sandbox_path / "profile.json"
        payload = json.loads(profile_json.read_text(encoding="utf-8"))
        for identity in ("key", "adapter", "capabilities", "resource_mode"):
            baseline = json.loads((source_root / "profile.json").read_text(encoding="utf-8"))
            if payload[identity] != baseline[identity]:
                raise ValueError("Candidate patch cannot change Profile identity or executable adapter.")
        payload["version"] = f"{profile.version.split('-')[0]}-candidate.{candidate_id}"
        profile_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        package_manifest = await asyncio.to_thread(seal_package, sandbox_path, source_checksum=checksum)
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
            resource_package_id=str(
                uuid5(
                    NAMESPACE_URL,
                    f"profile-package:{package_manifest.profile_key}/{package_manifest.profile_version}/"
                    f"{package_manifest.package_checksum[7:]}",
                )
            )
            if self._packages
            else None,
            resource_package_checksum=package_manifest.package_checksum if self._packages else None,
        )
        await self._candidates.put(candidate)
        if self._packages:
            await self._packages.upload(
                sandbox_path,
                created_by=authorized_by,
                candidate_id=candidate_id,
                base_package_id=source_root.name,
            )
        return ImprovementPreparation(
            regression_cases=cases,
            diagnoses=diagnoses,
            candidate=candidate,
            reason=(f"用户 {authorized_by} 已授权；候选已写入隔离 Profile 沙箱，尚未评测或发布。"),
            candidate_recommended=True,
            authorization_required=False,
        )

    async def publish_confirmed(self, candidate_id: str, reviewer_id: str) -> ProfileCandidate:
        """Enable a verified rule package after explicit human confirmation, without VLM evaluation."""
        if not reviewer_id.strip():
            raise ValueError("Rule publication requires a human reviewer.")
        candidate = await self._candidates.get(candidate_id)
        if self._packages:
            root, package = await self._packages.candidate_package(candidate)
        else:
            root = Path(candidate.sandbox_path)
            package = PackageManifest.model_validate_json(
                (root / "manifest.json").read_text(encoding="utf-8")
            )
            await asyncio.to_thread(verify_package, root, package)
        if package.source_profile_checksum != candidate.checksum:
            raise ValueError("Rule package content no longer matches the confirmed candidate.")
        manifest = ProfileManifest.model_validate_json((root / "profile.json").read_text(encoding="utf-8"))
        snapshot = ProfileSnapshot(
            manifest=manifest.model_copy(update={"status": ProfileStatus.ACTIVE}),
            profile_root=root,
            manifest_path=root / "profile.json",
            resolved_resources={key: root / safe_path(path) for key, path in manifest.resources.items()},
            checksum=candidate.checksum,
        )
        self._profiles.load_rules(snapshot)
        published = await self._candidates.activate_confirmed(candidate_id, reviewer_id)
        if self._packages:
            await self._packages.load_registry(self._profiles)
        else:
            self._profiles.register_snapshot(snapshot)
        return published

    async def evaluate(self, candidate_id: str, report: EvalReport) -> ImprovementEvaluation:
        if report.candidate_id != candidate_id:
            raise ValueError("Evaluation report candidate_id does not match the target candidate.")
        candidate = await self._candidates.get(candidate_id)
        if candidate.status == ProfileCandidateStatus.DRAFT:
            candidate = await self._candidates.transition(candidate_id, ProfileCandidateStatus.EVALUATING)
        elif candidate.status not in {ProfileCandidateStatus.EVALUATING, ProfileCandidateStatus.REJECTED}:
            raise ValueError("Candidate is not in an evaluation state.")
        judgement = await self._judge.judge(report)
        gate = self._gate.evaluate(report)
        await self._candidates.record_gate(candidate_id, gate)
        if not gate.passed and candidate.status != ProfileCandidateStatus.REJECTED:
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
        candidate = await self._candidates.get(candidate_id)
        if candidate.status != ProfileCandidateStatus.APPROVED:
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
        candidate = await self._candidates.get(candidate_id)
        if self._packages and candidate.resource_package_id:
            await self._packages.candidate_package(candidate)
            package_rows = await self._packages.client.select(
                "profile_resource_packages",
                params={
                    "id": f"eq.{candidate.resource_package_id}",
                },
            )
            active_rows = await self._packages.client.select(
                "profile_resource_packages",
                params={
                    "profile_key": f"eq.{candidate.profile.key}",
                    "status": "eq.active",
                },
            )
            allowed = {candidate.resource_package_id, package_rows[0].get("base_package_id")}
            if not any(row["id"] in allowed for row in active_rows):
                raise ValueError(
                    "Active Profile changed since this candidate was built; re-evaluation required."
                )
        if candidate.status == ProfileCandidateStatus.CANARY:
            candidate = await self._candidates.transition(candidate_id, ProfileCandidateStatus.ACTIVE)
        elif candidate.status != ProfileCandidateStatus.ACTIVE:
            raise ValueError("Only a reviewed canary may be published.")
        if self._packages and candidate.resource_package_id:
            audit = await self._candidates.audit_log(candidate_id)
            reviewer = next(
                (item.get("reviewer_id") for item in reversed(audit) if item.get("reviewer_id")), None
            )
            if not reviewer:
                raise ValueError("Published candidate requires an audited reviewer.")
            await self._packages.client.rpc(
                "publish_profile_package", {"package_id": candidate.resource_package_id, "reviewer": reviewer}
            )
            await self._packages.load_registry(self._profiles)
        return candidate

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
        candidate = await self._candidates.rollback(candidate_id, reviewer_id)
        if self._packages and candidate.resource_package_id:
            await self._packages.client.rpc(
                "rollback_profile_package",
                {"package_id": candidate.resource_package_id, "reviewer": reviewer_id},
            )
            await self._packages.load_registry(self._profiles)
        return candidate

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
