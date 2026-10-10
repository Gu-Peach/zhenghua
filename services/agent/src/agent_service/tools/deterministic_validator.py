from __future__ import annotations

from typing import Any

from ..domain.models.correction import CorrectionConstraints


class DeterministicCorrectionValidator:
    def validate(
        self,
        *,
        before: list[dict[str, Any]],
        after: list[dict[str, Any]],
        constraints: CorrectionConstraints,
    ) -> list[str]:
        warnings: list[str] = []
        before_map = {_id(item): item for item in before}
        after_map = {_id(item): item for item in after}
        allowed = set(constraints.allowed_connection_ids)
        if constraints.do_not_modify_unrelated_rows and allowed:
            changed = {
                key
                for key in before_map.keys() | after_map.keys()
                if before_map.get(key) != after_map.get(key)
            }
            outside = changed - allowed
            if outside:
                raise ValueError(f"Out-of-scope records changed: {sorted(outside)}")
        if constraints.preserve_start:
            for key in before_map.keys() & after_map.keys():
                if before_map[key].get("start") != after_map[key].get("start"):
                    raise ValueError(f"Correction attempted to change preserved start for {key!r}.")
        for record in after:
            if str(record.get("status", "")).lower() == "needs_review":
                warnings.append(f"{_id(record)} requires review")
        return warnings


def _id(record: dict[str, Any]) -> str:
    value = record.get("connection_id") or record.get("id")
    if not value:
        raise ValueError("Correction records require connection_id or id.")
    return str(value)
