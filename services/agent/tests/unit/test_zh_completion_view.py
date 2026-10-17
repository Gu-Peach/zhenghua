from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from src.agent.extraction_agent.domain.models.extraction_stages import (
    CrossPageCompletionRequest,
    DrawingPageInput,
    TerminalCoordinates,
)
from src.agent.extraction_agent.infrastructure.zh_vlm_stages import ZhVlmExtractionStageAdapter
from src.agent.extraction_agent.profiles.zh.completion_view import (
    CompletionViewRules,
    prepare_completion_example_view,
    prepare_completion_view,
    transform_completion_points,
)
from src.config import AgentSettings
from src.harness.model_gateway import FakeModelGateway
from src.profiles import ProfileRegistry

ROOT = Path(__file__).resolve().parents[4]


def _image(path: Path, width: int = 1000, height: int = 700) -> None:
    import pymupdf

    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height), False)
    pix.clear_with(255)
    pix.set_rect(pymupdf.IRect(int(width * 0.4), 0, int(width * 0.5), height), (255, 0, 0))
    path.write_bytes(pix.tobytes("png"))


def _rules(path: Path) -> Path:
    path.write_text(CompletionViewRules().model_dump_json(), encoding="utf-8")
    return path


def test_crop_preserves_source_file_and_original_input_pixel_allowance(tmp_path: Path) -> None:
    import pymupdf

    path = tmp_path / "page.png"
    _image(path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    view = prepare_completion_view(
        path,
        [{"target_column": 4}],
        target_pdf_page=139,
        rules_path=_rules(tmp_path / "rules.json"),
        input_max_side=200,
        max_total_pixels=6_000_000,
    )
    assert view.viewport is not None and view.png is not None
    png = pymupdf.Pixmap(view.png)
    assert png.width * png.height <= 200 * 140
    assert view.viewport.left < 450 < view.viewport.left + view.viewport.width
    assert png.pixel(png.width // 2, png.height // 2)[:3] == (255, 0, 0)
    assert view.viewport.top == 0 and view.viewport.height == 700
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("refs", [[], [{"target_column": 99}], [{"target_column": 1}, {"target_column": 4}]])
def test_unreliable_column_falls_back_before_any_model_request(tmp_path: Path, refs: list[dict]) -> None:
    view = prepare_completion_view(
        tmp_path / "not-opened.png",
        refs,
        target_pdf_page=139,
        rules_path=_rules(tmp_path / "rules.json"),
        input_max_side=2048,
        max_total_pixels=6_000_000,
    )
    assert view.png is None and view.viewport is None


def test_no_profile_resource_never_enables_cropping(tmp_path: Path) -> None:
    view = prepare_completion_view(
        tmp_path / "not-opened.png",
        [{"target_column": 1}],
        target_pdf_page=139,
        rules_path=None,
        input_max_side=2048,
        max_total_pixels=6_000_000,
    )
    assert view.viewport is None and view.reason == "profile_has_no_view_rules"


def test_point_roundtrip_and_model_bounds_validation(tmp_path: Path) -> None:
    path = tmp_path / "page.png"
    _image(path)
    prepared = prepare_completion_view(
        path,
        [{"target_column": 4}],
        target_pdf_page=139,
        rules_path=_rules(tmp_path / "rules.json"),
        input_max_side=200,
        max_total_pixels=6_000_000,
    )
    assert prepared.viewport is not None
    full = TerminalCoordinates(x=0.45, y=0.6, pdf_page_number=139)
    local = prepared.viewport.to_input_view(full)
    restored = prepared.viewport.to_full_page(local)
    assert restored.x == pytest.approx(full.x) and restored.y == pytest.approx(full.y)
    assert restored.pdf_page_number == 139
    with pytest.raises(ValidationError):
        transform_completion_points(
            {"end": {"terminal": "X2:9", "terminal_coordinates": {"x": 2, "y": 0.5, "pdf_page_number": 139}}},
            prepared.viewport,
            to_full_page=True,
        )


def test_example_expected_and_query_use_the_same_view_coordinate_space(tmp_path: Path) -> None:
    import base64

    path = tmp_path / "page.png"
    _image(path)
    point = {"x": 0.45, "y": 0.6, "pdf_page_number": 139}
    expected = {"end": {"terminal": "X2:9", "terminal_coordinates": point}}
    original = {
        "images": [
            {
                "role": "target_page",
                "path": str(path),
                "data_url": "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode(),
            }
        ],
        "input_json": json.dumps(
            {
                "context_version": 2,
                "target_page": {"pdf_page_number": 139},
                "references": [{"target_column": 4}],
            }
        ),
        "expected_json": json.dumps(expected),
    }
    prepared = prepare_completion_example_view(
        original,
        rules_path=_rules(tmp_path / "rules.json"),
        input_max_side=200,
        max_total_pixels=6_000_000,
        fewshot_max_side=1800,
    )
    task = json.loads(prepared["input_json"])
    assert task["context_version"] == 3 and task["image_view"]["column"] == 4
    assert json.loads(prepared["expected_json"])["end"]["terminal_coordinates"]["x"] != point["x"]
    assert json.loads(original["expected_json"]) == expected


def test_single_completion_call_converts_view_coordinates_back_to_full_page(tmp_path: Path) -> None:
    async def check() -> None:
        path = tmp_path / "page.png"
        _image(path)
        registry = ProfileRegistry(
            profile_root=ROOT / "services/agent/src/agent/extraction_agent/profiles",
            workspace_root=ROOT,
            allow_legacy_references=True,
        )
        registry.load_all()
        gateway = FakeModelGateway(
            [
                json.dumps(
                    {
                        "end": {
                            "terminal": "X2:9",
                            "terminal_coordinates": {"x": 0.5, "y": 0.6, "pdf_page_number": 139},
                        },
                        "source_note": "visible matching reference and target pin",
                    }
                )
            ]
        )
        adapter = ZhVlmExtractionStageAdapter(
            AgentSettings(default_model="fake", model_input_max_image_side=200), gateway
        )
        result = await adapter.resolve_cross_page(
            CrossPageCompletionRequest(
                run_id="offline",
                project_id="offline",
                profile=registry.bind("zh_crop", allow_experimental=True),
                task_id="one",
                target_page=DrawingPageInput(pdf_page_number=139, image_path=path),
                task_context=json.dumps(
                    {
                        "task_id": "one",
                        "source_pdf_page": 123,
                        "references": [{"target_column": 4, "target_pdf_page": 139}],
                    }
                ),
            )
        )
        assert len(gateway.calls) == 1
        metadata = gateway.calls[0].metadata["completion_image_view"]
        assert metadata["mode"] == "column_crop"
        assert result.end.terminal_coordinates.x == pytest.approx(
            (metadata["left"] + 0.5 * metadata["width"]) / metadata["original_width"]
        )
        assert result.end.terminal_coordinates.y == pytest.approx(0.6)
        assert result.end.terminal_coordinates.pdf_page_number == 139
        content = gateway.calls[0].messages[-1]["content"]
        assert sum(item.get("type") == "image_url" for item in content) == 1

    asyncio.run(check())
