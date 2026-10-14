from __future__ import annotations

from copy import deepcopy

from src.domain.enums import (
    AgentStage,
    CorrectionAction,
    CorrectionIssueKind,
    EventType,
    RunStatus,
    ScopeType,
)
from src.domain.models.correction import CorrectionBatch
from src.domain.models.proposals import ProposalOperation, ProposalValidation, ResultPatchProposal
from src.domain.models.runs import AgentRun, ModelRef, RunScope
from src.domain.ports import ArtifactRepository
from src.harness.stores import CancellationToken
from src.infrastructure.correction_data import CorrectionDataProvider
from src.tools.correction_router import CorrectionRoutePlanner
from src.tools.deterministic_validator import DeterministicCorrectionValidator
from src.agent.extraction_agent.tools.extraction_runner import ScopedExtractionRunner
from src.tools.result_diff import ResultDiffTool
from src.application.run_control import RunEventPublisher
from src.application.worker import RunExecutionOutcome


class CorrectionWorkflowExecutor:
    def __init__(
        self,
        *,
        data: CorrectionDataProvider,
        stages: ScopedExtractionRunner,
        model_name: str,
        artifacts: ArtifactRepository | None = None,
        publisher: RunEventPublisher | None = None,
    ) -> None:
        self._data = data
        self._stages = stages
        self._model_name = model_name
        self._planner = CorrectionRoutePlanner()
        self._validator = DeterministicCorrectionValidator()
        self._diff = ResultDiffTool()
        self._artifacts = artifacts
        self._publisher = publisher

    async def execute(self, run: AgentRun, cancellation: CancellationToken) -> RunExecutionOutcome:
        if run.options.correction_feedback_ids:
            return await self._execute_batch(run, cancellation)
        return await self._execute_item(run, cancellation)

    async def _execute_batch(self, run: AgentRun, cancellation: CancellationToken) -> RunExecutionOutcome:
        bundles = [await self._data.get_bundle(key) for key in run.options.correction_feedback_ids]
        identities = {
            (
                b.facts.target.project_id,
                b.facts.target.result_version_id,
                b.base_result_revision,
                b.profile.profile.key,
                b.profile.profile.version,
                b.profile.profile.checksum,
            )
            for b in bundles
        }
        if len(identities) != 1:
            raise ValueError("Correction batch must freeze one project, result and Profile version.")
        rank = {
            CorrectionAction.DIRECT_PATCH: 0,
            CorrectionAction.DETERMINISTIC_ONLY: 0,
            CorrectionAction.RERUN_STAGE_2: 1,
            CorrectionAction.RERUN_STAGE_2_AND_3: 2,
        }
        bundles.sort(key=lambda b: rank.get(self._planner.plan(b.facts).action, 3))
        batch = CorrectionBatch(
            batch_id=run.agent_run_id,
            project_id=run.project_id,
            base_result_version_id=bundles[0].facts.target.result_version_id,
            profile=bundles[0].profile,
            feedback_ids=run.options.correction_feedback_ids,
            direct_patch=[
                b.facts.feedback_id
                for b in bundles
                if self._planner.plan(b.facts).action == CorrectionAction.DIRECT_PATCH
            ],
            stage2=[
                b.facts.feedback_id
                for b in bundles
                if self._planner.plan(b.facts).action == CorrectionAction.RERUN_STAGE_2
            ],
            stage2_stage3=[
                b.facts.feedback_id
                for b in bundles
                if self._planner.plan(b.facts).action == CorrectionAction.RERUN_STAGE_2_AND_3
            ],
        )
        if self._artifacts:
            artifact_id = f"{run.agent_run_id}:correction-batch"
            await self._artifacts.put(
                artifact_id,
                {
                    "artifact_id": artifact_id,
                    "agent_run_id": run.agent_run_id,
                    "kind": "correction_batch",
                    "batch": batch.model_dump(mode="json"),
                },
            )
        proposals = []
        for bundle in bundles:
            cancellation.raise_if_cancelled()
            child = run.model_copy(
                update={
                    "feedback_id": bundle.facts.feedback_id,
                    "scope": RunScope(
                        type=bundle.facts.target.type,
                        id=bundle.facts.target.id,
                        field=bundle.facts.target.field,
                    ),
                }
            )
            result = await self._execute_item(child, cancellation)
            if not isinstance(result.proposal, ResultPatchProposal):
                raise ValueError("One correction item has insufficient evidence; batch was not committed.")
            proposals.append(result.proposal)
        merged: dict[str, ProposalOperation] = {}
        for proposal in proposals:
            for operation in proposal.operations:
                previous = merged.get(operation.target_id)
                if previous is None:
                    merged[operation.target_id] = operation.model_copy(deep=True)
                    continue
                assert operation.before is not None and operation.after is not None
                assert previous.after is not None
                assert previous.before is not None
                for key, value in operation.after.items():
                    if operation.before.get(key) != value:
                        if (
                            previous.before.get(key) != previous.after.get(key)
                            and previous.after.get(key) != value
                        ):
                            raise ValueError("Conflicting correction items target the same field.")
                        previous.after[key] = value
        warnings = [warning for p in proposals for warning in p.validation.warnings]
        combined = proposals[0].model_copy(
            update={
                "proposal_id": f"{run.agent_run_id}:result-proposal",
                "scope": run.scope,
                "feedback_id": run.feedback_id,
                "feedback_ids": run.options.correction_feedback_ids,
                "operations": list(merged.values()),
                "unchanged_assertions": [],
                "stage_artifact_ids": sorted({key for p in proposals for key in p.stage_artifact_ids}),
                "trace_ids": sorted({key for p in proposals for key in p.trace_ids}),
                "validation": ProposalValidation(
                    schema_valid=True, business_rules_valid=not warnings, warnings=warnings
                ),
                "status": "NEEDS_REVIEW" if warnings or not merged else "READY_FOR_REVIEW",
                "feedback_origin": "manual_injected_test_error"
                if any(p.feedback_origin == "manual_injected_test_error" for p in proposals)
                else "user",
            }
        )
        return RunExecutionOutcome(
            status=RunStatus.NEEDS_REVIEW,
            proposal=combined,
            artifact_ids=combined.stage_artifact_ids,
            metrics={"items": len(bundles), "operations": len(merged)},
        )

    async def _execute_item(self, run: AgentRun, cancellation: CancellationToken) -> RunExecutionOutcome:
        if not run.feedback_id:
            raise ValueError("Correction runs require feedback_id.")
        cancellation.raise_if_cancelled()
        bundle = await self._data.get_bundle(run.feedback_id)
        if bundle.facts.target.project_id != run.project_id:
            raise ValueError("Feedback target does not belong to the run project.")
        if bundle.facts.target.id != run.scope.id or bundle.facts.target.type != run.scope.type:
            raise ValueError("Correction target does not match the requested run scope.")
        if (
            bundle.facts.issue_kind == CorrectionIssueKind.DIRECT_VALUE_CHANGE
            and not bundle.facts.suggested_value_present
        ):
            raise ValueError("Direct value changes require a persisted suggested value.")
        if run.expected_result_version is None or run.expected_result_version != bundle.base_result_version:
            from src.domain.enums import ErrorCode
            from src.domain.errors import AgentServiceError

            raise AgentServiceError(
                ErrorCode.BASE_VERSION_CONFLICT,
                "The correction base result version has changed.",
                retryable=False,
            )
        plan = self._planner.plan(bundle.facts)
        item_artifact_id = f"{run.agent_run_id}:correction:{run.feedback_id}"
        if self._artifacts:
            cached = await self._artifacts.get(item_artifact_id)
            if cached:
                return RunExecutionOutcome(
                    status=RunStatus.NEEDS_REVIEW,
                    proposal=ResultPatchProposal.model_validate(cached["proposal"]),
                    artifact_ids=[item_artifact_id],
                )
        records = deepcopy(bundle.current_records)
        if plan.action == CorrectionAction.NO_ACTION:
            return RunExecutionOutcome(status=RunStatus.NEEDS_REVIEW)
        if plan.action == CorrectionAction.DIRECT_PATCH:
            if bundle.facts.target.type != ScopeType.CONNECTION:
                raise ValueError("Direct value patches require a single connection target.")
            field = bundle.context.field or bundle.facts.target.field
            target = next(
                (item for item in records if _id(item) == bundle.facts.target.id),
                None,
            )
            if target is None or not field:
                raise ValueError("Direct patch requires a target record and field.")
            target[field] = bundle.context.suggested_value
        elif plan.action == CorrectionAction.DETERMINISTIC_ONLY:
            records = [_normalize(item) for item in records]
        else:
            records = await self._stages.run(plan, bundle, run=run, cancellation=cancellation)
            if bundle.context.constraints.allowed_fields:
                projected = []
                for record in records:
                    original = next(item for item in bundle.current_records if _id(item) == _id(record))
                    value = deepcopy(original)
                    for field in bundle.context.constraints.allowed_fields + [
                        "status",
                        "confidence",
                        "is_cross_page",
                    ]:
                        if field in record:
                            value[field] = record[field]
                    projected.append(value)
                records = projected
        cancellation.raise_if_cancelled()
        constraints = bundle.context.constraints.model_copy(deep=True)
        constraints.allowed_connection_ids = sorted(
            set(constraints.allowed_connection_ids) | {bundle.facts.target.id}
        )
        if bundle.facts.target.field:
            constraints.allowed_fields = sorted(set(constraints.allowed_fields) | {bundle.facts.target.field})
        if plan.action not in {CorrectionAction.DIRECT_PATCH, CorrectionAction.DETERMINISTIC_ONLY}:
            if constraints.allowed_fields:
                constraints.allowed_fields = sorted(set(constraints.allowed_fields) | {"is_cross_page"})
        warnings = self._validator.validate(
            before=bundle.current_records,
            after=records,
            constraints=constraints,
        )
        operations = self._diff.diff(
            before=bundle.current_records,
            after=records,
            evidence_ids=bundle.evidence_ids,
            record_versions=bundle.record_versions,
            allowed_connection_ids=constraints.allowed_connection_ids,
            allowed_fields=constraints.allowed_fields,
            reason=plan.reason,
        )
        proposal = ResultPatchProposal(
            proposal_id=f"{run.agent_run_id}:result-proposal",
            agent_run_id=run.agent_run_id,
            project_id=run.project_id,
            base_result_version=bundle.base_result_version,
            base_result_revision=bundle.base_result_revision,
            profile=bundle.profile.profile,
            model=ModelRef(name=run.options.model_override or self._model_name),
            scope=RunScope(
                type=bundle.facts.target.type,
                id=bundle.facts.target.id,
                field=bundle.facts.target.field,
            ),
            feedback_id=run.feedback_id,
            operations=operations,
            unchanged_assertions=[
                self._diff.unchanged_assertion(
                    scope=bundle.facts.target.result_version_id,
                    records=bundle.unaffected_records,
                )
            ],
            validation=ProposalValidation(
                schema_valid=True,
                business_rules_valid=not warnings,
                warnings=warnings,
            ),
            status="NEEDS_REVIEW" if warnings or not operations else "READY_FOR_REVIEW",
            feedback_ids=[run.feedback_id],
            stage_artifact_ids=[item_artifact_id],
            trace_ids=[run.agent_run_id] if plan.estimated_model_calls else [],
            feedback_origin=str(bundle.context.evidence.get("feedback_origin", "user")),
        )
        if self._artifacts:
            await self._artifacts.put(
                item_artifact_id,
                {
                    "artifact_id": item_artifact_id,
                    "agent_run_id": run.agent_run_id,
                    "kind": "correction_item",
                    "feedback_id": run.feedback_id,
                    "bundle": bundle.model_dump(mode="json"),
                    "plan": plan.model_dump(mode="json"),
                    "proposal": proposal.model_dump(mode="json"),
                },
            )
        if self._publisher:
            await self._publisher.publish(
                run,
                EventType.STAGE_COMPLETED,
                stage=AgentStage.PROPOSAL,
                message="纠错项已持久化，等待用户确认。",
                artifact_refs=[item_artifact_id] if self._artifacts else [],
            )
        return RunExecutionOutcome(
            status=RunStatus.NEEDS_REVIEW,
            proposal=proposal,
            metrics={"operations": len(operations), "estimated_model_calls": plan.estimated_model_calls},
        )


def _id(record: dict[str, object]) -> str:
    return str(record.get("connection_id") or record.get("id") or "")


def _normalize(record: dict[str, object]) -> dict[str, object]:
    value = deepcopy(record)
    for key, item in list(value.items()):
        if isinstance(item, str):
            value[key] = item.strip()
    return value
