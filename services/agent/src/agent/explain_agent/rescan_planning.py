"""Validate task capabilities and acceptance coverage independently of model narration."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .models import RescanCandidate, RescanRequest


class RescanPlanError(ValueError):
    def __init__(self, message: str, code: str = "RESCAN_PLAN_INCOMPATIBLE") -> None:
        super().__init__(message)
        self.code = code


def pin_identity(value: Any) -> str:
    return str(value or "").strip().casefold()


def validate_requirements(request: RescanRequest, rows: list[dict[str, Any]] | None = None) -> None:
    """Never broaden write permissions or silently omit requested starts to fit an operation."""
    requirements = request.requirements
    if requirements is None:
        return  # Persisted tasks and public DTOs created before this contract remain readable.
    supported = (
        {"start_terminal", "end_terminal", "principle_number"}
        if request.fields == "all"
        else {f"{request.fields}_terminal"}
    )
    if set(requirements.required_fields) - supported:
        raise RescanPlanError(
            "所需字段超出当前修改权限；要求原理号或两端字段时请使用fields=all，不得只写进instructions。"
        )
    row_scoped = bool(request.scope.connection_ids or request.scope.principle_numbers)
    if requirements.connection_set == "rebuild" and (request.fields != "all" or row_scoped):
        raise RescanPlanError(
            "重建连接集合必须使用整页/工作区fields=all范围，不得截取已有行ID；缺失起点需要完整页提取候选。"
        )
    if request.fields == "all" and not row_scoped and requirements.connection_set != "rebuild":
        raise RescanPlanError(
            "整页all会生成范围替换候选，必须明确connection_set=rebuild；只保留旧行时请指定行ID。"
        )
    if (
        rows is not None
        and requirements.expected_start_terminals
        and requirements.connection_set == "preserve"
    ):
        expected = Counter(map(pin_identity, requirements.expected_start_terminals))
        actual = Counter(pin_identity(row.get("start_terminal")) for row in rows)
        if expected != actual:
            raise RescanPlanError(
                "预期起点与当前选中行不完整对应，请重新检索范围；存在漏提/多提时使用整页重建候选，不得省略或编造行ID。",
                "RESCAN_SCOPE_INCOMPLETE",
            )


def require_tool_requirements(schema: dict[str, Any], request_schema: dict[str, Any]) -> None:
    """The model must state intent, while historical API payloads may omit it."""
    request_schema["properties"].pop("result_mode", None)
    request_schema["properties"]["requirements"] = {"$ref": "#/$defs/RescanRequirements"}
    request_schema["required"] = list(dict.fromkeys([*request_schema.get("required", []), "requirements"]))
    requirement_schema = schema["$defs"]["RescanRequirements"]
    requirement_schema["required"] = list(requirement_schema["properties"])


def freeze_same_page_matches(
    baseline: list[dict[str, Any]], scanned: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Only a unique observed source pin can be mapped to a trusted old ID; never use a nearby end."""
    matches = []
    proposals = []
    for old in baseline:
        selected = [
            (i, row)
            for i, row in enumerate(scanned)
            if row["source_pdf_page_number"] == old.get("_scan_pdf_page", old["source_pdf_page_number"])
            and pin_identity(row.get("start_terminal")) == pin_identity(old.get("start_terminal"))
            and old.get("start_terminal")
            and not (
                old.get("start_code") and row.get("start_code") and old["start_code"] != row["start_code"]
            )
        ]
        if len(selected) != 1:
            continue
        index, row = selected[0]
        proposals.append((index, old, row))
    counts = Counter(index for index, _, _ in proposals)
    for index, old, row in proposals:
        if counts[index] != 1:
            continue
        frozen = {**row, "id": old["id"]}
        read_page = row["source_pdf_page_number"]
        frozen.update(
            target_pdf_page_number=read_page if read_page != old["source_pdf_page_number"] else None,
            target_drawing_page=row.get("source_drawing_page")
            if read_page != old["source_pdf_page_number"]
            else None,
            is_cross_page=read_page != old["source_pdf_page_number"],
        )
        for key, value in old.items():
            if key.startswith("start_") or key in {
                "source_pdf_page_number",
                "source_drawing_page",
                "workspace_code",
                "principle_number",
            }:
                frozen[key] = value
        matches.append(frozen)
    return matches


def check_candidate_requirements(job: dict[str, Any], candidate: RescanCandidate) -> RescanCandidate:
    """Report unmet requirements without turning expectations into extraction values."""
    request = RescanRequest.model_validate(job["request"])
    requirements = request.requirements
    if requirements is None:
        return candidate
    baseline = {str(row["id"]): row for row in job["baseline"]}
    if request.resolved_mode() == "replace_scope":
        final = [change.after.model_dump(mode="json", exclude_unset=True) for change in candidate.changes]
    else:
        final_by_id = {key: dict(row) for key, row in baseline.items()}
        for change in candidate.changes:
            final_by_id[str(change.connection_id)] = {
                **final_by_id.get(str(change.connection_id), {}),
                **change.after.model_dump(mode="json", exclude_unset=True),
            }
        final = list(final_by_id.values())
    gaps = []
    if requirements.expected_start_terminals:
        names = {pin_identity(value): value for value in requirements.expected_start_terminals}
        expected = Counter(map(pin_identity, requirements.expected_start_terminals))
        actual = Counter(pin_identity(row.get("start_terminal")) for row in final)
        missing = list((expected - actual).elements())
        extra = list((actual - expected).elements())
        if missing:
            gaps.append("未识别到预期起点：" + "、".join(names[value] for value in missing))
        if extra:
            gaps.append("提取起点集合存在多提或重复，请复核：" + "、".join(extra))
    labels = {"start_terminal": "起点端子", "end_terminal": "终点端子", "principle_number": "原理号"}
    for field in requirements.required_fields:
        count = sum(not row.get(field) for row in final)
        if count:
            gaps.append(f"所需{labels[field]}仍有{count}条未确认")
    if candidate.unmatched_ids:
        gaps.append(f"仍有{len(candidate.unmatched_ids)}条连接未完成识别或无法唯一匹配")
    if gaps:
        candidate.warnings = list(dict.fromkeys([*candidate.warnings, *gaps]))
        for change in candidate.changes:
            if change.action == "update":
                change.before.setdefault(
                    "needs_review", baseline[str(change.connection_id)].get("needs_review", False)
                )
            change.after.needs_review = True
            change.evidence["review_reasons"] = [
                *change.evidence.get("review_reasons", []),
                {"code": "rescan_requirements_unmet", "field": "requirements", "message": "；".join(gaps)},
            ]
    return candidate
