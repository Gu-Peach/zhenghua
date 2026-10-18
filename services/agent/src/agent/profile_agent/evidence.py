"""Load bounded rule/case evidence before the first model call, with explicit coverage gaps."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from src.profiles.package import checksum

from .tools import ProfileTools
from .validation import case_files


def load_initial_evidence(tools: ProfileTools) -> tuple[dict[str, Any], list[dict[str, str]]]:
    _, root, meta = tools.store.snapshot(tools.draft, tools.actor, tools.revision)
    manifest = json.loads((root / "profile.json").read_text(encoding="utf-8"))
    resources = manifest["resources"]
    paths = [
        "profile.json",
        resources["routing_rules"],
        resources["classification_prompt"],
        resources["page_scan_prompt"],
        resources["cross_page_prompt"],
        resources["classification_examples"] + "/manifest.json",
        resources["wiring_examples"] + "/manifest.json",
    ]
    focus = {
        "classification": "classification_prompt",
        "scan": "page_scan_prompt",
        "completion": "cross_page_prompt",
    }
    if tools.turn.focus_stage:
        paths.insert(0, resources[focus[tools.turn.focus_stage]])
    cases = case_files(root)
    for stage in ("classification", "scan", "completion"):
        case = next((item for item in cases if item["stage"] == stage), None)
        if case:
            paths.append(case["expected_path"])
            if case.get("input_path"):
                paths.append(case["input_path"])
    readings = []
    budget = 24000
    deferred = []
    for value in dict.fromkeys(paths):
        file = tools.store.file(root, value)
        if not file.is_file():
            readings.append({"path": value, "error": "RESOURCE_MISSING"})
            continue
        content = file.read_text(encoding="utf-8")
        if budget < 100:
            deferred.append(value)
            continue
        limit = min(3000, budget)
        readings.append(
            {
                "path": value,
                "checksum": checksum(file.read_bytes()),
                "text": content[:limit],
                "total_characters": len(content),
                "next_offset": limit if len(content) > limit else None,
            }
        )
        budget -= min(len(content), limit)
    # User originals take priority. Retain a small source/target example set when available.
    uploaded = meta.get("attachments", [])
    current_images = [a["path"] for a in uploaded if UUID(a["id"]) in tools.turn.attachment_ids]
    images = current_images or [a["path"] for a in uploaded[-2:]]
    image_stages = list(
        dict.fromkeys(
            [
                *([tools.turn.focus_stage] if tools.turn.focus_stage else []),
                "scan",
                "completion",
                "classification",
            ]
        )
    )
    for stage in image_stages:
        case = next((item for item in cases if item["stage"] == stage), None)
        if case:
            for image in case["images"]:
                if image["path"] not in images and len(images) < 6:
                    images.append(image["path"])
    pixels = tools.store.images(tools.draft, tools.actor, images) if images else []
    tools.viewed.update(images)
    return {
        "readings": readings,
        "deferred_files": deferred,
        "selected_images": images,
        "coverage": (
            "仅自动加载代表案例，next_offset非空表示截断；"
            "不能据此声称已检查全部规则/全部案例，需要时用工具继续读取。"
        ),
        "unloaded_user_images": [a["path"] for a in meta.get("attachments", []) if a["path"] not in images],
    }, pixels
