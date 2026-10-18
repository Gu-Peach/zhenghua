"""Build a verifiable evidence path without inventing past model reasoning."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from .models import EvidenceStep, ExplainContext


def prepare_evidence(context: ExplainContext) -> ExplainContext:
    row = context.row
    steps = [
        EvidenceStep(
            id="row",
            kind="record",
            description="当前数据库保存的连接事实与行版本。",
            facts=row.model_dump(mode="json"),
        )
    ]
    for drawing in context.drawings:
        steps.append(
            EvidenceStep(
                id=drawing.role,
                kind=drawing.role,
                description={
                    "source": "来源图纸索引。",
                    "target": "目标图纸索引。",
                    "reference": "跨页引用候选图纸索引，未证明终点。",
                }[drawing.role],
                facts=drawing.model_dump(mode="json", exclude={"image_url", "url_expires_in"}),
            )
        )
    if context.profile:
        steps.append(
            EvidenceStep(
                id="profile",
                kind="profile",
                description="该行证据保存的规则版本。"
                if context.profile.source == "record_evidence"
                else "当前项目规则引用，不能作为历史提取版本证明。",
                facts=context.profile.model_dump(mode="json"),
            )
        )
    descriptions: tuple[tuple[str, Literal["reference", "extraction", "review"], str], ...] = (
        ("references", "reference", "提取记录保存的跨页引用。"),
        ("source_note", "extraction", "提取时记录的来源说明。"),
        ("direction_basis", "extraction", "提取时记录的方向依据。"),
        ("current_source_text", "extraction", "已记录的电流原文依据。"),
        ("extraction_method", "extraction", "该行保存的提取方式。"),
        ("review_reasons", "review", "程序保存的复核原因。"),
        ("field_differences", "review", "当前字段与已保存提取值的差异，不推断变更操作者或原因。"),
        ("manual_change", "review", "已确认线表修订的方案和字段；历史提取说明保留用于追溯。"),
        ("rescan", "review", "用户确认后的重新扫描记录、实际原图/细节图证据及原规则版本。"),
    )
    for key, kind, label in descriptions:
        value = context.recorded.get(key)
        if value:
            steps.append(EvidenceStep(id=key, kind=kind, description=label, facts={key: value}))
    if not context.recorded.get("source_note"):
        context.gaps.append("未记录提取来源说明，无法还原每个字段当时的识别过程。")
    if not context.recorded.get("extraction_method"):
        context.gaps.append("未记录完整模型调用方式，不能断言当时模型看了哪些图片或内部思考。")
    if row.is_cross_page and not context.recorded.get("references"):
        context.gaps.append("当前行标记跨页，但未保存引用文字证据。")
    for name, value in (("起点端子", row.start_terminal), ("终点端子", row.end_terminal)):
        if not value:
            context.gaps.append(f"{name}尚未确认，不能根据常识补造。")
    context.gaps = list(dict.fromkeys(context.gaps))
    context.evidence_path = steps
    return context


def context_fingerprint(context: ExplainContext) -> str:
    return hashlib.sha256(
        json.dumps(
            context.model_facts(),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
