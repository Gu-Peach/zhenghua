from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from src.domain.enums import RunStatus
from src.domain.models.improvement import AcceptedFeedback, Diagnosis
from src.domain.models.runs import AgentRun
from src.domain.ports import ArtifactRepository, ResultDataRepository, TraceStore
from src.harness.stores import CancellationToken
from src.application.improvement_workflow import ImprovementWorkflow
from src.application.worker import RunExecutionOutcome


class ImprovementRunExecutor:
    """Accepted feedback -> diagnosis -> user authorization -> sandbox candidate."""

    def __init__(
        self,
        *,
        result_data: ResultDataRepository,
        workflow: ImprovementWorkflow,
        artifacts: ArtifactRepository,
        traces: TraceStore | None = None,
    ) -> None:
        self._result_data = result_data
        self._workflow = workflow
        self._artifacts = artifacts
        self._traces = traces

    async def execute(self, run: AgentRun, cancellation: CancellationToken) -> RunExecutionOutcome:
        cancellation.raise_if_cancelled()
        feedback_id = run.feedback_id or run.source_document_id
        feedback = await self._result_data.get_accepted_feedback(feedback_id)
        feedback_items = [feedback] + [
            await self._result_data.get_accepted_feedback(key)
            for key in run.options.correction_feedback_ids
            if key != feedback_id
        ]
        evidence = []
        trace_keys = set(feedback.trace_ids)
        for key in feedback.stage_artifact_ids:
            value = await self._artifacts.get(key)
            if value is not None:
                evidence.append(dict(value))
                source = value.get("bundle", {}).get("context", {}).get("evidence", {}).get("source_run_id")
                if source:
                    evidence.extend(dict(item) for item in await self._artifacts.list_for_run(str(source)))
                    trace_keys.add(str(source))
        if feedback.correction_run_id:
            evidence.extend(
                dict(item) for item in await self._artifacts.list_for_run(feedback.correction_run_id)
            )
        feedback.context["artifacts"] = evidence
        feedback.context["traces"] = [
            dict(trace)
            for key in sorted(trace_keys)
            for trace in (await self._traces.list(key) if self._traces else [])
        ]
        artifacts = await self._artifacts.list_for_run(run.agent_run_id)
        for item in feedback_items[1:]:
            item.context = dict(feedback.context)
        candidate_artifact = _find_artifact(artifacts, "profile_candidate")
        candidate_artifact = candidate_artifact or _find_artifact(artifacts, "profile_candidate_pending")

        diagnosis_artifact = _find_artifact(artifacts, "improvement_diagnosis")
        if diagnosis_artifact is None and candidate_artifact is None:
            preparation = await self._workflow.diagnose(feedback_items)
            diagnosis_artifact_id = f"{run.agent_run_id}:improvement-diagnosis"
            await self._artifacts.put(
                diagnosis_artifact_id,
                {
                    "artifact_id": diagnosis_artifact_id,
                    "agent_run_id": run.agent_run_id,
                    "kind": "improvement_diagnosis",
                    "feedback": feedback.model_dump(mode="json"),
                    "feedback_items": [item.model_dump(mode="json") for item in feedback_items],
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
        if human_input is not None and human_input.get("approve_profile_candidate") is False:
            return RunExecutionOutcome(
                status=RunStatus.SUCCEEDED,
                artifact_ids=[str((diagnosis_artifact or candidate_artifact or {})["artifact_id"])],
                metrics={"candidate_declined": True},
            )
        if human_input is None or human_input.get("approve_profile_candidate") is not True:
            return RunExecutionOutcome(
                status=RunStatus.WAITING_INPUT,
                artifact_ids=[str((candidate_artifact or diagnosis_artifact or {})["artifact_id"])],
            )
        reviewer_id = str(human_input.get("reviewer_id") or "").strip()
        if not reviewer_id or reviewer_id != run.requested_by:
            raise PermissionError("Rule modification requires confirmation from the source user.")
        if candidate_artifact is not None:
            return await self._publish(run, candidate_artifact["candidate"]["candidate_id"], reviewer_id)
        assert diagnosis_artifact is not None
        diagnoses = [Diagnosis.model_validate(item) for item in diagnosis_artifact.get("diagnoses", [])]
        feedback_items = [
            AcceptedFeedback.model_validate(value)
            for value in diagnosis_artifact.get("feedback_items", [diagnosis_artifact["feedback"]])
        ]
        preparation = await self._workflow.build_candidate(
            feedback=feedback_items,
            diagnoses=diagnoses,
            authorized_by=reviewer_id,
            candidate_id=str(uuid5(NAMESPACE_URL, f"confirmed-rule-update:{run.agent_run_id}")),
        )
        if preparation.candidate is None:
            raise ValueError("Authorized candidate creation did not produce a candidate.")
        candidate_artifact_id = f"{run.agent_run_id}:profile-candidate-pending"
        await self._artifacts.put(
            candidate_artifact_id,
            {
                "artifact_id": candidate_artifact_id,
                "agent_run_id": run.agent_run_id,
                "kind": "profile_candidate_pending",
                "candidate": preparation.candidate.model_dump(mode="json"),
                "regression_cases": [item.model_dump(mode="json") for item in preparation.regression_cases],
                "authorized_by": reviewer_id,
                "reason": preparation.reason,
            },
        )
        return await self._publish(run, preparation.candidate.candidate_id, reviewer_id)

    async def _publish(self, run: AgentRun, candidate_id: str, reviewer_id: str) -> RunExecutionOutcome:
        candidate = await self._workflow.publish_confirmed(candidate_id, reviewer_id)
        artifact_id = f"{run.agent_run_id}:profile-rule-update"
        await self._artifacts.put(
            artifact_id,
            {
                "artifact_id": artifact_id,
                "agent_run_id": run.agent_run_id,
                "kind": "profile_rule_update",
                "candidate": candidate.model_dump(mode="json"),
                "authorized_by": reviewer_id,
                "evaluation_required": False,
                "reason": "用户确认后规则修改已落地并启用；旧项目未自动切换规则版本。",
            },
        )
        return RunExecutionOutcome(
            status=RunStatus.SUCCEEDED,
            artifact_ids=[artifact_id],
            metrics={"rules_updated": True},
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
