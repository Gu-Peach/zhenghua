"""Offline contracts for the shared mechanism; no claims about model accuracy."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from src.agent.extraction_agent.domain.models.extraction_stages import (
    CrossPageCompletionRequest,
    DrawingPageInput,
    TerminalCoordinates,
)
from src.agent.extraction_agent.infrastructure.abb_vlm_stages import AbbVlmExtractionStageAdapter
from src.agent.extraction_agent.infrastructure.document.completion_view import (
    prepare_completion_view,
)
from src.agent.extraction_agent.infrastructure.zh_gantry_reel_vlm_stages import ZhGantryReelVlmAdapter
from src.config import AgentSettings
from src.harness.model_gateway import FakeModelGateway
from src.profiles import ProfileRegistry

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / "services/agent/src/agent/extraction_agent"


def _registry() -> ProfileRegistry:
    registry = ProfileRegistry(
        profile_root=BASE / "profiles", workspace_root=ROOT, allow_legacy_references=True,
    )
    registry.load_all()
    return registry


@pytest.mark.parametrize("key", ["abb", "zh_gantry_reel"])
def test_one_source_case_and_corresponding_target_task(key: str) -> None:
    binding = _registry().bind(key, allow_experimental=True)
    assert binding.rules.extraction.cross_page_input_mode == "target_only"
    folder = binding.resource("wiring_examples")
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["stage2_cases"]) == len(manifest["stage3_cases"]) == 1
    scan_case, completion_case = manifest["stage2_cases"][0], manifest["stage3_cases"][0]
    assert [image["role"] for image in scan_case["images"]] == ["source_page"]
    assert [image["role"] for image in completion_case["images"]] == ["target_page"]
    scan = json.loads((folder / scan_case["expected"]).read_text(encoding="utf-8"))
    task = json.loads((folder / completion_case["input"]).read_text(encoding="utf-8"))
    assert task["source_page"]["pdf_page_number"] == scan["pdf_page_number"]
    candidates = [
        connection for unit in scan["units"] for connection in unit["connections"]
        if connection.get("line_number") == task["line_number"]
        and connection.get("signal_name") == task["signal_name"]
    ]
    assert len(candidates) == 1 and candidates[0]["end"] is None
    for section in ("stage2_cases", "stage3_cases"):
        for case in manifest[section]:
            for relative, checksum in case["checksums"].items():
                assert checksum == "sha256:" + hashlib.sha256((folder / relative).read_bytes()).hexdigest()


@pytest.mark.parametrize("key", ["abb", "zh_gantry_reel"])
def test_real_fixture_crop_roundtrip_budget_and_read_only_input(key: str) -> None:
    import pymupdf

    profile = _registry().bind(key, allow_experimental=True)
    folder = profile.resource("wiring_examples")
    case = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["stage3_cases"][0]
    task = json.loads((folder / case["input"]).read_text(encoding="utf-8"))
    path = folder / case["images"][0]["path"]
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    prepared = prepare_completion_view(
        path, task["references"], target_pdf_page=task["target_page"]["pdf_page_number"],
        rules_path=profile.resource("completion_view_rules"),
        input_max_side=2048, max_total_pixels=6_000_000,
    )
    assert prepared.viewport is not None and prepared.png is not None
    viewport = prepared.viewport
    original, cropped = pymupdf.Pixmap(str(path)), pymupdf.Pixmap(prepared.png)
    scale = min(1, 2048 / max(original.width, original.height))
    assert cropped.width * cropped.height <= int(original.width * scale) * int(original.height * scale)
    assert viewport.width < viewport.original_width and viewport.height == viewport.original_height
    point = TerminalCoordinates(x=.5, y=.6, pdf_page_number=task["target_page"]["pdf_page_number"])
    restored = viewport.to_input_view(viewport.to_full_page(point))
    assert restored.x == pytest.approx(point.x) and restored.y == pytest.approx(point.y)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("key,adapter_type", [
    ("abb", AbbVlmExtractionStageAdapter), ("zh_gantry_reel", ZhGantryReelVlmAdapter),
])
def test_target_only_frozen_source_empty_retry_and_coordinate_mapping(
    tmp_path: Path, key: str, adapter_type: type[AbbVlmExtractionStageAdapter] | type[ZhGantryReelVlmAdapter],
) -> None:
    async def check() -> None:
        binding = _registry().bind(key, allow_experimental=True)
        folder = binding.resource("wiring_examples")
        case = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["stage3_cases"][0]
        task = json.loads((folder / case["input"]).read_text(encoding="utf-8"))
        source = task["source_page"]
        # Exercise the actual Graph task shape, including fields that must not reach the model.
        graph_task = {
            "task_id": task["task_id"],
            "source_page_context": {k: v for k, v in source.items() if k != "drawing_label"},
            "target_page_context": {k: v for k, v in task["target_page"].items() if k != "drawing_label"},
            "references": task["references"],
            "source_record": {
                "signal_name": task["signal_name"], "line_number": task["line_number"],
                "start_device": task["source_component"]["device"],
                "start_terminal": "FROZEN_PIN", "start_terminal_coordinates": {"x": .99, "y": .98},
                "current": "10A", "current_basis": "Ir", "current_source_text": "Ir=10A",
            },
        }
        gateway = FakeModelGateway([
            "{}",
            json.dumps({
                "task_id": task["task_id"], "end": {
                    "terminal": "TARGET_PIN", "terminal_coordinates": {
                        "x": .5, "y": .6, "pdf_page_number": task["target_page"]["pdf_page_number"],
                    },
                }, "current": "999A", "source_note": "matched source sheet and signal at target pin",
            }),
        ])
        adapter = adapter_type(AgentSettings(default_model="fake"), gateway)
        request = CrossPageCompletionRequest(
            run_id="offline", project_id="offline", profile=binding, task_id=task["task_id"],
            source_page=DrawingPageInput(
                pdf_page_number=source["pdf_page_number"], image_path=tmp_path / "MUST_NOT_OPEN.png",
            ),
            target_page=DrawingPageInput(
                pdf_page_number=task["target_page"]["pdf_page_number"],
                image_path=folder / case["images"][0]["path"],
            ), task_context=json.dumps(graph_task),
        )
        result = await adapter.resolve_cross_page(request)
        assert len(gateway.calls) == 2 and result.current is None
        first = gateway.calls[0]
        parts = first.messages[-1]["content"]
        assert sum(part.get("type") == "image_url" for part in parts) == 1
        text = parts[0]["text"]
        assert "FROZEN_PIN" not in text and "start_terminal_coordinates" not in text
        assert task["signal_name"] in text
        if key == "zh_gantry_reel":
            assert '"drawing_label":"1B"' in text and '"drawing_label":"2A"' in text
        view = first.metadata["completion_image_view"]
        assert view["mode"] == "column_crop"
        assert result.end is not None and result.end.terminal_coordinates is not None
        assert result.end.terminal_coordinates.x == pytest.approx(
            (view["left"] + .5 * view["width"]) / view["original_width"]
        )
        assert result.end.terminal_coordinates.y == pytest.approx(.6)

    asyncio.run(check())
