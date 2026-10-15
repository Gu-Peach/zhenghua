"""Resize request images without changing drawing files or normalized coordinates."""

from __future__ import annotations

import base64
import copy
import math
from dataclasses import dataclass
from typing import Any

IMAGE_BUDGET_POLICY_VERSION = "input_first_v1"


@dataclass(slots=True)
class _ImageEntry:
    image_url: dict[str, Any]
    pixmap: Any
    message_index: int
    kind: str
    width: int
    height: int


def _scaled_size(entry: _ImageEntry, scale: float, minimum_side: int) -> tuple[int, int]:
    minimum_scale = min(1.0, minimum_side / max(entry.width, entry.height))
    effective = max(scale, minimum_scale)
    return max(1, math.floor(entry.width * effective)), max(1, math.floor(entry.height * effective))


def _minimum_pixels(entries: list[_ImageEntry], minimum_side: int) -> int:
    return sum(
        width * height for entry in entries for width, height in [_scaled_size(entry, 0.0, minimum_side)]
    )


def _fit_images(entries: list[_ImageEntry], budget: int, *, minimum_side: int = 0) -> None:
    """Fit one priority tier without enlarging images or crossing its minimum size."""
    if sum(entry.width * entry.height for entry in entries) <= budget:
        return
    if _minimum_pixels(entries, minimum_side) > budget:
        raise ValueError("Image budget cannot accommodate required image sizes.")
    low, high = 0.0, 1.0
    for _ in range(40):
        mid = (low + high) / 2
        pixels = sum(
            width * height for entry in entries for width, height in [_scaled_size(entry, mid, minimum_side)]
        )
        if pixels <= budget:
            low = mid
        else:
            high = mid
    sizes = [_scaled_size(entry, low, minimum_side) for entry in entries]
    for entry, (width, height) in zip(entries, sizes, strict=True):
        entry.width, entry.height = width, height


def prepare_vision_messages(
    messages: list[dict[str, Any]],
    *,
    input_max_side: int,
    max_total_pixels: int,
    few_shot_min_side: int = 768,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Reserve actual-input pixels first, then shrink or remove complete example pairs."""
    import pymupdf

    if input_max_side < 1 or max_total_pixels < 1 or few_shot_min_side < 1:
        raise ValueError("Model image limits must be positive.")
    prepared = copy.deepcopy(messages)
    entries: list[_ImageEntry] = []
    for message_index, message in enumerate(prepared):
        content = message.get("content")
        if not isinstance(content, list):
            continue
        # Only example user messages can be removed; never discard system instructions.
        kind = "few_shot" if message_index < len(prepared) - 1 and message.get("role") == "user" else "input"
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "image_url":
                continue
            image_url = item["image_url"]
            url = image_url["url"]
            if not url.startswith("data:image/") or ";base64," not in url:
                raise ValueError("Extraction image budgeting requires inline image data.")
            pixmap = pymupdf.Pixmap(base64.b64decode(url.split(",", 1)[1], validate=True))
            scale = min(1.0, input_max_side / max(pixmap.width, pixmap.height)) if kind == "input" else 1.0
            width = max(1, math.floor(pixmap.width * scale))
            height = max(1, math.floor(pixmap.height * scale))
            entries.append(_ImageEntry(image_url, pixmap, message_index, kind, width, height))

    inputs = [entry for entry in entries if entry.kind == "input"]
    if len(inputs) > max_total_pixels:
        raise ValueError("Model image pixel budget is smaller than the required input image count.")
    case_indices = list(dict.fromkeys(entry.message_index for entry in entries if entry.kind == "few_shot"))
    retained = list(case_indices)
    input_pixels = sum(entry.width * entry.height for entry in inputs)
    input_reduced = input_pixels > max_total_pixels
    if input_reduced:
        retained.clear()
        _fit_images(inputs, max_total_pixels)
    else:
        available = max_total_pixels - input_pixels
        while retained:
            examples = [entry for entry in entries if entry.message_index in retained]
            if _minimum_pixels(examples, few_shot_min_side) <= available:
                _fit_images(examples, available, minimum_side=few_shot_min_side)
                break
            # Preserve manifest order; remove a whole case, including all its images.
            retained.pop()
    dropped = [index for index in case_indices if index not in retained]
    removed_messages = set(dropped)
    for index in dropped:
        if index + 1 < len(prepared) and prepared[index + 1].get("role") == "assistant":
            removed_messages.add(index + 1)
    kept_entries = [entry for entry in entries if entry.message_index not in removed_messages]
    details: list[dict[str, Any]] = []
    for entry in kept_entries:
        image_url, pixmap = entry.image_url, entry.pixmap
        width, height = entry.width, entry.height
        if (width, height) != (pixmap.width, pixmap.height):
            resized = pymupdf.Pixmap(pixmap, width, height)
            image_url["url"] = "data:image/png;base64," + base64.b64encode(resized.tobytes("png")).decode(
                "ascii"
            )
            width, height = resized.width, resized.height
        details.append(
            {
                "kind": entry.kind, "message_index": entry.message_index,
                "size_before": [pixmap.width, pixmap.height], "size_sent": [width, height],
            }
        )
    pixels_sent = sum(item["size_sent"][0] * item["size_sent"][1] for item in details)
    if pixels_sent > max_total_pixels:
        raise ValueError("Unable to fit extraction images into the configured pixel budget.")
    return [message for index, message in enumerate(prepared) if index not in removed_messages], {
        "vision_budget_policy": IMAGE_BUDGET_POLICY_VERSION,
        "vision_image_count": len(details),
        "vision_images": details,
        "vision_total_pixels": pixels_sent,
        "vision_input_max_side": input_max_side,
        "vision_max_total_pixels": max_total_pixels,
        "vision_few_shot_min_side": few_shot_min_side,
        "vision_few_shot_cases_before": len(case_indices),
        "vision_few_shot_cases_after": len(retained),
        "vision_dropped_few_shot_cases": dropped,
        "vision_input_reduced_for_budget": input_reduced,
    }
