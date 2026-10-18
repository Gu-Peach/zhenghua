"""ABB fixture integrity and field contracts, without invoking a real model."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from src.agent.extraction_agent.application.extraction_stage_factory import build_extraction_stage_dispatcher
from src.agent.extraction_agent.domain.models.extraction_stages import (
    CrossPageCompletionData,
    CrossPageCompletionRequest,
    DrawingPageInput,
    PageClassificationData,
    PageClassificationRequest,
    PageScanData,
    PageScanRequest,
)
from src.agent.extraction_agent.infrastructure.document.few_shot import (
    load_cross_page_few_shot_examples,
    load_page_classification_few_shot_examples,
    load_page_scan_few_shot_examples,
)
from src.agent.extraction_agent.profiles.abb import AbbExtractionPolicy
from src.agent.extraction_agent.profiles.extraction_policy import default_extraction_policies
from src.config import AgentSettings
from src.domain.enums import ProfileStatus
from src.harness.model_gateway import FakeModelGateway
from src.profiles.package import build_package, verify_package
from src.profiles.registry import ProfileRegistry

ROOT = Path(__file__).resolve().parents[4]
RESOURCES = ROOT / "services" / "agent" / "src/agent/extraction_agent/prompts" / "abb"
WIRING = RESOURCES / "examples_wiring" / "annotated"


def test_abb_resources_are_independent_and_ready(tmp_path: Path) -> None:
    registry = ProfileRegistry(
        profile_root=ROOT / "services" / "agent" / "src/agent/extraction_agent/profiles",
        workspace_root=ROOT,
        allow_legacy_references=True,
    )
    registry.load_all()
    abb = registry.resolve("abb")
    assert abb.manifest.status == ProfileStatus.ACTIVE
    assert abb.manifest.version == "1.2.1"
    assert abb.manifest.adapter == "abb_native"
    assert "full_document_extraction" in abb.manifest.capabilities
    assert all("prompts/zh" not in str(path).replace("\\", "/") for path in abb.resolved_resources.values())
    package = build_package(abb, tmp_path / "package")
    verify_package(tmp_path / "package", package)
    assert any("provenance.json" in entry.path for entry in package.files)
    # Classification205 plus the205/241/281 wiring images; originals remain outside the package.
    assert sum(Path(entry.path).suffix == ".png" for entry in package.files) == 4


def test_abb_native_policy_is_registered_and_resolves_sheet_reference() -> None:
    policy = default_extraction_policies().resolve("abb_native")
    assert isinstance(policy, AbbExtractionPolicy)
    prepared = policy.prepare_reference(
        {
            "raw": "/241.1A",
            "target_drawing_page": None,
            "target_internal_page": None,
            "target_column": None,
        },
        source_page={"page_number": 1, "function": "LV11"},
        drawing_index={
            "pages": [
                {"pdf_page": 1, "function": "LV11", "internal_page": 205},
                {"pdf_page": 2, "function": "LV12", "internal_page": 241},
            ]
        },
    )
    assert prepared["target_pdf_page"] == 2
    assert prepared["target_function"] == "LV12"
    assert prepared["target_column"] == 1


def test_abb_package_routes_all_three_stages_without_zh_rules() -> None:
    async def run() -> None:
        registry = ProfileRegistry(
            profile_root=ROOT / "services" / "agent" / "src/agent/extraction_agent/profiles",
            workspace_root=ROOT,
            allow_legacy_references=True,
        )
        registry.load_all()
        binding = registry.bind("abb")
        gateway = FakeModelGateway(
            [
                '{"plant_function":"LV11","drawing_page_number":205,"confidence":0.99}',
                '{"pdf_page_number":1,"drawing_function":"LV11","drawing_page_number":205,'
                '"units":[{"unit_id":"q4","connections":[]}]}',
                '{"task_id":"abb-task","end":{"device":"-Q1","terminal":"2"},'
                '"source_note":"matched target reference and Q1 pin","status":"resolved"}',
            ]
        )
        dispatcher = build_extraction_stage_dispatcher(
            AgentSettings(model_base_url="http://model.invalid/v1", default_model="fake"),
            gateway=gateway,
        )
        source = DrawingPageInput(pdf_page_number=1, image_path=RESOURCES / "1.png")
        target = DrawingPageInput(pdf_page_number=2, image_path=RESOURCES / "2.png")
        result1 = await dispatcher.classify_page(
            PageClassificationRequest(
                run_id="abb-run", project_id="abb-project", profile=binding, page=source
            )
        )
        result2 = await dispatcher.scan_page(
            PageScanRequest(
                run_id="abb-run", project_id="abb-project", profile=binding, page=source
            )
        )
        result3 = await dispatcher.resolve_cross_page(
            CrossPageCompletionRequest(
                run_id="abb-run",
                project_id="abb-project",
                profile=binding,
                task_id="abb-task",
                source_page=source,
                target_page=target,
                task_context='{"task_id":"abb-task","source_record":{"start_terminal":"2"}}',
            )
        )
        assert result1.drawing_page_number == 205
        assert result2.drawing_function == "LV11"
        assert result3.end and result3.end.terminal == "2"
        schema = json.loads(gateway.calls[1].messages[0]["content"].split("输出 JSON Schema：\n", 1)[1])
        assert "DrawingEndpoint" in schema["$defs"]
        assert "ZH" not in schema["$defs"]["DrawingEndpoint"]["properties"]["device"].get("description", "")
        assert "endpoint_role" not in schema["$defs"]["ScannedConnection"].get("required", [])
        assert all(call.metadata["profile"] == "abb" for call in gateway.calls)
        request_text = "\n".join(
            str(message["content"])
            for call in gateway.calls
            for message in call.messages
            if message["role"] == "user"
        )
        assert "不使用 ZH 起点白名单" in request_text
        assert "起点端子只能是 XD0" not in request_text
        assert sum(
            item.get("type") == "image_url"
            for item in gateway.calls[-1].messages[-1]["content"]
        ) == 1

    asyncio.run(run())


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
    assert data.pdf_page_number == 1
    assert len(example.images) == 1 and example.images[0].content == (RESOURCES / "1.png").read_bytes()
    assert example.images[0].note and "不是整页穷举结果" in example.images[0].note
    assert len(data.units) == 5 and data.units[0].wire_number is None
    connections = data.units[0].connections
    assert [c.line_number for c in connections] == ["Q4:2205", "Q4:4205", "Q4:6205", "Q4:8205"]
    assert [connection.start.terminal for connection in connections if connection.start] == [
        "Q4:2",
        "Q4:4",
        "Q4:6",
        "Q4:8",
    ]
    for connection in connections:
        assert connection.end is None and connection.is_cross_page.value == "cross_page"
        assert connection.references[0].target_drawing_page == 241
        assert connection.references[0].target_function is None
        assert connection.current is None
        assert connection.start and connection.start.terminal_coordinates
        assert connection.start.terminal_coordinates.pdf_page_number == 1


def test_circle_examples_keep_direct_segments_and_source_sheet_numbers() -> None:
    examples = load_page_scan_few_shot_examples(WIRING)
    fallback = PageScanData.model_validate_json(examples[0].expected_json)
    assert [c.line_number for c in fallback.units[1].connections] == ["Q3:2205", "Q3:4205", "Q3:6205"]
    circles = PageScanData.model_validate_json(
        (WIRING / "stage2/lv21_281_circles.expected.json").read_text(encoding="utf-8")
    )
    connections = [c for u in circles.units for c in u.connections]
    assert len(connections) == 9
    assert [c.line_number for c in connections] == [
        "552281", "553281", "554281", "757281", "758281", "759281",
        "X1:4281", "X1:5281", "X1:6281",
    ]
    assert [c.end.terminal for c in connections[3:6] if c.end] == ["4", "5", "6"]
    assert [c.end.terminal for c in connections[6:] if c.end] == ["1L1", "1L2", "1L3"]


def test_205_marker_pairs_include_busbar_inputs_once() -> None:
    data = PageScanData.model_validate_json(
        (WIRING / "stage2/lv11_205.expected.json").read_text(encoding="utf-8")
    )
    incoming = next(u for u in data.units if u.unit_id == "205-busbar-inputs").connections
    assert len(incoming) == 14
    assert [(c.start.terminal, c.end.terminal, c.line_number) for c in incoming if c.start and c.end] == [
        ("L1", "Q3:1", "224205"), ("L2", "Q3:3", "225205"), ("L3", "Q3:5", "226205"),
        ("L1", "Q5:1", "231205"), ("L2", "Q5:3", "232205"), ("L3", "Q5:5", "233205"),
        ("N", "X1:1", "564205"),
        ("L1", "Q4:1", "227205"), ("L2", "Q4:3", "228205"), ("L3", "Q4:5", "229205"),
        ("N", "Q4:7", "230205"),
        ("L1", "Q6:1", "125205"), ("L2", "Q6:3", "126205"), ("L3", "Q6:5", "127205"),
    ]
    assert len({c.line_number for c in incoming}) == len(incoming)
    assert all(c.is_cross_page.value == "same_page" and not c.references for c in incoming)
    assert all(c.line_number != "Q3:1205" for c in incoming)


def test_205_terminal_strip_label_is_not_pin_or_marker_number() -> None:
    data = PageScanData.model_validate_json(
        (WIRING / "stage2/lv11_205.expected.json").read_text(encoding="utf-8")
    )
    outputs = next(u for u in data.units if u.unit_id == "205-q6-to-x1").connections
    assert [c.line_number for c in outputs] == ["501205", "502205", "503205"]
    assert [c.end.terminal for c in outputs if c.end] == ["X1:11", "X1:12", "X1:13"]
    assert all(c.end and c.end.device == "-X1" and c.end.terminal_board == "X1" for c in outputs)
    fallback = next(u for u in data.units if u.unit_id == "205-x1-to-q103-fallback").connections
    assert [c.line_number for c in fallback] == ["X1:1205", "X1:2205", "X1:3205"]
    assert [c.end.terminal for c in fallback if c.end] == ["Q103:1", "Q103:3", "Q103:5"]
    assert all("." not in c.line_number for u in data.units for c in u.connections if c.line_number)


def test_cross_page_uses_one_target_and_compact_frozen_source() -> None:
    examples = load_cross_page_few_shot_examples(WIRING)
    assert len(examples) == 1
    example = examples[0]
    assert example.input_json
    task = json.loads(example.input_json)
    result = CrossPageCompletionData.model_validate_json(example.expected_json)
    assert result.task_id == task["task_id"]
    assert (task["source_page"]["pdf_page_number"], task["target_page"]["pdf_page_number"]) == (1, 2)
    assert task["source_page"]["drawing_page_number"] == 205
    assert task["signal_name"] == "=LV11-Q4 L1"
    assert "start_terminal" not in example.input_json
    assert "terminal_coordinates" not in example.input_json
    assert [image.role for image in example.images] == ["target_page"]
    assert example.images[0].content == (RESOURCES / "2.png").read_bytes()
    assert "start" not in json.loads(example.expected_json)
    assert result.end and (result.end.location, result.end.device, result.end.terminal) == (
        "+EH.Q21",
        "-Q1",
        "Q1:2",
    )
