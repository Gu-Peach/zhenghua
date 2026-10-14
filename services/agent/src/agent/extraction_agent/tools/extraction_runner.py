from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from copy import deepcopy
from functools import partial
from typing import Any, TypeVar

from src.agent.extraction_agent.agents.page_classifier import PageClassifierAgent
from src.agent.extraction_agent.agents.page_scanner import PageScannerAgent
from src.agent.extraction_agent.application.extraction_stage_dispatcher import ProfileBoundStageDispatcher
from src.application.run_control import RunEventPublisher
from src.domain.enums import AgentStage, CorrectionAction, ErrorCode, EventType, ScopeType
from src.domain.errors import AgentServiceError
from src.domain.models.common import StrictModel
from src.domain.models.correction import CorrectionEvidenceBundle, CorrectionPlan
from src.agent.extraction_agent.domain.models.extraction_stages import (
    CrossPageCompletionRequest,
    CrossPageCompletionResult,
    DrawingPageInput,
    PageClassificationResult,
    PageScanResult,
)
from src.domain.models.runs import AgentRun
from src.domain.ports import ArtifactRepository
from src.agent.extraction_agent.graphs.extraction import run_page_classification, run_page_scan
from src.agent.extraction_agent.graphs.extraction.page_scan import complete_page_connection
from src.harness.stores import CancellationToken

T = TypeVar("T", bound=StrictModel)


