from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..services.vlm_client import ImagePayload, VLMClient, _extract_json_candidate
from .state import MergeDecision, PageMeta


logger = logging.getLogger(__name__)


class SegmentDecider(Protocol):
    def decide(self, page_a: PageMeta, page_b: PageMeta) -> MergeDecision | Awaitable[MergeDecision]:
        """Decide whether two adjacent source pages belong to one segment."""


class SegmentDecisionPayload(BaseModel):
    """The response body required from Prompt S before page numbers are added."""

    model_config = ConfigDict(extra="ignore")

    merge: bool
    project_no_a: str | None = None
    project_no_b: str | None = None
    drawing_prefix_a: str | None = None
    drawing_prefix_b: str | None = None
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    needs_review: bool

    @field_validator(
        "project_no_a",
        "project_no_b",
        "drawing_prefix_a",
        "drawing_prefix_b",
        "reason",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


ImageLoader = Callable[[str], ImagePayload]


@dataclass
class VLMSegmentDecider:
    """Prompt-S implementation of the replaceable segment decision interface."""

    client: VLMClient
    prompt: str
    image_loader: ImageLoader
    retry_count: int = 1
    prefix_messages: Sequence[dict[str, Any]] = field(default_factory=tuple)

    async def decide(self, page_a: PageMeta, page_b: PageMeta) -> MergeDecision:
        image_a = self.image_loader(page_a["image_path"])
        image_b = self.image_loader(page_b["image_path"])
        page_a_number = page_a["page_number"]
        page_b_number = page_b["page_number"]
        request_text = (
            f"请只依据 Prompt S 判断相邻页 A=PDF 第 {page_a_number} 页、"
            f"B=PDF 第 {page_b_number} 页。第一张图片是 A，第二张图片是 B。"
            "请读取两张原图右下角图框中的 Project.NR 与 drawing prefix。"
            "只返回 Prompt S 要求的 JSON，不要返回 a、b 字段。"
        )
        last_error: Exception | None = None
        for attempt in range(self.retry_count + 1):
            try:
                response = await self.client.complete(
                    images=[image_a, image_b],
                    system_prompt=self.prompt,
                    user_text=request_text if attempt == 0 else (
                        request_text + " 上一次输出无法通过 JSON schema 校验，请重新读取图片并严格输出完整 JSON。"
                    ),
                    prefix_messages=self.prefix_messages,
                )
                payload = _parse_segment_payload(response)
                return _as_merge_decision(page_a_number, page_b_number, payload)
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Segment decision parse/request failed for pages %s-%s, attempt %s/%s: %s",
                    page_a_number,
                    page_b_number,
                    attempt + 1,
                    self.retry_count + 1,
                    exc,
                )

        return _degraded_decision(page_a_number, page_b_number, last_error)


def _parse_segment_payload(content: str) -> SegmentDecisionPayload:
    raw = content.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = json.loads(_extract_json_candidate(raw))
    if not isinstance(parsed, dict):
        raise ValueError("Prompt S response must be a JSON object.")
    return SegmentDecisionPayload.model_validate(parsed)


def _as_merge_decision(a: int, b: int, payload: SegmentDecisionPayload) -> MergeDecision:
    return {
        "a": a,
        "b": b,
        "merge": payload.merge,
        "project_no_a": payload.project_no_a,
        "project_no_b": payload.project_no_b,
        "drawing_prefix_a": payload.drawing_prefix_a,
        "drawing_prefix_b": payload.drawing_prefix_b,
        "reason": payload.reason,
        "confidence": payload.confidence,
        "needs_review": payload.needs_review,
    }


def _degraded_decision(a: int, b: int, error: Exception | None) -> MergeDecision:
    detail = str(error).strip() if error else "unknown error"
    return {
        "a": a,
        "b": b,
        "merge": False,
        "project_no_a": None,
        "project_no_b": None,
        "drawing_prefix_a": None,
        "drawing_prefix_b": None,
        "reason": f"VLM 分段判断失败，已降级为不合并：{detail}",
        "confidence": 0.0,
        "needs_review": True,
    }


def degraded_decision(a: int, b: int, error: Exception | None) -> MergeDecision:
    """Public fallback used by graph adapters and alternate deciders."""
    return _degraded_decision(a, b, error)
