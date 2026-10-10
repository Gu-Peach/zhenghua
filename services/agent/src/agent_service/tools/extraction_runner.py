from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..agents.cross_page_resolver import CrossPageResolverAgent
from ..agents.page_classifier import PageClassifierAgent
from ..agents.page_scanner import PageScannerAgent
from ..application.extraction_stage_dispatcher import ProfileBoundStageDispatcher
from ..domain.enums import CorrectionAction, ScopeType
from ..domain.models.correction import CorrectionEvidenceBundle, CorrectionPlan
from ..graphs.extraction import run_cross_page_completion, run_page_classification, run_page_scan


class ScopedExtractionRunner:
    def __init__(self, stages: ProfileBoundStageDispatcher) -> None:
        self._classifier = PageClassifierAgent(stages=stages)
        self._scanner = PageScannerAgent(stages=stages)
        self._resolver = CrossPageResolverAgent(stages=stages)

    async def run(
        self,
        plan: CorrectionPlan,
        bundle: CorrectionEvidenceBundle,
    ) -> list[dict[str, Any]]:
        records = deepcopy(bundle.current_records)
        if plan.action == CorrectionAction.RERUN_STAGE_1:
            for classification_request in bundle.page_classification_requests:
                await run_page_classification(
                    agent=self._classifier,
                    request=classification_request,
                )
        if plan.action in {
            CorrectionAction.RERUN_STAGE_1,
            CorrectionAction.RERUN_STAGE_2,
            CorrectionAction.RERUN_STAGE_2_AND_3,
        }:
            scanned: list[dict[str, Any]] = []
            for scan_request in bundle.page_scan_requests:
                scan_result = await run_page_scan(agent=self._scanner, request=scan_request)
                for unit in scan_result.units:
                    for connection in unit.connections:
                        value = connection.model_dump(mode="json", exclude_none=False)
                        if not value.get("connection_id"):
                            value["connection_id"] = connection.local_connection_id
                        scanned.append(value)
            if scanned:
                allowed_ids = bundle.context.constraints.allowed_connection_ids
                if not allowed_ids:
                    if plan.target.type != ScopeType.CONNECTION:
                        raise ValueError(
                            "Drawing/workspace corrections require an explicit connection allowlist."
                        )
                    allowed_ids = [plan.target.id]
                records = _replace_scoped(records, scanned, allowed_ids)
        if plan.action in {CorrectionAction.RERUN_STAGE_1, CorrectionAction.RERUN_STAGE_2_AND_3}:
            allowed_ids = bundle.context.constraints.allowed_connection_ids or [plan.target.id]
            cross_page_ids = {
                _id(record)
                for record in records
                if str(record.get("is_cross_page", "unknown")) == "cross_page"
            }
            for cross_page_request in bundle.cross_page_requests:
                target_id = bundle.cross_page_task_targets.get(cross_page_request.task_id)
                if target_id is None and cross_page_request.task_id in allowed_ids:
                    target_id = cross_page_request.task_id
                if target_id is not None and target_id not in allowed_ids:
                    raise ValueError(
                        f"Cross-page task {cross_page_request.task_id!r} maps outside "
                        "the correction allowlist."
                    )
                if target_id is None and len(allowed_ids) == 1:
                    target_id = allowed_ids[0]
                if target_id is None:
                    raise ValueError(
                        f"Cross-page task {cross_page_request.task_id!r} is outside the correction allowlist."
                    )
                if target_id not in cross_page_ids:
                    continue
                completion_result = await run_cross_page_completion(
                    agent=self._resolver,
                    request=cross_page_request,
                )
                target = next((item for item in records if _id(item) == target_id), None)
                if target is not None:
                    target["end"] = (
                        completion_result.end.model_dump(mode="json") if completion_result.end else None
                    )
                    target["intermediate_points"] = [
                        item.model_dump(mode="json") for item in completion_result.intermediate_points
                    ]
                    target["status"] = completion_result.status
                    target["confidence"] = completion_result.confidence
        return records


def _replace_scoped(
    existing: list[dict[str, Any]],
    scanned: list[dict[str, Any]],
    allowed_ids: list[str],
) -> list[dict[str, Any]]:
    allowed = set(allowed_ids)
    if len(allowed) == 1 and len(scanned) == 1:
        scanned[0]["connection_id"] = next(iter(allowed))
    replacements: dict[str, dict[str, Any]] = {}
    for record in scanned:
        connection_id = _id(record)
        if not connection_id and len(allowed) == 1 and len(scanned) == 1:
            connection_id = next(iter(allowed))
            record["connection_id"] = connection_id
        if connection_id not in allowed:
            raise ValueError(f"Page scan returned out-of-scope connection {connection_id!r}.")
        if connection_id in replacements:
            raise ValueError(f"Page scan returned duplicate connection {connection_id!r}.")
        replacements[connection_id] = record
    output = [replacements.pop(_id(item), item) for item in existing]
    if replacements:
        output.extend(replacements[key] for key in sorted(replacements))
    return output


def _id(record: dict[str, Any]) -> str:
    return str(record.get("connection_id") or record.get("id") or "")
