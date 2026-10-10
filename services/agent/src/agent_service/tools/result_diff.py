from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Literal

from ..domain.models.proposals import ProposalOperation, UnchangedAssertion


class ResultDiffTool:
    def diff(
        self,
        *,
        before: list[dict[str, Any]],
        after: list[dict[str, Any]],
        evidence_ids: list[str],
        record_versions: Mapping[str, int],
        allowed_connection_ids: list[str],
        allowed_fields: list[str],
        reason: str,
    ) -> list[ProposalOperation]:
        before_map = {_record_id(item): item for item in before}
        after_map = {_record_id(item): item for item in after}
        allowed_ids = set(allowed_connection_ids)
        operations: list[ProposalOperation] = []
        for target_id in sorted(before_map.keys() | after_map.keys()):
            if allowed_ids and target_id not in allowed_ids:
                if before_map.get(target_id) != after_map.get(target_id):
                    raise ValueError(f"Correction changed out-of-scope connection {target_id!r}.")
                continue
            old = before_map.get(target_id)
            new = after_map.get(target_id)
            if old == new:
                continue
            op: Literal["add", "replace", "remove"]
            if old is not None and new is not None:
                changed = _changed_fields(old, new)
                if allowed_fields and not changed.issubset(set(allowed_fields)):
                    outside = sorted(changed - set(allowed_fields))
                    raise ValueError(f"Correction changed fields outside allowlist: {outside}")
                op = "replace"
            elif old is None:
                op = "add"
            else:
                op = "remove"
            operations.append(
                ProposalOperation(
                    op=op,
                    target_type="CONNECTION",
                    target_id=target_id,
                    expected_version=record_versions.get(target_id),
                    before=old,
                    after=new,
                    evidence_ids=evidence_ids,
                    reason=reason,
                    confidence=_confidence(new or old or {}),
                )
            )
        return operations

    def unchanged_assertion(
        self,
        *,
        scope: str,
        records: list[dict[str, Any]],
    ) -> UnchangedAssertion:
        ordered = sorted(records, key=_record_id)
        digest = hashlib.sha256(
            json.dumps(ordered, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return UnchangedAssertion(
            scope=scope,
            connection_ids=[_record_id(item) for item in ordered],
            hash=f"sha256:{digest}",
        )


def _record_id(record: Mapping[str, Any]) -> str:
    value = record.get("connection_id") or record.get("id")
    if not value:
        raise ValueError("Correction records require connection_id or id.")
    return str(value)


def _changed_fields(before: Mapping[str, Any], after: Mapping[str, Any]) -> set[str]:
    return {
        key
        for key in before.keys() | after.keys()
        if before.get(key) != after.get(key) and key not in {"confidence", "source_note", "status"}
    }


def _confidence(record: Mapping[str, Any]) -> float:
    try:
        return max(0.0, min(1.0, float(record.get("confidence", 0.8))))
    except (TypeError, ValueError):
        return 0.8
