from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from ..domain.enums import ScopeType
from ..domain.models.profiles import ProfileBinding
from ..domain.models.proposals import (
    ProposalOperation,
    ProposalValidation,
    ResultProposal,
    UnchangedAssertion,
)
from ..domain.models.runs import ModelRef, RunScope


def build_extraction_result_proposal(
    *,
    agent_run_id: str,
    project_id: str,
    source_document_id: str,
    base_result_version: int,
    profile: ProfileBinding,
    model_name: str,
    state: Mapping[str, Any],
    validation_warnings: list[str],
) -> ResultProposal:
    records = _records_from_state(state)
    operations = [
        ProposalOperation(
            op="add",
            target_type="CONNECTION",
            target_id=_record_id(record, index),
            after=record,
            evidence_ids=_evidence_ids(source_document_id, record),
            reason="三阶段提取与确定性校验生成的候选连接。",
            confidence=_confidence(record),
        )
        for index, record in enumerate(records, start=1)
    ]
    needs_review = any(_needs_review(record) for record in records)
    digest = hashlib.sha256(
        json.dumps(records, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return ResultProposal(
        proposal_id=f"{agent_run_id}:result-proposal",
        agent_run_id=agent_run_id,
        project_id=project_id,
        base_result_version=base_result_version,
        profile=profile.profile,
        model=ModelRef(name=model_name),
        scope=RunScope(type=ScopeType.PROJECT, id=project_id),
        operations=operations,
        unchanged_assertions=[
            UnchangedAssertion(
                scope=project_id,
                connection_ids=[],
                hash=f"sha256:{digest}",
            )
        ],
        validation=ProposalValidation(
            schema_valid=True,
            business_rules_valid=not validation_warnings,
            warnings=list(validation_warnings),
        ),
        status=(
            "NEEDS_REVIEW" if needs_review or validation_warnings or not operations else "READY_FOR_REVIEW"
        ),
    )


def _records_from_state(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    raw_groups = state.get("wiring_records") or {}
    if not isinstance(raw_groups, Mapping):
        return records
    for group_id in sorted(str(key) for key in raw_groups):
        group = raw_groups.get(group_id) or []
        for raw in group:
            if hasattr(raw, "model_dump"):
                value = raw.model_dump(mode="json", exclude_none=False)
            elif isinstance(raw, Mapping):
                value = dict(raw)
            else:
                continue
            value.setdefault("group_id", group_id)
            records.append(value)
    return records


def _record_id(record: Mapping[str, Any], index: int) -> str:
    existing = record.get("connection_id") or record.get("local_connection_id")
    if existing:
        return str(existing)
    fingerprint = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
    return f"extracted-{index:06d}-{hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()[:12]}"


def _evidence_ids(source_document_id: str, record: Mapping[str, Any]) -> list[str]:
    pages = record.get("source_pages") or []
    values = [
        f"document:{source_document_id}:pdf-page:{int(page)}"
        for page in pages
        if str(page).isdigit() and int(page) > 0
    ]
    return values or [f"document:{source_document_id}"]


def _confidence(record: Mapping[str, Any]) -> float:
    try:
        return max(0.0, min(1.0, float(record.get("confidence", 0.5))))
    except (TypeError, ValueError):
        return 0.5


def _needs_review(record: Mapping[str, Any]) -> bool:
    return str(record.get("status", "")).lower() == "needs_review" or bool(
        record.get("external_source_required")
    )
