"""Resolve explicit business pages inside the immutable job catalog, never from prose."""

import re
from typing import Any

from .models import RescanTargetBinding


class RescanTargetError(ValueError):
    """A safe, actionable target-selection error suitable for the job status."""


def normalized(value: Any) -> str:
    return re.sub(r"[\W_]+", "", str(value or "").casefold())


def resolve_target_page(binding: RescanTargetBinding, metadata: dict[int, dict[str, Any]]) -> int:
    """Resolve all explicit constraints, distinguishing absent, conflicting and ambiguous targets."""
    named = {
        number: page
        for number, page in metadata.items()
        if normalized(page.get("workspace_page")) == normalized(binding.drawing_page)
    }
    if not named:
        raise RescanTargetError(f"目标页{binding.drawing_page}不在本项目图纸目录中，请核对业务页号。")
    matches = [
        number
        for number, page in named.items()
        if (
            not binding.workspace_code
            or normalized(page.get("function")) == normalized(binding.workspace_code)
        )
        and (not binding.pdf_page_number or number == binding.pdf_page_number)
    ]
    if len(matches) == 1:
        return matches[0]
    choices = "；".join(
        f"{page.get('function') or '未分类'} / PDF {number}" for number, page in sorted(named.items())[:8]
    )
    if not matches:
        constraints = "、".join(
            filter(
                None,
                [
                    binding.workspace_code,
                    f"PDF {binding.pdf_page_number}" if binding.pdf_page_number else None,
                ],
            )
        )
        raise RescanTargetError(
            f"目标页{binding.drawing_page}在本项目对应{choices}，与传入的目标限制{constraints}冲突。"
            "请按目标图纸目录修正绑定；源连接scope.workspace_code不是目标工作区，不得直接继承。"
        )
    raise RescanTargetError(
        f"目标页{binding.drawing_page}在本项目匹配多个图纸（{choices}），请明确目标工作区或PDF物理页。"
    )


def bound_targets(job: dict[str, Any], metadata: dict[int, dict[str, Any]]) -> dict[str, int]:
    allowed = {str(row["id"]) for row in job["baseline"]}
    result: dict[str, int] = {}
    for raw in job["request"].get("target_bindings", []):
        binding = RescanTargetBinding.model_validate(raw)
        identifiers = list(map(str, binding.connection_ids))
        if set(identifiers) - allowed or set(identifiers).intersection(result):
            raise RescanTargetError("目标页绑定含范围外或重复连接，请重新选择连接后重试。")
        target = resolve_target_page(binding, metadata)
        result.update({identifier: target for identifier in identifiers})
    return result


def reference_target(row: dict[str, Any], metadata: dict[int, dict[str, Any]]) -> int | None:
    targets = set()
    for ref in ((row.get("evidence") or {}).get("record") or {}).get("references", []):
        if ref.get("external"):
            continue
        if ref.get("target_pdf_page") in metadata:
            targets.add(int(ref["target_pdf_page"]))
        elif ref.get("target_function") and ref.get("target_drawing_page") is not None:
            targets.update(
                number
                for number, page in metadata.items()
                if normalized(page.get("function")) == normalized(ref["target_function"])
                and str(page.get("internal_page")) == str(ref["target_drawing_page"])
            )
    return next(iter(targets)) if len(targets) == 1 else None


def endpoint_pages(
    row: dict[str, Any],
    metadata: dict[int, dict[str, Any]],
    explicit: dict[str, int],
    details: list[dict[str, Any]],
    *,
    same_page: bool = False,
) -> tuple[int, int | None]:
    """Resolve physical endpoint pages independently of the record's extraction-origin page."""
    origin = int(row["source_pdf_page_number"])
    pair = {int(number) for number in (origin, row.get("target_pdf_page_number")) if number is not None}
    matches = [
        number
        for number in pair
        if row.get("start_code") and metadata.get(number, {}).get("object_loc") == row["start_code"]
    ]
    source = int(
        (row.get("start_terminal_coordinates") or {}).get("pdf_page_number")
        or (matches[0] if len(matches) == 1 else origin)
    )
    bound = explicit.get(str(row["id"]))
    if same_page:
        if bound is not None and bound != source:
            raise RescanTargetError("同页要求与显式目标页冲突，请核对起点所在页和目标页。")
        return source, source
    uploaded = {int(item["pdf_page_number"]) for item in details if item["role"] == "target"}
    target = bound or (
        (row.get("end_terminal_coordinates") or {}).get("pdf_page_number")
        or row.get("target_pdf_page_number")
        or reference_target(row, metadata)
        or (origin if not row.get("is_cross_page") else None)
        or (next(iter(uploaded)) if len(uploaded) == 1 else None)
    )
    return source, int(target) if target is not None else None
