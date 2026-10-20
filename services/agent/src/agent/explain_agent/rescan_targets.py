"""Resolve explicit business pages inside the immutable job catalog, never from prose."""

import re
from typing import Any

from .models import RescanTargetBinding


class RescanTargetError(ValueError):
    """A safe, actionable target-selection error suitable for the job status."""


def normalized(value: Any) -> str:
    return re.sub(r"[\W_]+", "", str(value or "").casefold())


def bound_targets(job: dict[str, Any], metadata: dict[int, dict[str, Any]]) -> dict[str, int]:
    allowed = {str(row["id"]) for row in job["baseline"]}
    result: dict[str, int] = {}
    for raw in job["request"].get("target_bindings", []):
        binding = RescanTargetBinding.model_validate(raw)
        identifiers = list(map(str, binding.connection_ids))
        if set(identifiers) - allowed or set(identifiers).intersection(result):
            raise RescanTargetError("目标页绑定含范围外或重复连接，请重新选择连接后重试。")
        matches = [
            number
            for number, page in metadata.items()
            if normalized(page.get("workspace_page")) == normalized(binding.drawing_page)
            and (
                not binding.workspace_code
                or normalized(page.get("function")) == normalized(binding.workspace_code)
            )
            and (not binding.pdf_page_number or number == binding.pdf_page_number)
        ]
        if len(matches) != 1:
            raise RescanTargetError(
                f"目标页{binding.drawing_page}在本项目未唯一定位，请明确工作区或PDF物理页。"
            )
        result.update({identifier: matches[0] for identifier in identifiers})
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
