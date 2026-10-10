from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..domain.enums import RunStatus
from ..domain.models.improvement import Diagnosis
from ..domain.models.runs import AgentRun
from ..domain.ports import ArtifactRepository, ResultDataRepository
from ..harness.stores import CancellationToken
from .improvement_workflow import ImprovementWorkflow
from .worker import RunExecutionOutcome


class ImprovementRunExecutor:
    """Accepted feedback -> diagnosis -> user authorization -> sandbox candidate."""

    def __init__(
        self,
        *,
        result_data: ResultDataRepository,
        workflow: ImprovementWorkflow,
        artifacts: ArtifactRepository,
    ) -> None:
        self._result_data = result_data
        self._workflow = workflow
        self._artifacts = artifacts

    async def execute(self, run: AgentRun, cancellation: CancellationToken) -> RunExecutionOutcome:
        cancellation.raise_if_cancelled()
        feedback_id = run.feedback_id or run.source_document_id
        feedback = await self._result_data.get_accepted_feedback(feedback_id)
        artifacts = await self._artifacts.list_for_run(run.agent_run_id)
        candidate_artifact = _find_artifact(artifacts, "profile_candidate")
        if candidate_artifact is not None:
            return RunExecutionOutcome(
                status=RunStatus.NEEDS_REVIEW,
                artifact_ids=[str(candidate_artifact["artifact_id"])],
            )

        diagnosis_artifact = _find_artifact(artifacts, "improvement_diagnosis")
        if diagnosis_artifact is None:
            preparation = await self._workflow.diagnose([feedback])
            diagnosis_artifact_id = f"{run.agent_run_id}:improvement-diagnosis"
            await self._artifacts.put(
                diagnosis_artifact_id,
                {
                    "artifact_id": diagnosis_artifact_id,
                    "agent_run_id": run.agent_run_id,
                    "kind": "improvement_diagnosis",
                    "feedback": feedback.model_dump(mode="json"),
                    "diagnoses": [item.model_dump(mode="json") for item in preparation.diagnoses],
                    "regression_cases": [
                        item.model_dump(mode="json") for item in preparation.regression_cases
                    ],
                    "candidate_recommended": preparation.candidate_recommended,
                    "authorization_required": preparation.authorization_required,
                    "reason": preparation.reason,
                },
            )
            if not preparation.candidate_recommended:
                return RunExecutionOutcome(
                    status=RunStatus.SUCCEEDED,
                    artifact_ids=[diagnosis_artifact_id],
                    metrics={"diagnoses": len(preparation.diagnoses)},
                )
            return RunExecutionOutcome(
                status=RunStatus.WAITING_INPUT,
                artifact_ids=[diagnosis_artifact_id],
                metrics={"diagnoses": len(preparation.diagnoses)},
            )

        human_input = _latest_human_input(artifacts)
        if human_input is None or human_input.get("approve_profile_candidate") is not True:
            return RunExecutionOutcome(
                status=RunStatus.WAITING_INPUT,
                artifact_ids=[str(diagnosis_artifact["artifact_id"])],
            )
        reviewer_id = str(human_input.get("reviewer_id") or "").strip()
        if not reviewer_id:
            raise ValueError("Profile candidate authorization requires reviewer_id.")
        diagnoses = [Diagnosis.model_validate(item) for item in diagnosis_artifact.get("diagnoses", [])]
        preparation = await self._workflow.build_candidate(
            feedback=[feedback],
            diagnoses=diagnoses,
            authorized_by=reviewer_id,
        )
        if preparation.candidate is None:
            raise ValueError("Authorized candidate creation did not produce a candidate.")
        candidate_artifact_id = f"{run.agent_run_id}:profile-candidate"
        await self._artifacts.put(
            candidate_artifact_id,
            {
                "artifact_id": candidate_artifact_id,
                "agent_run_id": run.agent_run_id,
                "kind": "profile_candidate",
                "candidate": preparation.candidate.model_dump(mode="json"),
                "regression_cases": [item.model_dump(mode="json") for item in preparation.regression_cases],
                "authorized_by": reviewer_id,
                "reason": preparation.reason,
            },
        )
        return RunExecutionOutcome(
            status=RunStatus.NEEDS_REVIEW,
            artifact_ids=[candidate_artifact_id],
            metrics={"candidate_created": True},
        )


def _find_artifact(
    artifacts: list[Mapping[str, Any]],
    kind: str,
) -> Mapping[str, Any] | None:
    return next((item for item in artifacts if item.get("kind") == kind), None)


def _latest_human_input(artifacts: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    inputs = [item for item in artifacts if item.get("kind") == "human_input"]
    if not inputs:
        return None
    payload = inputs[-1].get("payload")
    return payload if isinstance(payload, Mapping) else None
