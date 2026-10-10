from __future__ import annotations

from copy import deepcopy

from ..domain.enums import CorrectionAction, CorrectionIssueKind, RunStatus, ScopeType
from ..domain.models.proposals import ProposalValidation, ResultPatchProposal
from ..domain.models.runs import AgentRun, ModelRef, RunScope
from ..harness.stores import CancellationToken
from ..infrastructure.correction_data import CorrectionDataProvider
from ..tools.correction_router import CorrectionRoutePlanner
from ..tools.deterministic_validator import DeterministicCorrectionValidator
from ..tools.extraction_runner import ScopedExtractionRunner
from ..tools.result_diff import ResultDiffTool
from .worker import RunExecutionOutcome


class CorrectionWorkflowExecutor:
    def __init__(
        self,
        *,
        data: CorrectionDataProvider,
        stages: ScopedExtractionRunner,
        model_name: str,
    ) -> None:
        self._data = data
        self._stages = stages
        self._model_name = model_name
        self._planner = CorrectionRoutePlanner()
        self._validator = DeterministicCorrectionValidator()
        self._diff = ResultDiffTool()

    async def execute(self, run: AgentRun, cancellation: CancellationToken) -> RunExecutionOutcome:
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
            from ..domain.enums import ErrorCode
            from ..domain.errors import AgentServiceError

            raise AgentServiceError(
                ErrorCode.BASE_VERSION_CONFLICT,
                "The correction base result version has changed.",
                retryable=False,
            )
        plan = self._planner.plan(bundle.facts)
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
            records = await self._stages.run(plan, bundle)
        cancellation.raise_if_cancelled()
        constraints = bundle.context.constraints.model_copy(deep=True)
        constraints.allowed_connection_ids = sorted(
            set(constraints.allowed_connection_ids) | {bundle.facts.target.id}
        )
        if bundle.facts.target.field:
            constraints.allowed_fields = sorted(set(constraints.allowed_fields) | {bundle.facts.target.field})
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
