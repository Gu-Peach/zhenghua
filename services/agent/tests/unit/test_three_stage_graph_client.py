from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agent_service.application.three_stage_extraction import ExtractionStageGraphClient
from agent_service.domain.models.extraction_stages import (
    CrossPageCompletionData,
    DrawingEndpoint,
    PageClassificationData,
    PageScanData,
)
from agent_service.domain.models.profiles import ProfileBinding
from agent_service.profiles import ProfileRegistry


ROOT = Path(__file__).resolve().parents[4]


class FakeStages:
    async def classify_page(self, request):
        return PageClassificationData(
            plant_function="002.C",
            drawing_page_number=7,
            confidence=0.95,
        )

    async def scan_page(self, request):
        return PageScanData(
            pdf_page_number=request.page.pdf_page_number,
            units=[{"unit_id": "unit-1", "wire_number": "0272", "connections": []}],
        )

    async def resolve_cross_page(self, request):
        return CrossPageCompletionData(
            task_id=request.task_id,
            end=DrawingEndpoint(device="-TA1", terminal="2"),
            status="resolved",
            confidence=0.9,
        )


class ThreeStageGraphClientTests(unittest.TestCase):
    def test_all_three_langgraph_subgraphs_bridge_legacy_graph_contracts(self) -> None:
        async def run() -> None:
            registry = ProfileRegistry(
                profile_root=ROOT / "services" / "agent" / "profiles",
                workspace_root=ROOT,
                allow_legacy_references=True,
            )
            registry.load_all()
            binding: ProfileBinding = registry.bind("zh")

            with tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary)
                incoming = output / "pages" / ".incoming"
                incoming.mkdir(parents=True)
                source_path = incoming / "page_001.png"
                target_path = incoming / "page_002.png"
                source_path.write_bytes(b"source")
                target_path.write_bytes(b"target")
                client = ExtractionStageGraphClient(
                    run_id="run-1",
                    project_id="project-1",
                    profile=binding,
                    stages=FakeStages(),
                    output_dir=output,
                )
                source = SimpleNamespace(
                    name=source_path.name,
                    page_number=1,
                    blank=False,
                    content=b"source",
                )
                target = SimpleNamespace(
                    name=target_path.name,
                    page_number=2,
                    blank=False,
                    content=b"target",
                )

                classified = await client.classify_page(source, context_text="physical page 1")
                classified_path = output / "pages" / "002.C" / "7.png"
                classified_path.parent.mkdir(parents=True)
                classified_path.write_bytes(source_path.read_bytes())
                (output / "agent").mkdir()
                (output / "agent" / "drawing_index.json").write_text(
                    json.dumps(
                        {"pages": [{"pdf_page": 1, "function": "002.C", "internal_page": 7}]},
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                source_path.unlink()
                scanned = await client.scan_page(source, page_context="source context")
                completed = await client.resolve_cross_page(
                    target,
                    task_context=json.dumps({"task_id": "task-1"}),
                )

                self.assertEqual(classified.plant_function, "002.C")
                self.assertEqual(classified.page_number, 7)
                self.assertEqual(client._page(source).image_path, classified_path)
                self.assertEqual(scanned.pdf_page_number, 1)
                self.assertEqual(scanned.units[0].wire_number, "0272")
                self.assertEqual(completed.task_id, "task-1")
                self.assertEqual(completed.end.terminal, "2")

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
