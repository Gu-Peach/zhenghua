from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from ..domain.enums import CorrectionIssueKind, CrossPageState, ErrorCode, ScopeType
from ..domain.errors import AgentServiceError
from ..domain.models.correction import (
    CorrectionConstraints,
    CorrectionContext,
    CorrectionEvidenceBundle,
    CorrectionFacts,
    FeedbackTarget,
)
from ..domain.models.extraction_stages import (
    CrossPageCompletionRequest,
    DrawingPageInput,
    PageClassificationRequest,
    PageScanRequest,
)
from ..domain.models.improvement import AcceptedFeedback, AffectedScope
from ..domain.models.proposals import ResultProposal
from ..domain.models.result_data import (
    ConnectionSearchQuery,
    ConnectionSearchResult,
    ResultCommitResult,
)
from ..profiles import ProfileRegistry
from .result_mapping import normalized_connection_from_record, proposal_to_normalized_units
from .supabase_client import SupabaseClient


class SupabaseResultDataRepository:
    """Controlled normalized result lookup and atomic version persistence."""

    def __init__(
        self,
        client: SupabaseClient,
        *,
        profiles: ProfileRegistry,
        drawing_cache_root: Path,
    ) -> None:
        self._client = client
        self._profiles = profiles
        self._drawing_cache_root = drawing_cache_root.resolve()

    async def search_connections(
        self,
        query: ConnectionSearchQuery,
    ) -> list[ConnectionSearchResult]:
        params: dict[str, str] = {"order": "result_version.desc,wire_number.asc,core_order.asc"}
        fields = {
            "project_id": query.project_id,
            "project_name": query.project_name,
            "workspace_id": query.workspace_id,
            "workspace_name": query.workspace_name,
            "workspace_page": query.workspace_page,
            "result_version_id": query.result_version_id,
            "connection_id": query.connection_id,
            "wire_number": query.wire_number,
        }
        for field, value in fields.items():
            if value is not None:
                params[field] = f"eq.{value}"
        rows = await self._client.select("wiring_connection_rows", params=params)
        if query.terminal is not None:
            rows = [
                row
                for row in rows
                if query.terminal in {row.get("start_terminal"), row.get("end_terminal")}
            ]
        if query.result_version_id is None and query.connection_id is None:
            latest = {
                str(row["project_id"]): max(
                    int(item["result_version"])
                    for item in rows
                    if item["project_id"] == row["project_id"]
                )
                for row in rows
            }
            rows = [row for row in rows if int(row["result_version"]) == latest[str(row["project_id"])]]
        return [_search_result(row) for row in rows]

    async def get_correction_bundle(self, connection_id: str) -> CorrectionEvidenceBundle:
        matches = await self.search_connections(ConnectionSearchQuery(connection_id=connection_id))
        if not matches:
            raise AgentServiceError(
                ErrorCode.PROJECT_CONTEXT_NOT_FOUND,
                "The requested connection was not found.",
                retryable=False,
            )
        match = matches[0]
        connection_rows = await self._client.select(
            "wiring_connections",
            params={"id": f"eq.{connection_id}", "limit": "1"},
        )
        if not connection_rows:
            raise AgentServiceError(
                ErrorCode.PROJECT_CONTEXT_NOT_FOUND,
                "The requested connection payload was not found.",
                retryable=False,
            )
        connection = connection_rows[0]
        evidence = await self._client.select(
            "connection_evidence",
            params={"connection_id": f"eq.{connection_id}", "order": "created_at.asc"},
        )
        drawings = await self._client.select(
            "drawings",
            params={"project_id": f"eq.{match.project_id}", "order": "pdf_page_number.asc"},
        )
        drawing_by_id = {str(row["id"]): row for row in drawings}
        source_id = str(connection.get("source_drawing_id") or "")
        if not source_id and connection.get("wiring_unit_id"):
            unit_rows = await self._client.select(
                "wiring_units",
                params={"id": f"eq.{connection['wiring_unit_id']}", "select": "drawing_id", "limit": "1"},
            )
            if unit_rows and unit_rows[0].get("drawing_id"):
                source_id = str(unit_rows[0]["drawing_id"])
        source = drawing_by_id.get(source_id)
        if source is None and match.workspace_page is not None:
            source = next(
                (row for row in drawings if str(row.get("workspace_page")) == match.workspace_page),
                None,
            )
        if source is None:
            raise AgentServiceError(
                ErrorCode.PROJECT_CONTEXT_NOT_FOUND,
                "The source drawing for this connection was not found.",
                retryable=False,
            )

        result_rows = await self._client.select(
            "result_versions",
            params={"id": f"eq.{match.result_version_id}", "limit": "1"},
        )
        profile_value = result_rows[0].get("profile") if result_rows else None
        profile_key = (
            str(profile_value.get("key"))
            if isinstance(profile_value, Mapping) and profile_value.get("key")
            else None
        )
        if not profile_key:
            projects = await self._client.select(
                "projects",
                params={"id": f"eq.{match.project_id}", "select": "standard_profile", "limit": "1"},
            )
            profile_key = str(projects[0].get("standard_profile") or "zh")
        binding = self._profiles.bind(profile_key, allow_experimental=True)

        source_page = await self._drawing_input(match.project_id, source)
        current = _current_record(match, connection)
        context_json = json.dumps(
            {"target_connection_id": connection_id, "current_record": current},
            ensure_ascii=False,
        )
        run_key = f"correction:{connection_id}"
        target_evidence = [row for row in evidence if row.get("kind") == "target"]
        cross_requests: list[CrossPageCompletionRequest] = []
        task_targets: dict[str, str] = {}
        for index, row in enumerate(target_evidence, start=1):
            drawing = drawing_by_id.get(str(row["drawing_id"]))
            if drawing is None:
                continue
            task_id = f"{connection_id}:target:{index}"
            cross_requests.append(
                CrossPageCompletionRequest(
                    run_id=run_key,
                    project_id=match.project_id,
                    profile=binding,
                    task_id=task_id,
                    target_page=await self._drawing_input(match.project_id, drawing),
                    task_context=context_json,
                )
            )
            task_targets[task_id] = connection_id

        evidence_ids = [str(row["id"]) for row in evidence]
        if not evidence_ids:
            evidence_ids = [f"connection:{connection_id}"]
        target_drawing_ids = [str(row["drawing_id"]) for row in target_evidence]
        return CorrectionEvidenceBundle(
            facts=CorrectionFacts(
                feedback_id="pending-feedback",
                target=FeedbackTarget(
                    type=ScopeType.CONNECTION,
                    id=connection_id,
                    project_id=match.project_id,
                    result_version_id=match.result_version_id,
                ),
                issue_kind=CorrectionIssueKind.RECOGNITION_ERROR,
                is_cross_page=match.is_cross_page,
                affected_drawing_ids=[str(source["id"])],
                target_drawing_ids=target_drawing_ids,
            ),
            context=CorrectionContext(
                feedback_id="pending-feedback",
                observed_problem="Re-read the selected connection.",
                constraints=CorrectionConstraints(
                    allowed_target_drawings=target_drawing_ids,
                    allowed_connection_ids=[connection_id],
                ),
                evidence={"connection": current, "evidence_rows": evidence},
            ),
            profile=binding,
            base_result_version=match.result_version,
            current_records=[current],
            record_versions={connection_id: match.record_version},
            evidence_ids=evidence_ids,
            page_classification_requests=[
                PageClassificationRequest(
                    run_id=run_key,
                    project_id=match.project_id,
                    profile=binding,
                    page=source_page,
                    known_context=context_json,
                )
            ],
            page_scan_requests=[
                PageScanRequest(
                    run_id=run_key,
                    project_id=match.project_id,
                    profile=binding,
                    page=source_page,
                    page_context=context_json,
                )
            ],
            cross_page_requests=cross_requests,
            cross_page_task_targets=task_targets,
        )

    async def persist_extraction_proposal(
        self,
        proposal: ResultProposal,
        created_by: str,
    ) -> ResultCommitResult:
        drawings = await self._client.select(
            "drawings",
            params={"project_id": f"eq.{proposal.project_id}", "order": "pdf_page_number.asc"},
        )
        workspaces = await self._client.select(
            "workspaces",
            params={"project_id": f"eq.{proposal.project_id}", "order": "sort_order.asc"},
        )
        units = proposal_to_normalized_units(proposal, drawings=drawings, workspaces=workspaces)
        status = (
            "needs_review"
            if proposal.status == "NEEDS_REVIEW"
            or not proposal.validation.schema_valid
            or not proposal.validation.business_rules_valid
            else "draft"
        )
        committed = await self._commit_rpc(
            proposal=proposal,
            created_by=created_by,
            target_status=status,
            units=units,
            feedback_updates=[],
        )
        return ResultCommitResult(
            proposal_id=proposal.proposal_id,
            project_id=proposal.project_id,
            previous_result_version=proposal.base_result_version,
            result_version=int(committed["result_version"]),
            result_version_id=str(committed["result_version_id"]),
            confirmed_by=created_by,
        )

    async def commit_result_patch(
        self,
        proposal: ResultProposal,
        confirmed_by: str,
    ) -> ResultCommitResult:
        feedback_id = getattr(proposal, "feedback_id", None)
        if not isinstance(feedback_id, str) or not feedback_id:
            raise AgentServiceError(
                ErrorCode.INVALID_REQUEST,
                "Result patch confirmation requires feedback_id.",
                retryable=False,
            )
        versions = await self._client.select(
            "result_versions",
            params={
                "project_id": f"eq.{proposal.project_id}",
                "version": f"eq.{proposal.base_result_version}",
                "limit": "1",
            },
        )
        if not versions:
            raise AgentServiceError(
                ErrorCode.BASE_VERSION_CONFLICT,
                "The base result version no longer exists.",
                retryable=False,
            )
        units = await self._version_payload(str(versions[0]["id"]))
        by_connection = {
            str(connection["source_connection_id"]): (unit, connection)
            for unit in units
            for connection in unit["connections"]
        }
        before_values: dict[str, Any] = {}
        after_values: dict[str, Any] = {}
        evidence_ids: list[str] = []
        for operation in proposal.operations:
            if operation.op != "replace" or operation.before is None or operation.after is None:
                raise AgentServiceError(
                    ErrorCode.INVALID_REQUEST,
                    "Confirmed correction proposals accept replace operations only.",
                    retryable=False,
                )
            pair = by_connection.get(operation.target_id)
            if pair is None:
                raise AgentServiceError(
                    ErrorCode.PROJECT_CONTEXT_NOT_FOUND,
                    "A correction target is outside the base result version.",
                    retryable=False,
                )
            unit, current = pair
            if operation.expected_version is not None and operation.expected_version != int(
                current["record_version"]
            ):
                raise AgentServiceError(
                    ErrorCode.BASE_VERSION_CONFLICT,
                    "A connection changed before confirmation.",
                    retryable=False,
                )
            before_values[operation.target_id] = operation.before
            after_values[operation.target_id] = operation.after
            evidence_ids.extend(operation.evidence_ids)
            current.update(
                normalized_connection_from_record(
                    operation.after,
                    current=current,
                    record_version=int(current["record_version"]) + 1,
                )
            )
            current["status"] = "confirmed"
            current["needs_review"] = False
            if operation.after.get("terminal_strip") not in (None, ""):
                unit["terminal_strip"] = str(operation.after["terminal_strip"])

        accepted = AcceptedFeedback(
            feedback_id=feedback_id,
            project_id=proposal.project_id,
            accepted=True,
            result_version_id="pending",
            profile=proposal.profile,
            model_name=proposal.model.name,
            target=AffectedScope(type=proposal.scope.type, ids=list(before_values)),
            before=before_values,
            after=after_values,
            evidence_ids=sorted(set(evidence_ids)) or [f"feedback:{feedback_id}"],
            stage_artifact_ids=[f"{proposal.agent_run_id}:correction"],
            trace_ids=[f"{proposal.agent_run_id}:trace"],
            prompt_checksum=proposal.profile.checksum or "unversioned-profile",
        )
        committed = await self._commit_rpc(
            proposal=proposal,
            created_by=confirmed_by,
            target_status="accepted",
            units=units,
            feedback_updates=[
                {
                    "feedback_id": feedback_id,
                    "before": before_values,
                    "after": after_values,
                    "accepted_payload": accepted.model_dump(mode="json"),
                }
            ],
        )
        stored_feedback = await self.get_accepted_feedback(feedback_id)
        return ResultCommitResult(
            proposal_id=proposal.proposal_id,
            project_id=proposal.project_id,
            previous_result_version=proposal.base_result_version,
            result_version=int(committed["result_version"]),
            result_version_id=str(committed["result_version_id"]),
            confirmed_by=confirmed_by,
            accepted_feedback=[stored_feedback],
        )

    async def get_accepted_feedback(self, feedback_id: str) -> AcceptedFeedback:
        rows = await self._client.select(
            "feedback_items",
            params={"id": f"eq.{feedback_id}", "status": "eq.accepted", "limit": "1"},
        )
        if not rows or not isinstance(rows[0].get("accepted_payload"), Mapping):
            raise KeyError(feedback_id)
        return AcceptedFeedback.model_validate(rows[0]["accepted_payload"])

    async def _commit_rpc(
        self,
        *,
        proposal: ResultProposal,
        created_by: str,
        target_status: str,
        units: list[dict[str, Any]],
        feedback_updates: list[dict[str, Any]],
    ) -> Mapping[str, Any]:
        try:
            value = await self._client.rpc(
                "commit_wiring_result",
                {
                    "proposal_key": proposal.proposal_id,
                    "target_project_id": str(UUID(proposal.project_id)),
                    "target_agent_run_id": str(UUID(proposal.agent_run_id)),
                    "created_by_user": str(UUID(created_by)),
                    "expected_base_version": proposal.base_result_version,
                    "target_status": target_status,
                    "profile_value": proposal.profile.model_dump(mode="json"),
                    "model_value": proposal.model.model_dump(mode="json"),
                    "units_value": units,
                    "feedback_updates": feedback_updates,
                },
            )
        except AgentServiceError as exc:
            if exc.code == ErrorCode.INVALID_REQUEST:
                raise AgentServiceError(
                    ErrorCode.BASE_VERSION_CONFLICT,
                    "The result could not be committed because its base version or scope changed.",
                    retryable=False,
                ) from exc
            raise
        if not isinstance(value, Mapping):
            raise AgentServiceError(
                ErrorCode.INTERNAL_ERROR,
                "Supabase returned an invalid result commit response.",
                retryable=False,
            )
        return value

    async def _version_payload(self, result_version_id: str) -> list[dict[str, Any]]:
        unit_rows = await self._client.select(
            "wiring_units",
            params={"result_version_id": f"eq.{result_version_id}", "order": "wire_number.asc"},
        )
        payload: list[dict[str, Any]] = []
        for row in unit_rows:
            connections = await self._client.select(
                "wiring_connections",
                params={"wiring_unit_id": f"eq.{row['id']}", "order": "core_order.asc"},
            )
            normalized_connections: list[dict[str, Any]] = []
            for connection in connections:
                evidence = await self._client.select(
                    "connection_evidence",
                    params={"connection_id": f"eq.{connection['id']}", "order": "created_at.asc"},
                )
                normalized_connections.append(
                    {
                        **{
                            key: value
                            for key, value in connection.items()
                            if key not in {"id", "wiring_unit_id"}
                        },
                        "source_connection_id": str(connection["id"]),
                        "evidence": [_evidence_payload(item) for item in evidence],
                    }
                )
            payload.append(
                {
                    "workspace_id": row["workspace_id"],
                    "drawing_id": row.get("drawing_id"),
                    "voltage_level": row.get("voltage_level"),
                    "terminal_strip": row.get("terminal_strip"),
                    "status": row["status"],
                    "needs_review": row["needs_review"],
                    "raw_payload": row.get("raw_payload") or {},
                    "connections": normalized_connections,
                }
            )
        return payload

    async def _drawing_input(
        self,
        project_id: str,
        drawing: Mapping[str, Any],
    ) -> DrawingPageInput:
        bucket = str(drawing.get("image_bucket") or "project-assets")
        object_path = str(drawing.get("image_path") or "")
        if not object_path:
            raise AgentServiceError(
                ErrorCode.SOURCE_ARTIFACT_EXPIRED,
                "The drawing image is not registered in Storage.",
                retryable=False,
            )
        destination = self._drawing_cache_root / project_id / f"{drawing['id']}.png"
        if not destination.is_file():
            content = await self._client.download(bucket=bucket, object_path=object_path)
            await asyncio.to_thread(_atomic_write, destination, content)
        drawing_page = _positive_int(drawing.get("workspace_page"))
        return DrawingPageInput(
            pdf_page_number=int(drawing["pdf_page_number"]),
            image_path=destination,
            drawing_id=str(drawing["id"]),
            storage_bucket=bucket,
            storage_path=object_path,
            drawing_page_number=drawing_page,
        )