class ScopedExtractionRunner:
    def __init__(
        self,
        stages: ProfileBoundStageDispatcher,
        *,
        artifacts: ArtifactRepository | None = None,
        publisher: RunEventPublisher | None = None,
        materialize: Callable[[DrawingPageInput], Awaitable[DrawingPageInput]] | None = None,
    ) -> None:
        self._classifier = PageClassifierAgent(stages=stages)
        self._scanner = PageScannerAgent(stages=stages)
        self._artifacts = artifacts
        self._publisher = publisher
        self._materialize = materialize

    async def _step(
        self,
        run: AgentRun | None,
        stage: AgentStage,
        key: str,
        request: StrictModel,
        model: type[T],
        call: Callable[[], Awaitable[T]],
        cancellation: CancellationToken | None,
    ) -> T:
        if cancellation:
            cancellation.raise_if_cancelled()
        artifact_id = f"{run.agent_run_id}:correction-stage:{stage.value}:{key}" if run else ""
        if self._artifacts and run:
            cached = await self._artifacts.get(artifact_id)
            if cached:
                return model.model_validate(cached["result"])
        if self._publisher and run:
            await self._publisher.publish(
                run, EventType.STAGE_STARTED, stage=stage, message=f"纠错 {stage.value} 正在执行。"
            )
        result = await call()
        if cancellation:
            cancellation.raise_if_cancelled()
        if self._artifacts and run:
            await self._artifacts.put(
                artifact_id,
                {
                    "artifact_id": artifact_id,
                    "agent_run_id": run.agent_run_id,
                    "kind": "correction_stage_item",
                    "stage": stage.value,
                    "item_id": key,
                    "request": request.model_dump(mode="json"),
                    "result": result.model_dump(mode="json"),
                },
            )
        if self._publisher and run:
            await self._publisher.publish(
                run,
                EventType.STAGE_COMPLETED,
                stage=stage,
                message=f"纠错 {stage.value} 已持久化。",
                artifact_refs=[artifact_id] if self._artifacts else [],
            )
        return result

    async def run(
        self,
        plan: CorrectionPlan,
        bundle: CorrectionEvidenceBundle,
        *,
        run: AgentRun | None = None,
        cancellation: CancellationToken | None = None,
    ) -> list[dict[str, Any]]:
        records = deepcopy(bundle.current_records)
        if plan.action == CorrectionAction.RERUN_STAGE_1:
            for classification_request in bundle.page_classification_requests:
                await self._step(
                    run,
                    AgentStage.PAGE_CLASSIFICATION,
                    bundle.facts.feedback_id,
                    classification_request,
                    PageClassificationResult,
                    partial(run_page_classification, agent=self._classifier, request=classification_request),
                    cancellation,
                )
        if plan.action in {
            CorrectionAction.RERUN_STAGE_1,
            CorrectionAction.RERUN_STAGE_2,
            CorrectionAction.RERUN_STAGE_2_AND_3,
        }:
            scanned: list[dict[str, Any]] = []
            for original in bundle.page_scan_requests:
                scan_request = original.model_copy(
                    update={
                        "run_id": run.agent_run_id if run else original.run_id,
                        "page_context": json.dumps(
                            {
                                "task": "scoped_correction_reextract",
                                "original_context": original.page_context,
                                "correction": bundle.context.model_dump(mode="json"),
                            },
                            ensure_ascii=False,
                        ),
                    }
                )
                scan_result = await self._step(
                    run,
                    AgentStage.PAGE_SCAN,
                    f"{bundle.facts.feedback_id}:{scan_request.page.pdf_page_number}",
                    scan_request,
                    PageScanResult,
                    partial(run_page_scan, agent=self._scanner, request=scan_request),
                    cancellation,
                )
                for unit in scan_result.units:
                    for connection in unit.connections:
                        value = connection.model_dump(mode="json", exclude_none=False)
                        if not value.get("connection_id"):
                            value["connection_id"] = connection.local_connection_id
                        scanned.append(value)
            allowed_ids = bundle.context.constraints.allowed_connection_ids
            if not allowed_ids:
                if plan.target.type != ScopeType.CONNECTION:
                    raise ValueError(
                        "Drawing/workspace corrections require an explicit connection allowlist."
                    )
                allowed_ids = [plan.target.id]
            records = _replace_scoped(
                records, scanned, allowed_ids, bundle.context.constraints.allowed_fields
            )
        if plan.action in {
            CorrectionAction.RERUN_STAGE_1,
            CorrectionAction.RERUN_STAGE_2,
            CorrectionAction.RERUN_STAGE_2_AND_3,
        }:
            allowed_ids = bundle.context.constraints.allowed_connection_ids or [plan.target.id]
            cross_page_ids = {
                _id(record)
                for record in records
                if str(record.get("is_cross_page", "unknown")) == "cross_page"
            }
            cross_requests = list(bundle.cross_page_requests)
            if bundle.available_pages:
                cross_requests = []
                for record in records:
                    if _id(record) not in cross_page_ids or _id(record) not in allowed_ids:
                        continue
                    references = record.get("references") or []
                    for index, reference in enumerate(references):
                        candidates = [
                            page
                            for page in bundle.available_pages
                            if (
                                reference.get("target_pdf_page") == page.pdf_page_number
                                if reference.get("target_pdf_page")
                                else str(reference.get("target_function") or "").strip("=").upper()
                                == str(page.plant_function or "").strip("=").upper()
                                and reference.get("target_drawing_page") == page.drawing_page_number
                            )
                        ]
                        if len(candidates) != 1 or reference.get("external"):
                            record["status"] = "needs_review"
                            continue
                        page = candidates[0]
                        if self._materialize:
                            page = await self._materialize(page)
                        task_id = f"{bundle.facts.feedback_id}:{_id(record)}:{index}"
                        bundle.cross_page_task_targets[task_id] = _id(record)
                        cross_requests.append(
                            CrossPageCompletionRequest(
                                run_id=run.agent_run_id if run else bundle.facts.feedback_id,
                                project_id=bundle.facts.target.project_id,
                                profile=bundle.profile,
                                task_id=task_id,
                                target_page=page,
                                task_context=json.dumps(
                                    {"connection": record, "reference": reference}, ensure_ascii=False
                                ),
                            )
                        )
                    if not references:
                        record["status"] = "needs_review"
            if self._artifacts and run:
                task_artifact_id = f"{run.agent_run_id}:correction-tasks:{bundle.facts.feedback_id}"
                await self._artifacts.put(
                    task_artifact_id,
                    {
                        "artifact_id": task_artifact_id,
                        "agent_run_id": run.agent_run_id,
                        "kind": "correction_task_manifest",
                        "requests": [request.model_dump(mode="json") for request in cross_requests],
                    },
                )
                stored = await self._artifacts.get(task_artifact_id)
                assert stored is not None
                cross_requests = [
                    CrossPageCompletionRequest.model_validate(value) for value in stored["requests"]
                ]
            for cross_page_request in cross_requests:
                if self._materialize:
                    cross_page_request = cross_page_request.model_copy(
                        update={"target_page": await self._materialize(cross_page_request.target_page)}
                    )
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
                record = next(item for item in records if _id(item) == target_id)
                source = cross_page_request.source_page
                if source is None:
                    candidates = [
                        request.page
                        for request in bundle.page_scan_requests
                        if request.page.pdf_page_number == record.get("origin_pdf_page")
                        or request.page.drawing_id == record.get("drawing_id")
                        and request.page.drawing_id is not None
                    ]
                    if not candidates and len(bundle.page_scan_requests) == 1:
                        candidates = [bundle.page_scan_requests[0].page]
                    source = candidates[0] if len(candidates) == 1 else None
                if source is not None and self._materialize:
                    source = await self._materialize(source)
                cross_page_request = cross_page_request.model_copy(
                    update={
                        "source_page": source,
                        "run_id": run.agent_run_id if run else cross_page_request.run_id,
                        "task_context": json.dumps(
                            {
                                "task": "scoped_correction_reextract",
                                "original_context": cross_page_request.task_context,
                                "stage2_record": next(item for item in records if _id(item) == target_id),
                                "correction": bundle.context.model_dump(mode="json"),
                            },
                            ensure_ascii=False,
                        ),
                    }
                )
                completion_result = await self._step(
                    run,
                    AgentStage.PAGE_SCAN,
                    f"complete:{cross_page_request.task_id}",
                    cross_page_request,
                    CrossPageCompletionResult,
                    partial(complete_page_connection, agent=self._scanner, request=cross_page_request),
                    cancellation,
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
                    end = completion_result.end
                    if end:
                        target["end_code"] = end.device
                        target["end_description"] = end.name
                        target["end_terminal"] = end.terminal
        return records


def _replace_scoped(
    existing: list[dict[str, Any]],
    scanned: list[dict[str, Any]],
    allowed_ids: list[str],
    allowed_fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Map page-local outputs to frozen DB targets using semantic source fields."""
    allowed = set(allowed_ids)
    originals = {_id(item): item for item in existing if _id(item) in allowed}
    if not allowed or set(originals) != allowed:
        raise AgentServiceError(ErrorCode.INVALID_REQUEST, "纠错目标不在冻结的原始记录中。")
    replacements: dict[str, dict[str, Any]] = {}
    for source in scanned:
        record = deepcopy(source)
        connection_id = _id(record)
        original = originals.get(connection_id)
        # Preserve compatibility with ID-bound records that have no source evidence.
        # If evidence exists, a model-supplied DB ID must not override a mismatch.
        if original is not None and _start_identity(original) == (None, None, None, None):
            matches = [connection_id]
        else:
            matches = [key for key, item in originals.items() if _same_start(item, record)]
        if len(matches) > 1:
            raise AgentServiceError(
                ErrorCode.MODEL_SCHEMA_INVALID, "Stage 2 起点对应多个纠错目标，需人工确认。"
            )
        if not matches:
            continue  # Other connections on the same page are not correction targets.
        connection_id = matches[0]
        record["connection_id"] = connection_id
        if connection_id in replacements:
            raise AgentServiceError(
                ErrorCode.MODEL_SCHEMA_INVALID, "Stage 2 重复返回同一纠错起点，需人工确认。"
            )
        original = originals[connection_id]
        if allowed_fields:
            replacement = deepcopy(original)
            for internal in ("references", "is_cross_page", "status", "confidence"):
                if internal in record:
                    replacement[internal] = record[internal]
            for field in allowed_fields:
                if field in record:
                    replacement[field] = record[field]
                elif field.startswith(("start_", "end_")):
                    side, name = field.split("_", 1)
                    endpoint = record.get(side) or {}
                    replacement[field] = endpoint.get(
                        {"code": "device", "description": "name"}.get(name, name)
                    )
            replacements[connection_id] = replacement
        else:
            replacement = {**original, **record, "start": original.get("start")}
            end = record.get("end") or {}
            for field, attribute in (
                ("end_code", "device"),
                ("end_description", "name"),
                ("end_terminal", "terminal"),
            ):
                replacement[field] = end.get(attribute)
            if "current" in record:
                replacement["current_value"] = record["current"]
            if "line_number" in record:
                replacement["principle_number"] = record["line_number"]
            replacements[connection_id] = replacement
    if allowed - replacements.keys():
        raise AgentServiceError(
            ErrorCode.MODEL_SCHEMA_INVALID,
            "Stage 2 未找到全部目标起点，或设备/位置/端子不一致；未生成修订，请核对图纸。",
        )
    return [replacements.get(_id(item), deepcopy(item)) for item in existing]


def _start_identity(record: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    """start_code is a display projection (often location), not always a device."""
    start = record.get("start") or {}
    code = _identity_text(record.get("start_code"))
    nested_device = _identity_text(start.get("device"))
    location = _identity_text(record.get("start_location") or start.get("location"))
    if not location:
        location = next((v for v in (code, nested_device) if v and v.startswith("+")), None)
    device = _identity_text(record.get("start_device"))
    if not device:
        device = next(
            (v for v in (nested_device, code) if v and v != location and not v.startswith("+")), None
        )
    device = device.lstrip("-") if device else None
    board = _identity_text(record.get("start_terminal_board") or start.get("terminal_board"))
    board = board.lstrip("-") if board else None
    terminal = _identity_text(record.get("start_terminal")) or _identity_text(start.get("terminal"))
    if terminal and ":" in terminal:
        qualified_board, terminal = terminal.rsplit(":", 1)
        qualified_board = qualified_board.lstrip("-")
        if board and board != qualified_board:
            raise AgentServiceError(ErrorCode.MODEL_SCHEMA_INVALID, "Stage 2 起点端子排与端子名称不一致。")
        board = qualified_board
    return location, device, board, terminal


def _same_start(original: dict[str, Any], scanned: dict[str, Any]) -> bool:
    left, right = _start_identity(original), _start_identity(scanned)
    if not left[3] or not right[3] or left[3] != right[3]:
        return False
    if left[0] and not right[0]:
        return False  # A known location cannot be inferred from a bare terminal.
    if any(a and b and a != b for a, b in zip(left[:3], right[:3], strict=True)):
        return False
    return any(a and b and a == b for a, b in zip(left[1:3], right[1:3], strict=True))


def _identity_text(value: Any) -> str | None:
    return "".join(str(value).split()).upper() if value is not None and str(value).strip() else None


def _id(record: dict[str, Any]) -> str:
    return str(record.get("connection_id") or record.get("id") or "")
