"""ABB fixture integrity and field contracts, without invoking a real model."""

from __future__ import annotations

import json
from pathlib import Path

from agent_service.domain.enums import ProfileStatus
from agent_service.domain.models.extraction_stages import (
    CrossPageCompletionData,
    PageClassificationData,
    PageScanData,
)
from agent_service.infrastructure.document.few_shot import (
    load_cross_page_few_shot_examples,
    load_page_classification_few_shot_examples,
    load_page_scan_few_shot_examples,
)
from agent_service.profiles.package import build_package, verify_package
from agent_service.profiles.registry import ProfileRegistry

ROOT = Path(__file__).resolve().parents[4]
RESOURCES = ROOT / "services" / "agent" / "prompts" / "abb"
WIRING = RESOURCES / "examples_wiring" / "annotated"


def test_abb_resources_are_independent_and_experimental(tmp_path: Path) -> None:
    registry = ProfileRegistry(
        profile_root=ROOT / "services" / "agent" / "profiles",
        workspace_root=ROOT,
        allow_legacy_references=True,
    )
    registry.load_all()
    abb = registry.resolve("abb", allow_experimental=True)
    assert abb.manifest.status == ProfileStatus.EXPERIMENTAL
    assert abb.manifest.version == "1.1.1"
    assert abb.manifest.adapter == "abb_native"
    assert "full_document_extraction" not in abb.manifest.capabilities
    assert all("prompts/zh" not in str(path).replace("\\", "/") for path in abb.resolved_resources.values())
    package = build_package(abb, tmp_path / "package")
    verify_package(tmp_path / "package", package)
    assert any("provenance.json" in entry.path for entry in package.files)
    # One classification image and two shared wiring images; unused cases are not packaged.
    assert sum(Path(entry.path).suffix == ".png" for entry in package.files) == 3


def test_classification_uses_one_current_sheet_not_cont() -> None:
    examples = load_page_classification_few_shot_examples(RESOURCES / "examples_page_classification")
    assert len(examples) == 1
    example = examples[0]
    data = PageClassificationData.model_validate_json(example.expected_json)
    assert (data.plant_function, data.drawing_page_number) == ("LV11", 205)
    assert len(example.images) == 1 and example.images[0].content == (RESOURCES / "1.png").read_bytes()


def test_page_scan_uses_one_full_page_with_cross_page_connections() -> None:
    examples = load_page_scan_few_shot_examples(WIRING)
    assert len(examples) == 1
    example = examples[0]
    data = PageScanData.model_validate_json(example.expected_json)
    assert data.pdf_page_number is None
    assert len(example.images) == 1 and example.images[0].content == (RESOURCES / "1.png").read_bytes()
    assert example.images[0].note and "不是整页穷举结果" in example.images[0].note
    assert len(data.units) == 1 and data.units[0].wire_number is None
    connections = data.units[0].connections
    assert [connection.start.terminal for connection in connections if connection.start] == [
        "2",
        "4",
        "6",
        "8",
    ]
    for connection in connections:
        assert connection.end is None and connection.is_cross_page.value == "cross_page"
        assert connection.references[0].target_drawing_page == 241
        assert connection.references[0].target_function is None
        assert connection.current is None


def test_cross_page_uses_one_source_target_pair_and_frozen_source() -> None:
    examples = load_cross_page_few_shot_examples(WIRING)
    assert len(examples) == 1
    example = examples[0]
    assert example.input_json
    task = json.loads(example.input_json)
    result = CrossPageCompletionData.model_validate_json(example.expected_json)
    assert result.task_id == task["task_id"]
    assert (task["source_pdf_page"], task["target_pdf_page"]) == (1, 2)
    assert task["source_record"]["drawing_page_number"] == 205
    assert task["source_record"]["start_terminal"] == "2"
    assert task["source_record"]["end_terminal"] is None
    assert [image.role for image in example.images] == ["source_page", "target_page"]
    assert [image.content for image in example.images] == [
        (RESOURCES / "1.png").read_bytes(),
        (RESOURCES / "2.png").read_bytes(),
    ]
    assert "start" not in json.loads(example.expected_json)
    assert result.end and (result.end.location, result.end.device, result.end.terminal) == (
        "+EH.Q21",
        "-Q1",
        "2",
    )
