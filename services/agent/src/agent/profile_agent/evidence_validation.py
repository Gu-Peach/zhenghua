"""Validate evidence against one owned revision and host-provided turn context."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence, Set
from pathlib import Path
from typing import Any

from .models import Finding, ProfileError
from .validation import relative_file


def _observation_contains(observation: dict[str, Any], quote: str) -> bool:
    # Preserve literal line breaks/quotes in pasted results as well as JSON excerpts.
    if quote in json.dumps(observation, ensure_ascii=False):
        return True
    values: list[Any] = [observation]
    while values:
        value = values.pop()
        if isinstance(value, str) and quote in value:
            return True
        if isinstance(value, dict):
            values.extend(value.values())
        elif isinstance(value, list):
            values.extend(value)
    return False


def validate_findings(
    root: Path,
    findings: list[Finding],
    *,
    viewed_images: Set[str] = frozenset(),
    observations: Sequence[dict[str, Any]] = (),
    user_message: str = "",
) -> list[dict[str, str]]:
    """Images are viewed observations, never machine-verified OCR or proof of causality."""
    verified: list[dict[str, str]] = []
    texts: dict[str, str] = {}
    for finding in findings:
        if finding.category != "insufficient_evidence" and not finding.evidence:
            raise ProfileError("EVIDENCE_REQUIRED", "明确归因必须给出规则/案例原文或已查看原图依据", 422)
        if finding.category in {"model_deviation", "mixed"} and not observations:
            raise ProfileError("OBSERVATION_REQUIRED", "没有实际输出对照，不能确定是模型偏离", 422)
        if finding.category == "insufficient_evidence" and not finding.missing_evidence:
            raise ProfileError("EVIDENCE_REQUIRED", "请说明还缺哪些原图、实际输出或期望结果", 422)
        has_resource = False
        for anchor in finding.evidence:
            path, quote = anchor.path, anchor.quote
            if not quote.strip():
                raise ProfileError("INVALID_EVIDENCE", "证据摘录不能仅为空白", 422)
            if path == "user_message" or path.startswith("observations/"):
                if path == "user_message":
                    matches = quote in user_message
                else:
                    match = re.fullmatch(r"observations/(0|[1-9][0-9]?)", path)
                    if not match or int(match[1]) >= len(observations):
                        raise ProfileError(
                            "INVALID_EVIDENCE", "观察证据请引用本轮observations/<有效索引>", 422
                        )
                    matches = _observation_contains(observations[int(match[1])], quote)
                if not matches:
                    raise ProfileError("INVALID_EVIDENCE", "摘录未出现在本轮用户输入/观察中", 422)
                verified.append({"path": path, "source": "user_supplied", "verification": "exact_text"})
                continue
            try:
                file = relative_file(root, path)
            except (ValueError, OSError) as exc:
                raise ProfileError(
                    "INVALID_EVIDENCE_PATH", "请使用当前草稿资源列表中的完整相对路径", 422
                ) from exc
            suffix = file.suffix.lower()
            if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
                if path not in viewed_images:
                    raise ProfileError(
                        "EVIDENCE_IMAGE_NOT_VIEWED", "该图片本轮尚未查看，请先view_images再引用", 422
                    )
                verification = "viewed_image"
                source = "image"
            elif suffix in {".md", ".json", ".txt"}:
                if path not in texts:
                    try:
                        texts[path] = file.read_text(encoding="utf-8")
                    except (UnicodeError, OSError) as exc:
                        raise ProfileError(
                            "INVALID_EVIDENCE", "证据文件无法读取，请重新检查当前资源", 422
                        ) from exc
                if quote not in texts[path]:
                    raise ProfileError(
                        "INVALID_EVIDENCE", "摘录未出现在当前文件原文中，请read_file后精确引用", 422
                    )
                verification = "exact_text"
                source = "text"
            else:
                raise ProfileError("INVALID_EVIDENCE", "证据仅支持规则文本、已查看图片或本轮用户观察", 422)
            has_resource = True
            verified.append({"path": path, "source": source, "verification": verification})
        if finding.category != "insufficient_evidence" and not has_resource:
            raise ProfileError(
                "EVIDENCE_REQUIRED", "用户陈述单独不能证明归因，请补规则原文或已查看图纸依据", 422
            )
    return verified
