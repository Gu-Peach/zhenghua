from __future__ import annotations

import base64
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from src.agent.extraction_agent.domain.models.extraction_stages import TerminalCoordinates
from src.domain.models.common import FrozenModel


class CompletionViewRules(FrozenModel):
    version: int = 1
    enabled: bool = True
    columns: int = Field(default=10, ge=1)
    first_column: int = 0
    frame_left: float = Field(default=0.02, ge=0, lt=1)
    frame_right: float = Field(default=0.99, gt=0, le=1)
    half_width_columns: float = Field(default=0.95, ge=0.5, le=3)
    max_side: int = Field(default=4096, ge=1)
    min_aspect: float = Field(default=1.2, gt=0)
    max_aspect: float = Field(default=1.8, gt=0)

    @model_validator(mode="after")
    def check_ranges(self) -> CompletionViewRules:
        if self.frame_left >= self.frame_right or self.min_aspect > self.max_aspect:
            raise ValueError("Invalid completion view frame or aspect range")
        return self


class CompletionInputView(FrozenModel):
    mode: Literal["column_crop"] = "column_crop"
    column: int
    coordinate_space: Literal["input_image"] = "input_image"


class CompletionImageViewport(FrozenModel):
    mode: Literal["column_crop"] = "column_crop"
    column: int
    original_width: int = Field(ge=1)
    original_height: int = Field(ge=1)
    left: int = Field(ge=0)
    top: int = Field(ge=0)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    input_width: int = Field(ge=1)
    input_height: int = Field(ge=1)

    @model_validator(mode="after")
    def check_bounds(self) -> CompletionImageViewport:
        if self.left + self.width > self.original_width or self.top + self.height > self.original_height:
            raise ValueError("Completion view exceeds the original image")
        return self

    def to_full_page(self, point: TerminalCoordinates) -> TerminalCoordinates:
        return point.model_copy(
            update={
                "x": (self.left + point.x * self.width) / self.original_width,
                "y": (self.top + point.y * self.height) / self.original_height,
            }
        )

    def input_context(self) -> CompletionInputView:
        return CompletionInputView(column=self.column)

    def to_input_view(self, point: TerminalCoordinates) -> TerminalCoordinates:
        x = (point.x * self.original_width - self.left) / self.width
        y = (point.y * self.original_height - self.top) / self.height
        if not 0 <= x <= 1 or not 0 <= y <= 1:
            raise ValueError("Confirmed example point is outside the completion view")
        return point.model_copy(update={"x": x, "y": y})


@dataclass(frozen=True)
class PreparedCompletionView:
    png: bytes | None = None
    viewport: CompletionImageViewport | None = None
    reason: str = "full_page"

    @property
    def metadata(self) -> dict[str, Any]:
        return (
            {"mode": "column_crop", **self.viewport.model_dump()}
            if self.viewport
            else {
                "mode": "full_page",
                "reason": self.reason,
            }
        )


def prepare_completion_view(
    image_path: Path,
    references: Sequence[Mapping[str, Any]],
    *,
    target_pdf_page: int,
    rules_path: Path | None,
    input_max_side: int,
    max_total_pixels: int,
    max_view_side: int | None = None,
) -> PreparedCompletionView:
    """Prepare one bounded target image, without locating regions with a model."""
    if input_max_side < 1 or max_total_pixels < 1 or (max_view_side is not None and max_view_side < 1):
        raise ValueError("Completion view image limits must be positive")
    if rules_path is None:
        return PreparedCompletionView(reason="profile_has_no_view_rules")
    rules = CompletionViewRules.model_validate_json(rules_path.read_text(encoding="utf-8"))
    if not rules.enabled:
        return PreparedCompletionView(reason="disabled")
    if max_view_side is not None:
        rules = rules.model_copy(update={"max_side": min(rules.max_side, max_view_side)})
    columns = {
        item["target_column"]
        for item in references
        if item.get("target_pdf_page") in (None, target_pdf_page) and type(item.get("target_column")) is int
    }
    if len(columns) != 1:
        return PreparedCompletionView(reason="missing_or_ambiguous_column")
    column = next(iter(columns))
    if not rules.first_column <= column < rules.first_column + rules.columns:
        return PreparedCompletionView(reason="column_out_of_frame")
    try:
        stat = image_path.stat()
        return _render_view(
            str(image_path.resolve()),
            stat.st_mtime_ns,
            stat.st_size,
            column,
            rules.model_dump_json(),
            input_max_side,
            max_total_pixels,
        )
    except (OSError, RuntimeError, ValueError):
        # Existing full-image loading/error handling remains the fallback path.
        return PreparedCompletionView(reason="view_preparation_failed")


