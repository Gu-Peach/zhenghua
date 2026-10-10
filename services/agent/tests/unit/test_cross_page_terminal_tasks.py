from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agent_service.graphs.document_extraction.cross_page import (
    _apply_cross_page_completion,
    _build_cross_page_tasks_node,
    _resolve_cross_page_node,
)
from agent_service.profiles.zh.policy import ZhExtractionPolicy


class _SequentialResolver:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.calls: list[tuple[str, str]] = []

    async def resolve_cross_page(
        self,
        target_image: str,
        *,
        task_context: str,
    ) -> dict:
        task_id = str(json.loads(task_context)["task_id"])
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.calls.append((task_id, target_image))
        await asyncio.sleep(0.01)
        self.active -= 1
        return {
            "task_id": task_id,
            "end": {"device": "-TARGET", "terminal": task_id},
            "status": "resolved",
            "confidence": 0.9,
        }


def _runtime(output: Path, resolver: object | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        policy=ZhExtractionPolicy(),
        settings=SimpleNamespace(terminal_strip_mapping={}),
        extraction_client=resolver,
        output_mode="library",
        extraction_errors={},
        validation_warnings=[],
        payload_for=lambda image_path: str(image_path),
        log=lambda _message: None,
    )


class CrossPageTerminalTaskTests(unittest.TestCase):
    def test_stage_three_null_current_preserves_stage_two_current(self) -> None:
        wire_units = {
            "unit-1": {
                "unit_id": "unit-1",
                "connections": [
                    {
                        "connection_id": "connection-1",
                        "current": "400A",
                        "current_basis": "Ir",
                        "current_source_text": "Ir=400A",
                    }
                ],
            }
        }
        task = {
            "unit_id": "unit-1",
            "connection_id": "connection-1",
            "source_pdf_page": 10,
            "target_pdf_page": 20,
            "references": [{"target_pdf_page": 20}],
        }
        result = {
            "end": {"device": "-TA2", "terminal": "U2"},
            "current": None,
            "current_basis": None,
            "current_source_text": None,
            "status": "resolved",
        }

        _apply_cross_page_completion(wire_units, task, result)

        connection = wire_units["unit-1"]["connections"][0]
        self.assertEqual(connection["current"], "400A")
        self.assertEqual(connection["current_basis"], "Ir")
        self.assertEqual(connection["current_source_text"], "Ir=400A")
        self.assertEqual(connection["end"]["terminal"], "U2")

    def test_one_connection_with_multiple_targets_becomes_single_target_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            state = {
                "output_path": str(output),
                "pages": [
                    {"page_number": 10, "image_path": "page-10.png", "function": "002.C"},
                    {"page_number": 20, "image_path": "page-20.png", "function": "002.C"},
                    {"page_number": 30, "image_path": "page-30.png", "function": "003.C"},
                ],
                "drawing_index": {},
                "wiring_records": {},
                "table_rows_by_unit": {},
                "wire_units": {
                    "unit-1": {
                        "unit_id": "unit-1",
                        "wire_number": "0272",
                        "source_pages": [10],
                        "connections": [
                            {
                                "connection_id": "connection-1",
                                "origin_pdf_page": 10,
                                "line_number": "002C1001",
                                "start": {"device": "-XD21", "terminal": "1"},
                                "end": None,
                                "references": [
                                    {"raw": "003.C/1", "target_pdf_page": 30},
                                    {"raw": "002.C/2", "target_pdf_page": 20},
                                ],
                                "status": "needs_review",
                            }
                        ],
                    }
                },
            }

            update = _build_cross_page_tasks_node(state, _runtime(output))

            tasks = update["cross_page_tasks"]
            self.assertEqual([task["target_pdf_page"] for task in tasks], [20, 30])
            self.assertEqual(
                [task["task_id"] for task in tasks],
                ["connection-1:target-p20", "connection-1:target-p30"],
            )
            self.assertTrue(all("target_pdf_pages" not in task for task in tasks))
            self.assertTrue(all(len(task["references"]) == 1 for task in tasks))

    def test_stage_three_resolves_terminal_tasks_sequentially_with_one_target(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary)
                resolver = _SequentialResolver()
                runtime = _runtime(output, resolver)
                tasks = [
                    {
                        "task_id": "task-20",
                        "unit_id": "unit-1",
                        "connection_id": "connection-1",
                        "source_pdf_page": 10,
                        "target_pdf_page": 20,
                        "references": [{"target_pdf_page": 20}],
                    },
                    {
                        "task_id": "task-30",
                        "unit_id": "unit-2",
                        "connection_id": "connection-2",
                        "source_pdf_page": 10,
                        "target_pdf_page": 30,
                        "references": [{"target_pdf_page": 30}],
                    },
                ]
                state = {
                    "output_path": str(output),
                    "pages": [
                        {"page_number": 10, "image_path": "page-10.png"},
                        {"page_number": 20, "image_path": "page-20.png"},
                        {"page_number": 30, "image_path": "page-30.png"},
                    ],
                    "cross_page_tasks": tasks,
                    "wire_units": {},
                }

                update = await _resolve_cross_page_node(state, runtime)

                self.assertEqual(list(update["cross_page_results"]), ["task-20", "task-30"])
                self.assertEqual(resolver.max_active, 1)
                self.assertEqual(
                    resolver.calls,
                    [
                        ("task-20", "page-20.png"),
                        ("task-30", "page-30.png"),
                    ],
                )

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
