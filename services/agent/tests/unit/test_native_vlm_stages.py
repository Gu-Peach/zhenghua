from __future__ import annotations

import asyncio
import base64
import struct
import tempfile
import unittest
from pathlib import Path

from agent_service.config import AgentSettings
from agent_service.domain.enums import ErrorCode
from agent_service.domain.models.extraction_stages import (
    CrossPageCompletionRequest,
    DrawingPageInput,
    PageClassificationRequest,
    PageScanRequest,
)
from agent_service.harness.model_gateway import FakeModelGateway, ModelGatewayError
from agent_service.infrastructure.zh_vlm_stages import ZhVlmExtractionStageAdapter
from agent_service.profiles import ProfileRegistry

AGENT_ROOT = Path(__file__).resolve().parents[2]
ROOT = AGENT_ROOT.parent.parent


class NativeVlmStageTests(unittest.TestCase):
    def test_non_schema_model_error_is_not_retried_as_schema_error(self) -> None:
        async def run() -> None:
            registry = ProfileRegistry(
                profile_root=AGENT_ROOT / "profiles",
                workspace_root=ROOT,
                allow_legacy_references=True,
            )
            registry.load_all()
            profile = registry.bind("zh")
            gateway = FakeModelGateway(
                [ModelGatewayError(ErrorCode.INVALID_REQUEST, "model rejected image", retryable=False)]
            )
            adapter = ZhVlmExtractionStageAdapter(
                AgentSettings(model_base_url="http://model.invalid/v1", default_model="fake-vlm"),
                gateway,
            )
            with tempfile.TemporaryDirectory() as temporary:
                image = Path(temporary) / "source.png"
                image.write_bytes(b"image")
                with self.assertRaisesRegex(ModelGatewayError, "model rejected image"):
                    await adapter.classify_page(
                        PageClassificationRequest(
                            run_id="run-1",
                            project_id="project-1",
                            profile=profile,
                            page=DrawingPageInput(pdf_page_number=1, image_path=image),
                        )
                    )

            self.assertEqual(len(gateway.calls), 1)

        asyncio.run(run())

    def test_three_stage_adapter_sends_query_and_few_shot_images(self) -> None:
        async def run() -> None:
            registry = ProfileRegistry(
                profile_root=AGENT_ROOT / "profiles",
                workspace_root=ROOT,
                allow_legacy_references=True,
            )
            registry.load_all()
            profile = registry.bind("zh")
            gateway = FakeModelGateway(
                [
                    '{"plant_function":"002.C","page_number":3,"confidence":0.9}',
                    '{"pdf_page_number":12,"units":[{"unit_id":"u1","wire_number":"0272","connections":[]}]}',
                    '{"end":{"device":"-TA2","terminal":"U2"},"status":"resolved"}',
                ]
            )
            adapter = ZhVlmExtractionStageAdapter(
                AgentSettings(model_base_url="http://model.invalid/v1", default_model="fake-vlm"),
                gateway,
            )
            with tempfile.TemporaryDirectory() as temporary:
                source = Path(temporary) / "source.png"
                target = Path(temporary) / "target.png"
                source.write_bytes(b"source image")
                target.write_bytes(b"target image")
                source_page = DrawingPageInput(pdf_page_number=12, image_path=source)
                target_page = DrawingPageInput(pdf_page_number=13, image_path=target)

                classification = await adapter.classify_page(
                    PageClassificationRequest(
                        run_id="run-1",
                        project_id="project-1",
                        profile=profile,
                        page=source_page,
                    )
                )
                scan = await adapter.scan_page(
                    PageScanRequest(
                        run_id="run-1",
                        project_id="project-1",
                        profile=profile,
                        page=source_page,
                    )
                )
                cross_page = await adapter.resolve_cross_page(
                    CrossPageCompletionRequest(
                        run_id="run-1",
                        project_id="project-1",
                        profile=profile,
                        task_id="task-1",
                        target_page=target_page,
                        task_context=(
                            '{"task_id":"task-1","line_number":"002C0601",'
                            '"source_record":{"drawing_function":"002.C",'
                            '"start_terminal":"XA:1","current":"400A"},'
                            '"references":[{"target_function":"002.C"}]}'
                        ),
                    )
                )

            self.assertEqual(classification.drawing_page_number, 3)
            self.assertEqual(scan.units[0].wire_number, "0272")
            self.assertEqual(cross_page.task_id, "task-1")
            self.assertEqual(len(gateway.calls), 3)
            image_parts = [
                part
                for request in gateway.calls
                for message in request.messages
                if message["role"] == "user" and isinstance(message["content"], list)
                for part in message["content"]
                if isinstance(part, dict) and part.get("type") == "image_url"
            ]
            self.assertTrue(image_parts)
            self.assertTrue(all(part["image_url"].get("detail") == "auto" for part in image_parts))
            self.assertTrue(
                all(
                    _contains_image(message)
                    for request in gateway.calls
                    for message in request.messages
                    if message["role"] == "user"
                )
            )

            stage2_examples = _example_image_parts(gateway.calls[1].messages)
            self.assertEqual(len(stage2_examples), 1)
            self.assertTrue(all(max(_png_dimensions(part)) <= 1800 for part in stage2_examples))
            stage2_input = gateway.calls[1].messages[-1]["content"][-1]
            self.assertEqual(_decode_image_part(stage2_input), b"source image")

            stage3_examples = _example_image_parts(gateway.calls[2].messages)
            self.assertEqual(len(stage3_examples), 1)
            self.assertTrue(all(max(_png_dimensions(part)) <= 1800 for part in stage3_examples))
            self.assertIn(
                "002c11-xa1-to-002c06-ta2-u2",
                gateway.calls[2].messages[-2]["content"],
            )
            self.assertEqual(
                sum(
                    1
                    for message in gateway.calls[2].messages
                    if message.get("role") == "user"
                    and isinstance(message.get("content"), list)
                    for part in message["content"]
                    if isinstance(part, dict) and part.get("type") == "image_url"
                ),
                2,
            )
            self.assertEqual(
                [_decode_image_part(part) for part in gateway.calls[2].messages[-1]["content"][1:]],
                [b"target image"],
            )

        asyncio.run(run())


def _contains_image(message: dict) -> bool:
    content = message.get("content")
    return isinstance(content, list) and any(
        isinstance(item, dict) and item.get("type") == "image_url" for item in content
    )


def _example_image_parts(messages: list[dict]) -> list[dict]:
    return [
        part
        for message in messages[1:-1]
        if message.get("role") == "user" and isinstance(message.get("content"), list)
        for part in message["content"]
        if isinstance(part, dict) and part.get("type") == "image_url"
    ]


def _decode_image_part(part: dict) -> bytes:
    return base64.b64decode(part["image_url"]["url"].split(",", 1)[1])


def _png_dimensions(part: dict) -> tuple[int, int]:
    image_bytes = _decode_image_part(part)
    return struct.unpack(">II", image_bytes[16:24])


if __name__ == "__main__":
    unittest.main()