@lru_cache(maxsize=32)
def _render_view(
    path: str,
    mtime_ns: int,
    file_size: int,
    column: int,
    rules_json: str,
    input_max_side: int,
    max_total_pixels: int,
) -> PreparedCompletionView:
    import pymupdf

    rules = CompletionViewRules.model_validate_json(rules_json)
    source = pymupdf.Pixmap(path)
    w, h = source.width, source.height
    if not rules.min_aspect <= w / h <= rules.max_aspect:
        return PreparedCompletionView(reason="unsupported_page_layout")
    if source.colorspace is None:
        return PreparedCompletionView(reason="unsupported_colorspace")
    if source.colorspace.n not in (1, 3):
        source = pymupdf.Pixmap(pymupdf.csRGB, source)
    step = (rules.frame_right - rules.frame_left) / rules.columns
    center = rules.frame_left + (column - rules.first_column + 0.5) * step
    left = max(0, math.floor((center - rules.half_width_columns * step) * w))
    right = min(w, math.ceil((center + rules.half_width_columns * step) * w))
    if right <= left or right - left >= w:
        return PreparedCompletionView(reason="no_useful_reduction")
    rect = pymupdf.IRect(left, 0, right, h)
    crop = pymupdf.Pixmap(source.colorspace, rect, source.alpha)
    crop.copy(source, rect)
    crop.set_origin(0, 0)

    # Never spend more actual-input pixels than the former whole-page request.
    baseline_scale = min(1.0, input_max_side / max(w, h))
    pixel_limit = min(
        max(1, math.floor(w * baseline_scale)) * max(1, math.floor(h * baseline_scale)),
        max_total_pixels,
    )
    scale = min(
        1.0,
        rules.max_side / max(crop.width, crop.height),
        math.sqrt(pixel_limit / (crop.width * crop.height)),
    )
    width, height = max(1, math.floor(crop.width * scale)), max(1, math.floor(crop.height * scale))
    if (width, height) != (crop.width, crop.height):
        crop = pymupdf.Pixmap(crop, width, height)
    if crop.width * crop.height > pixel_limit or max(crop.width, crop.height) > rules.max_side:
        raise ValueError("Completion image exceeds its input pixel allowance")
    view = CompletionImageViewport(
        column=column,
        original_width=w,
        original_height=h,
        left=left,
        top=0,
        width=right - left,
        height=h,
        input_width=crop.width,
        input_height=crop.height,
    )
    return PreparedCompletionView(png=crop.tobytes("png"), viewport=view)


def transform_completion_points(
    payload: Mapping[str, Any],
    view: CompletionImageViewport,
    *,
    to_full_page: bool,
) -> dict[str, Any]:
    """Transform only target-image points, validating model coordinates before mapping."""
    import copy

    result = copy.deepcopy(dict(payload))
    endpoints = [result.get("end"), *(result.get("intermediate_points") or [])]
    for endpoint in endpoints:
        if not isinstance(endpoint, dict) or not endpoint.get("terminal_coordinates"):
            continue
        if endpoint.get("terminal") in (None, ""):
            endpoint["terminal_coordinates"] = None
            continue
        point = TerminalCoordinates.model_validate(endpoint["terminal_coordinates"])
        point = view.to_full_page(point) if to_full_page else view.to_input_view(point)
        endpoint["terminal_coordinates"] = point.model_dump(mode="json")
    return result


def prepare_completion_example_view(
    example: Mapping[str, Any],
    *,
    rules_path: Path | None,
    input_max_side: int,
    max_total_pixels: int,
    fewshot_max_side: int,
) -> dict[str, Any]:
    """Use the same view contract for one selected target-only demonstration."""
    import pymupdf

    original = dict(example)
    images = original.get("images") or []
    if rules_path is None or len(images) != 1 or images[0].get("role") != "target_page":
        return original
    task = json.loads(original.get("input_json") or "{}")
    target = task.get("target_page") or {}
    target_pdf = target.get("pdf_page_number") or task.get("target_pdf_page")
    if not target_pdf or not images[0].get("path"):
        return original
    before = pymupdf.Pixmap(base64.b64decode(images[0]["data_url"].split(",", 1)[1]))
    prepared = prepare_completion_view(
        Path(images[0]["path"]),
        task.get("references") or [],
        target_pdf_page=int(target_pdf),
        rules_path=rules_path,
        input_max_side=input_max_side,
        max_total_pixels=min(max_total_pixels, before.width * before.height),
        max_view_side=fewshot_max_side,
    )
    if prepared.viewport is None or prepared.png is None:
        return original
    try:
        expected = transform_completion_points(
            json.loads(original["expected_json"]),
            prepared.viewport,
            to_full_page=False,
        )
    except ValueError:
        # The ground truth must stay visible; never invent an in-crop coordinate.
        return original
    task["context_version"] = 3
    task["image_view"] = prepared.viewport.input_context().model_dump(mode="json")
    original["input_json"] = json.dumps(task, ensure_ascii=False, separators=(",", ":"))
    original["expected_json"] = json.dumps(expected, ensure_ascii=False, separators=(",", ":"))
    original["images"] = [
        {
            **images[0],
            "data_url": "data:image/png;base64," + base64.b64encode(prepared.png).decode("ascii"),
        }
    ]
    return original
