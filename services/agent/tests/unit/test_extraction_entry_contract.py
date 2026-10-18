"""Request/output parity between uploaded PDFs and the local Stage2 script."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
from pydantic import ValidationError

from src.agent.extraction_agent.agents.page_scanner import PageScannerAgent
from src.agent.extraction_agent.application.extraction_contract import (
    SCAN_CONTEXT_PREFIX,
    scan_context,
)
from src.agent.extraction_agent.application.incremental import published_rows
from src.agent.extraction_agent.application.page_workflow_extraction import ExtractionStageGraphClient
from src.agent.extraction_agent.domain.models.extraction_stages import (
    DrawingPageInput,
    DrawingReference,
    PageScanData,
    PageScanRequest,
)
from src.agent.extraction_agent.domain.models.wiring import WireRecord
from src.agent.extraction_agent.domain.table_output import output_fields, table_row
from src.agent.extraction_agent.infrastructure.zh_vlm_stages import ZhVlmExtractionStageAdapter
from src.agent.extraction_agent.profiles.abb.policy import AbbExtractionPolicy
from src.config import AgentSettings
from src.harness.model_gateway import FakeModelGateway
from src.profiles import ProfileRegistry
from src.profiles.package import build_package

ROOT = Path(__file__).resolve().parents[4]


def _script():
    spec = importlib.util.spec_from_file_location(
        "local_groups_contract", ROOT / "services/agent/scripts/run_stage2_groups.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 70), False)
    pix.clear_with(255)
    path.write_bytes(pix.tobytes("png"))


def test_prefix_is_the_verified_script_text_and_idempotent() -> None:
    assert SCAN_CONTEXT_PREFIX == (
        "本次测试不提取色标：每条 connection.color 必须为 null。其他字段按图中证据读取。\n"
    )
    assert scan_context(scan_context("page facts")) == SCAN_CONTEXT_PREFIX + "page facts"


def test_frozen_platform_and_local_script_send_identical_scan_requests(tmp_path: Path) -> None:
    async def check() -> None:
        registry = ProfileRegistry(
            profile_root=ROOT / "services/agent/src/agent/extraction_agent/profiles",
            workspace_root=ROOT, allow_legacy_references=True,
        )
        registry.load_all()
        local = registry.bind("zh_crop", allow_experimental=True)
        build_package(registry.resolve("zh_crop", allow_experimental=True), tmp_path / "profiles/selected")
        frozen_registry = ProfileRegistry(profile_root=tmp_path / "profiles", workspace_root=tmp_path)
        frozen_registry.load_all()
        frozen = frozen_registry.bind("zh_crop", allow_experimental=True)
        directory = tmp_path / "platform"
        path = directory / "pages/004.G/6.png"
        _image(path)
        metadata = {
            "pdf_page": 131, "function": "004.G", "internal_page": 6, "object_loc": "+01F35",
            "is_non_wiring": False,
        }
        (directory / "agent").mkdir()
        (directory / "agent/drawing_index.json").write_text(
            json.dumps({"pages": [metadata]}), encoding="utf-8",
        )
        stage_result = {
            "pdf_page_number": 131, "drawing_function": "004.G", "drawing_page_number": 6,
            "units": [{"unit_id": "one", "connections": [
                {"endpoint_role": role, "direction_basis": "visible wire", "color": "red",
                 "line_number": str(index), "start": {"terminal": f"XD3:{index}"}}
                for index, role in enumerate(("source", "receiver", "unknown"), 1)
            ]}],
        }
        settings = AgentSettings(default_model="fake")
        gateways = [FakeModelGateway([json.dumps(stage_result)]) for _ in range(2)]
        adapters = [ZhVlmExtractionStageAdapter(settings, gateway) for gateway in gateways]
        common = {"project_id": "offline", "output_dir": directory}
        platform = ExtractionStageGraphClient(run_id="upload", profile=frozen, stages=adapters[0], **common)
        script = _script().LocalImageClient(
            run_id="local", profile=local, stages=adapters[1],
            pages=[{**metadata, "page_number": 131, "image_path": str(path)}],
            model_context={"completion_max_side": 0}, **common,
        )
        payload = SimpleNamespace(name="6.png", page_number=131, blank=False)
        context = json.dumps({"pdf_page_number": 131, "drawing_function": "004.G"}, ensure_ascii=False)
        first = await platform.scan_page(payload, page_context=context)
        second = await script.scan_page(payload, page_context=context)
        assert first.model_dump() == second.model_dump()
        assert [c.endpoint_role for c in first.units[0].connections] == ["source", "unknown"]
        assert all(c.color is None for c in first.units[0].connections)
        assert first.scan_diagnostics.raw_connections == 3
        assert first.scan_diagnostics.receiver_connections == 1
        assert first.scan_diagnostics.retained_connections == 2
        assert gateways[0].calls[0].messages == gateways[1].calls[0].messages
        assert gateways[0].calls[0].metadata["request_fingerprint"] == (
            gateways[1].calls[0].metadata["request_fingerprint"]
        )
        schema = gateways[0].calls[0].messages[0]["content"].split("输出 JSON Schema：\n", 1)[1]
        assert "scan_diagnostics" not in schema and "PageScanDiagnostics" not in schema
        assert platform._page(payload).plant_function == "004.G"
        assert platform._page(payload).object_location == "+01F35"

    asyncio.run(check())


def test_database_business_fields_follow_the_same_projection_as_script_table() -> None:
    record = WireRecord(
        unit_id="u", connection_id="c", pdf_page_number=61,
        drawing_function="003.C", drawing_page_number=2, line_number="003C0201",
        start_location="+01F11.1", start_terminal="XD10:16",
        end_location="+01F18", end_terminal="X1:L1", current=0, color="red",
        remark="actual remark", source_note="diagnostic only",
        start_terminal_coordinates={"x": .2, "y": .3, "pdf_page_number": 61},
        end_terminal_coordinates={"x": .4, "y": .5, "pdf_page_number": 385},
    )
    state = {
        "pages": [{"page_number": 61, "function": "003.C", "internal_page": 2}],
        "wiring_records": {"u": [record]},
    }
    published = published_rows(state, project_id="p", run_id="r", profile={}, number=61)[0]
    fields = output_fields(record.model_dump(mode="json"))
    for key, value in fields.items():
        expected = value
        if key in {"start_terminal", "end_terminal", "current_value"} and value is not None:
            expected = str(value)
        assert getattr(published, key) == expected
    assert table_row(record.model_dump(mode="json"))[3:9:3] == ["+01F11.1", "+01F18"]
    assert published.color_mark is None and published.remark == "actual remark"


def test_zh_zero_column_is_valid_while_negative_columns_and_zero_pages_are_not() -> None:
    scan = PageScanData.model_validate({"units": [{"unit_id": "u", "connections": [{
        "references": [{"raw": "=098.M/1.0", "target_function": "098.M",
                        "target_drawing_page": 1, "target_column": 0}],
    }]}]})
    assert scan.units[0].connections[0].references[0].target_column == 0
    with pytest.raises(ValidationError):
        DrawingReference(target_column=-1)
    with pytest.raises(ValidationError):
        DrawingReference(target_drawing_page=0)
    reference = AbbExtractionPolicy().prepare_reference(
        {"raw": "/241.0A"}, source_page={"page_number": 1}, drawing_index={},
    )
    assert reference["external"] and reference["target_pdf_page"] is None


@pytest.mark.parametrize("roles,outcome,retained", [
    ([], "no_connections", 0),
    (["receiver"], "receivers_only", 0),
    (["source", "receiver"], "sources_retained", 1),
])
def test_diagnostics_distinguish_empty_model_results_from_receiver_filtering(
    tmp_path: Path, roles: list[str], outcome: str, retained: int,
) -> None:
    async def check() -> None:
        registry = ProfileRegistry(
            profile_root=ROOT / "services/agent/src/agent/extraction_agent/profiles",
            workspace_root=ROOT, allow_legacy_references=True,
        )
        registry.load_all()

        async def scan(request):
            return PageScanData.model_validate({"units": [{"unit_id": "u", "connections": [
                {"endpoint_role": role} for role in roles
            ]}]})

        agent = PageScannerAgent(stages=SimpleNamespace(scan_page=scan))
        result = await agent.run(PageScanRequest(
            run_id="offline", project_id="offline", profile=registry.bind("zh_crop", allow_experimental=True),
            page=DrawingPageInput(pdf_page_number=119, image_path=tmp_path / "not-opened.png"),
        ))
        assert result.scan_diagnostics.outcome == outcome
        assert result.scan_diagnostics.raw_connections == len(roles)
        assert result.scan_diagnostics.retained_connections == retained

    asyncio.run(check())
