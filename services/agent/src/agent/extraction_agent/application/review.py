"""One deterministic review decision, independent of model status/confidence."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from src.agent.extraction_agent.domain.models.review import (
    ReviewDecision,
    ReviewPhase,
    ReviewReason,
)

MODEL_CONTROL_FIELDS = frozenset(
    {
        "scan_diagnostics",
        "status",
        "needs_review",
        "review_reasons",
        "processing_status",
        "completion_state",
        "completion_evidence",
    }
)

REVIEW_CONTRACT_VERSION = "1.0.0"


def facts_only(value: Any) -> Any:
    """Remove model-owned verdicts from responses, examples and JSON Schemas."""
    if isinstance(value, list):
        return [facts_only(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: facts_only(item) for key, item in value.items() if key not in MODEL_CONTROL_FIELDS}
    if isinstance(result.get("required"), list):
        result["required"] = [key for key in result["required"] if key not in MODEL_CONTROL_FIELDS]
    return result


def evaluate_review(
    record: Mapping[str, Any],
    *,
    phase: ReviewPhase,
    strict_evidence: bool,
    warnings: Sequence[str] = (),
) -> ReviewDecision:
    """Evaluate current facts; pending referenced endpoints are not final omissions."""
    reasons: list[ReviewReason] = []

    def add(code: str, field: str | None, message: str) -> None:
        if not any(item.code == code and item.field == field and item.message == message for item in reasons):
            reasons.append(ReviewReason(code=code, field=field, message=message))

    refs = record.get("references") or []
    pending = phase == "scan" and not record.get("end_terminal") and bool(refs)
    role = record.get("endpoint_role", "source")
    if role == "unknown" or (strict_evidence and not str(record.get("direction_basis") or "").strip()):
        add("direction_unconfirmed", "direction", "起终点方向缺少可确认的图纸依据")
    spare = str(record.get("line_number") or "").upper() == "SPARE"
    for side in ("start", "end"):
        if side == "end" and pending:
            continue
        terminal = str(record.get(f"{side}_terminal") or "").strip()
        device = record.get(f"{side}_device")
        board = record.get(f"{side}_terminal_board")
        if not terminal:
            add(
                f"missing_{side}_terminal",
                f"{side}_terminal",
                f"{'起点' if side == 'start' else '终点'}端子未确认",
            )
        elif strict_evidence and not spare:
            if re.fullmatch(r"[IQ]\d+\.\d+", terminal, re.I) or re.search(
                r"(?:^|:)\w+_(?:L\d?|N|PE|\+|-)(?:\.\d+)?$",
                terminal,
                re.I,
            ):
                add("non_physical_terminal", f"{side}_terminal", "PLC地址或电位名称不能作为实际端子")
            if not (device or board or ":" in terminal or terminal.upper() in {"N-BAR", "PE-BAR"}):
                add("endpoint_identity_incomplete", side, "缺少所属元件或端子排身份")
    if phase == "final":
        completion = record.get("completion_state")
        messages = {
            "unavailable": ("target_unavailable", "跨页目标或图片不可用"),
            "conflicting": ("target_conflict", "多个目标返回不同终点"),
            "failed": ("completion_failed", "补全未能产生可确认的结果"),
        }
        if completion in messages:
            code, message = messages[completion]
            add(code, "end", message)
        if completion == "resolved" and strict_evidence and not record.get("completion_evidence"):
            add("completion_evidence_missing", "end", "补全结果缺少目标路径依据")
        if not record.get("end_terminal"):
            for reference in refs:
                if isinstance(reference, dict) and reference.get("reason"):
                    add("reference_unresolved", "references", str(reference["reason"]))
    for uncertainty in record.get("uncertainties") or []:
        if hasattr(uncertainty, "model_dump"):
            uncertainty = uncertainty.model_dump()
        if isinstance(uncertainty, dict) and not (pending and uncertainty.get("field") == "end"):
            add(
                "visual_uncertainty",
                uncertainty.get("field"),
                str(uncertainty.get("detail") or "图像信息不明确"),
            )
    for warning in warnings:
        add("profile_validation", None, warning)
    return ReviewDecision(
        needs_review=bool(reasons),
        review_reasons=reasons,
        processing_status="pending_completion" if pending else "scanned" if phase == "scan" else "completed",
    )
