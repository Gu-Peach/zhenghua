from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import NAMESPACE_URL, uuid4, uuid5

from ..domain.models.improvement import AcceptedFeedback
from ..domain.models.proposals import ResultProposal
from ..domain.models.result_data import (
    ConnectionSearchQuery,
    ConnectionSearchResult,
    PrepareCorrectionRequest,
    PreparedCorrection,
    ResultCommitResult,
)
from ..domain.ports import ResultDataRepository
from ..infrastructure.correction_data import CorrectionDataRepository


class ControlledResultDataTool:
    """Strongly typed result lookup/correction commands; never accepts SQL or table names."""

    def __init__(
        self,
        *,
        repository: ResultDataRepository,
        correction_data: CorrectionDataRepository,
        authorize: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> None:
        self._repository = repository
        self._correction_data = correction_data
        self._authorize = authorize

    async def find_connections(self, query: ConnectionSearchQuery) -> list[ConnectionSearchResult]:
        return await self._repository.search_connections(query)

    async def authorize_project(self, project_id: str, user_id: str) -> None:
        if self._authorize:
            await self._authorize(project_id, user_id)

    async def prepare_correction(self, request: PrepareCorrectionRequest) -> PreparedCorrection:
        matches = await self.find_connections(request.query)
        if not matches:
            raise LookupError("没有找到符合条件的连接。")
        if len(matches) > 1:
            raise ValueError("检索条件匹配多个连接，需要用户补充唯一目标。")
        match = matches[0]
        if self._authorize:
            await self._authorize(match.project_id, request.requested_by)
        bundle = await self._repository.get_correction_bundle(match.connection_id)
        feedback_id = (
            str(uuid5(NAMESPACE_URL, f"correction:{request.requested_by}:{request.item_id}"))
            if request.item_id
            else str(uuid4())
        )
        bundle.facts.feedback_id = feedback_id
        bundle.facts.target.project_id = match.project_id
        bundle.facts.target.result_version_id = match.result_version_id
        bundle.facts.target.id = match.connection_id
        bundle.facts.target.field = request.field
        bundle.facts.issue_kind = request.issue_kind
        bundle.facts.is_cross_page = match.is_cross_page
        bundle.facts.suggested_value_present = request.suggested_value_present
        bundle.context.feedback_id = feedback_id
        bundle.context.field = request.field
        bundle.context.observed_problem = request.observed_problem
        bundle.context.suggested_value = request.suggested_value
        bundle.context.evidence["feedback_origin"] = request.feedback_origin
        if any(record.get("origin") == "manual_injected_test_error" for record in bundle.current_records):
            bundle.context.evidence["feedback_origin"] = "manual_injected_test_error"
        bundle.context.constraints.allowed_connection_ids = [match.connection_id]
        bundle.context.constraints.allowed_fields = [request.field] if request.field else []
        if request.field and request.field.startswith("start_"):
            bundle.context.constraints.preserve_start = False
        bundle.base_result_version = match.result_version
        bundle.base_result_revision = match.result_revision
        await self._correction_data.register(bundle, requested_by=request.requested_by)
        return PreparedCorrection(
            feedback_id=feedback_id,
            match=match,
            expected_result_version=match.result_version,
        )

    async def commit_result_patch(
        self,
        proposal: ResultProposal,
        *,
        confirmed_by: str,
    ) -> ResultCommitResult:
        if self._authorize:
            await self._authorize(proposal.project_id, confirmed_by)
        return await self._repository.commit_result_patch(proposal, confirmed_by)

    async def get_accepted_feedback(self, feedback_id: str) -> AcceptedFeedback:
        return await self._repository.get_accepted_feedback(feedback_id)