def _search_result(row: Mapping[str, Any]) -> ConnectionSearchResult:
    return ConnectionSearchResult(
        connection_id=str(row["connection_id"]),
        project_id=str(row["project_id"]),
        project_name=str(row["project_name"]),
        workspace_id=str(row["workspace_id"]),
        workspace_name=str(row["workspace_name"]),
        workspace_page=str(row["workspace_page"]) if row.get("workspace_page") is not None else None,
        result_version_id=str(row["result_version_id"]),
        result_version=int(row["result_version"]),
        record_version=int(row.get("record_version") or 1),
        source_document_id=str(row["source_document_id"]),
        wire_number=str(row["wire_number"]) if row.get("wire_number") is not None else None,
        terminal_strip=row.get("terminal_strip"),
        start_terminal=row.get("start_terminal"),
        end_terminal=row.get("end_terminal"),
        is_cross_page=CrossPageState(str(row.get("is_cross_page") or "unknown")),
    )


def _current_record(match: ConnectionSearchResult, connection: Mapping[str, Any]) -> dict[str, Any]:
    raw = connection.get("raw_payload")
    value = dict(raw) if isinstance(raw, Mapping) else {}
    value.update(
        {
            "connection_id": match.connection_id,
            "principle_number": connection.get("principle_number"),
            "line_number": connection.get("principle_number"),
            "start_code": connection.get("start_code"),
            "start_description": connection.get("start_description"),
            "start_terminal": connection.get("start_terminal"),
            "end_code": connection.get("end_code"),
            "end_description": connection.get("end_description"),
            "end_terminal": connection.get("end_terminal"),
            "current_value": connection.get("current_value"),
            "current": connection.get("current_value"),
            "remark": connection.get("remark"),
            "color_mark": connection.get("color_mark"),
            "color": connection.get("color_mark"),
            "is_cross_page": match.is_cross_page.value,
            "start": {
                "device": connection.get("start_code"),
                "name": connection.get("start_description"),
                "terminal": connection.get("start_terminal"),
            },
            "end": {
                "device": connection.get("end_code"),
                "name": connection.get("end_description"),
                "terminal": connection.get("end_terminal"),
            },
        }
    )
    return value


def _positive_int(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _evidence_payload(item: Mapping[str, Any]) -> dict[str, Any]:
    value = {
        "drawing_id": item["drawing_id"],
        "kind": item["kind"],
        "raw_text": item.get("raw_text"),
    }
    if item.get("bbox") is not None:
        value["bbox"] = item["bbox"]
    return value


def _atomic_write(destination: Path, content: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, destination)
