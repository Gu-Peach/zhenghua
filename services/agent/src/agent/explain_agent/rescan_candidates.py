"""Conservative identity matching and field masks, independent of models and storage."""

from __future__ import annotations

import math
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from .models import RescanCandidate, RescanChange, RescanFields


def match_score(old: dict[str, Any], new: dict[str, Any]) -> int:
    if old["source_pdf_page_number"] != new["source_pdf_page_number"]:
        return 0
    score = (
        4 if old.get("principle_number") and old.get("principle_number") == new.get("principle_number") else 0
    )
    score += sum(
        2 for key in ("start_terminal", "end_terminal") if old.get(key) and old.get(key) == new.get(key)
    )
    old_points = [old.get(key) for key in ("start_terminal_coordinates", "end_terminal_coordinates")]
    new_points = [new.get(key) for key in ("start_terminal_coordinates", "end_terminal_coordinates")]
    if any(
        a
        and b
        and a["pdf_page_number"] == b["pdf_page_number"]
        and math.hypot(a["x"] - b["x"], a["y"] - b["y"]) < 0.025
        for a in old_points
        for b in new_points
    ):
        score += 5
    return score


def build_candidate(
    job: dict[str, Any], scanned: list[dict[str, Any]], warnings: list[str]
) -> RescanCandidate:
    baseline = job["baseline"]
    choices: dict[str, int] = {}
    uncertain: set[int] = set()
    for old in baseline:
        scores = sorted(((match_score(old, new), i) for i, new in enumerate(scanned)), reverse=True)
        if scores and scores[0][0] >= 4:
            if len(scores) > 1 and scores[0][0] == scores[1][0]:
                uncertain.update(i for score, i in scores if score == scores[0][0])
            else:
                choices[old["id"]] = scores[0][1]
    repeated = {index for index in choices.values() if list(choices.values()).count(index) > 1}
    uncertain.update(repeated)
    choices = {identifier: index for identifier, index in choices.items() if index not in uncertain}
    changes = []
    fields_mode = job["request"]["fields"]
    for old in baseline:
        if old["id"] not in choices:
            continue
        new = scanned[choices[old["id"]]]
        if fields_mode in {"start", "end"}:
            opposite = "start" if fields_mode == "end" else "end"
            a, b = old.get(f"{opposite}_terminal_coordinates"), new.get(f"{opposite}_terminal_coordinates")
            same_pin = bool(
                a
                and b
                and a["pdf_page_number"] == b["pdf_page_number"]
                and math.hypot(a["x"] - b["x"], a["y"] - b["y"]) < 0.025
            )
            if (
                old.get(f"{opposite}_terminal")
                and new.get(f"{opposite}_terminal")
                and old[f"{opposite}_terminal"] != new[f"{opposite}_terminal"]
                and not same_pin
            ):
                choices.pop(old["id"])
                warnings.append("扫描中的冻结对端与现有记录不一致，该行保持原值；请核对方向或整条连接重扫。")
                continue
        new = dict(new)
        new["needs_review"] = bool(new.get("needs_review")) or any(
            not new.get(f"{side}_terminal") or not new.get(f"{side}_terminal_coordinates")
            for side in ("start", "end")
        )
        allowed = set(RescanFields.model_fields)
        if fields_mode == "end":
            allowed = {
                key
                for key in allowed
                if key.startswith("end_")
                or key in {"needs_review", "target_pdf_page_number", "target_drawing_page", "is_cross_page"}
            }
        elif fields_mode == "start":
            allowed = {key for key in allowed if key.startswith("start_") or key == "needs_review"}
        values = {key: new[key] for key in allowed if key in new and new[key] != old.get(key)}
        # Never keep a previous pin when a newly read terminal has no reliable position.
        for side in ("start", "end"):
            if f"{side}_terminal" in values and f"{side}_terminal_coordinates" in allowed:
                values[f"{side}_terminal_coordinates"] = new.get(f"{side}_terminal_coordinates")
        evidence = dict(new.get("evidence", {}))
        retained_reasons = (
            []
            if fields_mode == "all"
            else [
                reason
                for reason in (old.get("evidence") or {}).get("review_reasons", [])
                if not str(reason.get("field", "")).startswith(fields_mode)
            ]
        )
        evidence["review_reasons"] = [*retained_reasons, *evidence.get("review_reasons", [])]
        final = {**old, **values}
        missing = any(
            not final.get(f"{side}_terminal") or not final.get(f"{side}_terminal_coordinates")
            for side in ("start", "end")
        )
        if (missing or retained_reasons) and not final.get("needs_review"):
            values["needs_review"] = True
        if values:
            changes.append(
                RescanChange(
                    action="update",
                    connection_id=old["id"],
                    record_version=old["record_version"],
                    source_pdf_page_number=old["source_pdf_page_number"],
                    source_drawing_page=old.get("source_drawing_page"),
                    workspace_code=old.get("workspace_code"),
                    principle_number=old.get("principle_number"),
                    before={key: old.get(key) for key in values},
                    after=RescanFields.model_validate(values),
                    evidence=evidence,
                )
            )
    row_scoped = bool(
        job["request"]["scope"].get("connection_ids") or job["request"]["scope"].get("principle_numbers")
    )
    used = set(choices.values()) | uncertain
    if not row_scoped and fields_mode == "all":
        for index, new in enumerate(scanned):
            if index in used:
                continue
            values = {key: new[key] for key in RescanFields.model_fields if key in new}
            values["needs_review"] = bool(new.get("needs_review")) or any(
                not new.get(f"{side}_terminal") or not new.get(f"{side}_terminal_coordinates")
                for side in ("start", "end")
            )
            changes.append(
                RescanChange(
                    action="insert",
                    connection_id=uuid5(NAMESPACE_URL, f"rescan-new:{job['id']}:{index}"),
                    record_version=0,
                    source_pdf_page_number=new["source_pdf_page_number"],
                    source_drawing_page=new.get("source_drawing_page"),
                    workspace_code=new.get("workspace_code"),
                    principle_number=new.get("principle_number"),
                    after=RescanFields.model_validate(values),
                    evidence=new.get("evidence", {}),
                )
            )
    unmatched = [old["id"] for old in baseline if old["id"] not in choices]
    if unmatched:
        warnings = [*warnings, f"{len(unmatched)}条原记录无法唯一匹配，保持原值；不会按未识别自动删除。"]
    return RescanCandidate(
        changes=changes, warnings=list(dict.fromkeys(warnings))[:1000], unmatched_ids=unmatched
    )
