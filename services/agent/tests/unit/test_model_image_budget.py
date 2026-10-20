"""Offline image-boundary regressions; never call a provider or database."""

from __future__ import annotations

import base64
import copy
import hashlib
from pathlib import Path

import pymupdf

from src.agent.extraction_agent.infrastructure.document.model_images import prepare_vision_messages


def image_bytes(width: int, height: int) -> bytes:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height), False)
    pixmap.clear_with(255)
    return pixmap.tobytes("png")


def image_part(data: bytes) -> dict:
    return {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64," + base64.b64encode(data).decode(), "detail": "auto"},
    }


def test_cross_page_inputs_keep_size_and_drop_the_complete_example(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(image_bytes(3508, 2481))
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    few_shot = image_part(image_bytes(1748, 1234))
    messages = [
        {"role": "user", "content": [few_shot, copy.deepcopy(few_shot)]},
        {"role": "assistant", "content": '{"end":null}'},
        {"role": "user", "content": [image_part(source.read_bytes()), image_part(source.read_bytes())]},
    ]
    before = copy.deepcopy(messages)
    prepared, metadata = prepare_vision_messages(messages, input_max_side=2048, max_total_pixels=6_000_000)
    assert messages == before
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
    assert metadata["vision_image_count"] == 2
    assert metadata["vision_dropped_few_shot_cases"] == [0]
    assert metadata["vision_input_reduced_for_budget"] is False
    assert len(prepared) == 1 and prepared[0]["role"] == "user"
    assert metadata["vision_total_pixels"] <= 6_000_000
    actual_pixels = 0
    for message in prepared:
        if isinstance(message["content"], list):
            for part in message["content"]:
                pixmap = pymupdf.Pixmap(base64.b64decode(part["image_url"]["url"].split(",", 1)[1]))
                actual_pixels += pixmap.width * pixmap.height
    assert actual_pixels == metadata["vision_total_pixels"]
    for info in metadata["vision_images"]:
        width, height = info["size_sent"]
        before_width, before_height = info["size_before"]
        assert width <= before_width and height <= before_height
        assert abs(width * before_height - height * before_width) <= before_width + before_height
        if info["kind"] == "input":
            assert max(width, height) == 2048


def test_small_images_are_neither_upscaled_nor_reencoded() -> None:
    messages = [{"role": "user", "content": [image_part(image_bytes(32, 16))]}]
    prepared, metadata = prepare_vision_messages(messages, input_max_side=2048, max_total_pixels=6_000_000)
    assert prepared == messages
    assert metadata["vision_total_pixels"] == 512


def test_explicit_real_images_before_text_instruction_never_become_discardable_examples():
    messages = [
        {"role": "user", "content": [image_part(image_bytes(600, 600))]},
        {"role": "assistant", "content": "example"},
        {"role": "user", "content": [image_part(image_bytes(800, 600))]},
        {"role": "user", "content": [image_part(image_bytes(800, 600))]},
        {"role": "user", "content": "冻结任务说明，无图"},
    ]
    prepared, metadata = prepare_vision_messages(
        messages,
        input_max_side=2048,
        max_total_pixels=960000,
        input_message_indices={2, 3},
    )
    assert metadata["vision_image_count"] == 2
    assert all(item["kind"] == "input" for item in metadata["vision_images"])
    assert prepared[-1]["content"] == "冻结任务说明，无图"


def test_long_thin_images_fit_total_budget_without_mutating_source() -> None:
    messages = [{"role": "user", "content": [image_part(image_bytes(1000, 1))]}]
    prepared, metadata = prepare_vision_messages(messages, input_max_side=2048, max_total_pixels=10)
    assert metadata["vision_total_pixels"] <= 10
    assert prepared != messages
    assert metadata["vision_input_reduced_for_budget"] is True


def test_examples_shrink_before_a_current_image_loses_pixels() -> None:
    messages = [
        {"role": "user", "content": [image_part(image_bytes(1000, 1000))]},
        {"role": "assistant", "content": '{"example":1}'},
        {"role": "user", "content": [image_part(image_bytes(1000, 1000))]},
    ]
    prepared, metadata = prepare_vision_messages(messages, input_max_side=2048, max_total_pixels=1_800_000)
    example, actual = metadata["vision_images"]
    assert actual["size_sent"] == [1000, 1000]
    assert 768 <= max(example["size_sent"]) < 1000
    assert metadata["vision_total_pixels"] <= 1_800_000
    assert metadata["vision_few_shot_cases_after"] == 1
    assert prepared[-1] == messages[-1]


def test_case_removal_keeps_manifest_priority_and_matching_answers() -> None:
    messages = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": [image_part(image_bytes(800, 600))]},
        {"role": "assistant", "content": "first expected"},
        {"role": "user", "content": [image_part(image_bytes(800, 600))]},
        {"role": "assistant", "content": "second expected"},
        {"role": "user", "content": [image_part(image_bytes(1000, 800))]},
    ]
    prepared, metadata = prepare_vision_messages(messages, input_max_side=2048, max_total_pixels=1_300_000)
    assert metadata["vision_dropped_few_shot_cases"] == [3]
    assert [message["role"] for message in prepared] == ["system", "user", "assistant", "user"]
    assert prepared[2]["content"] == "first expected"
    assert prepared[-1] == messages[-1]


def test_only_actual_inputs_over_budget_trigger_actual_input_downsampling() -> None:
    messages = [
        {"role": "user", "content": [image_part(image_bytes(800, 600))]},
        {"role": "assistant", "content": "expected"},
        {
            "role": "user",
            "content": [image_part(image_bytes(2000, 1500)), image_part(image_bytes(2000, 1500))],
        },
    ]
    prepared, metadata = prepare_vision_messages(messages, input_max_side=2048, max_total_pixels=3_000_000)
    assert metadata["vision_few_shot_cases_after"] == 0
    assert metadata["vision_input_reduced_for_budget"] is True
    assert metadata["vision_total_pixels"] <= 3_000_000
    assert len(prepared) == 1
    assert all(info["kind"] == "input" for info in metadata["vision_images"])
