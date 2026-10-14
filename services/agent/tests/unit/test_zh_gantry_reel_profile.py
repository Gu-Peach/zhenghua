"""Offline resource/identity regressions; no vision accuracy or database claims."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from src.agent.extraction_agent.application.extraction_stage_factory import build_extraction_stage_dispatcher
from src.config import AgentSettings
from src.agent.extraction_agent.domain.models.extraction_stages import (
    CrossPageCompletionData,
    CrossPageCompletionRequest,
    DrawingPageInput,
    PageClassificationData,
    PageClassificationRequest,
    PageScanData,
    PageScanRequest,
)
from src.agent.extraction_agent.domain.models.wiring import WireRecord
from src.harness.model_gateway import FakeModelGateway
from src.profiles import ProfileRegistry
from src.agent.extraction_agent.profiles.extraction_policy import default_extraction_policies
from src.agent.extraction_agent.profiles.zh_gantry_reel.policy import (
    ZhGantryReelPolicy,
    decode_sheet,
    encode_sheet,
    parse_title_block,
)

ROOT = Path(__file__).resolve().parents[4]
ASSETS = ROOT / "services/agent/src/agent/extraction_agent/prompts/zh_gantry_reel"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def registry() -> ProfileRegistry:
    value = ProfileRegistry(
        profile_root=ROOT / "services/agent/src/agent/extraction_agent/profiles", workspace_root=ROOT, allow_legacy_references=True
    )
    value.load_all()
    return value


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args, **kwargs):
        raise AssertionError("This resource test must not call a provider/database")

    monkeypatch.setattr(httpx.AsyncClient, "request", blocked)
    monkeypatch.setattr(httpx.Client, "request", blocked)


def test_all_25_title_blocks_match_reversible_sheet_inventory() -> None:
    index = read(ASSETS / "sheet-index.json")["raw_to_normalized"]
    evidence = read(ASSETS / "title-block-evidence.json")["pages"]
    assert len(index) == len(evidence) == 25
    expected = {item["pdf_page_number"]: (key, item) for key, item in index.items()}
    for row in evidence:
        function, number, title, non_wiring = parse_title_block(row["title_block_text"])
        raw, item = expected[row["pdf_page_number"]]
        assert (function, number, non_wiring) == (item["function"], item["page"], item["non_wiring"])
        assert decode_sheet(function, number) == raw
    assert sum(item["non_wiring"] for item in index.values()) == 7
    assert encode_sheet("1E") == ("GCR.1", 5)
    assert encode_sheet("3.a", terminal_report=True) == ("GCR.TD", 301)


def test_manifest_counts_schemas_and_every_asset_checksum() -> None:
    assert registry().resolve("zh_gantry_reel", allow_experimental=True).manifest.status == "experimental"
    total = 0
    for folder, sections in [
        ("examples_page_classification", [("cases", PageClassificationData)]),
        ("examples_wiring", [("stage2_cases", PageScanData), ("stage3_cases", CrossPageCompletionData)]),
    ]:
        directory = ASSETS / folder
        manifest = read(directory / "manifest.json")
        for section, model in sections:
            assert len(manifest[section]) == 2
            for case in manifest[section]:
                expected = directory / case["expected"]
                model.model_validate_json(expected.read_text(encoding="utf-8"))
                if case.get("input"):
                    assert (directory / case["input"]).is_file()
                for image in case["images"]:
                    assert (directory / image["path"]).is_file()
                total += 1
    assert total == 6
    rules = read(ASSETS / "field-rules.json")
    policy = ROOT / "services/agent/src/agent/extraction_agent/profiles/zh_gantry_reel/policy.py"
    assert rules["policy_version"] == "0.1.0"
    assert rules["policy_checksum"] == "sha256:" + hashlib.sha256(policy.read_bytes()).hexdigest()
    for asset in read(ASSETS / "provenance.json")["assets"]:
        content = (ASSETS / asset["path"]).read_bytes()
        assert "sha256:" + hashlib.sha256(content).hexdigest() == asset["checksum"]
        assert len(content) == asset["size_bytes"]


def test_address_keeps_row_and_refuses_external_or_invalid_grid() -> None:
    policy = ZhGantryReelPolicy()
    index = {"page_lookup": {"GCR.1:2": 3, "GCR.1:7": 8}}
    result = policy.prepare_reference(
        {"raw": "1G45H / CLIQ3"}, source_page={"page_number": 6}, drawing_index=index
    )
    assert (
        result["target_function"],
        result["target_drawing_page"],
        result["target_column"],
        result["target_pdf_page"],
    ) == ("GCR.1", 7, 45, 8)
    assert "row=H" in result["reason"]
    for raw in ("098M19-PN", "CONT.ON.SH 1B", "1B49C", "1B00C"):
        failed = policy.prepare_reference(
            {"raw": raw, "target_pdf_page": 99}, source_page={"page_number": 6}, drawing_index=index
        )
        assert failed["target_pdf_page"] is None and failed["external"]
    assert policy.parse_references(type("Page", (), {"text": "1B30B 1E09R", "pdf_page": 1})()) == []


def test_literal_board_and_raw_sheet_do_not_inherit_workbook_business_class() -> None:
    policy = default_extraction_policies().resolve("zh_gantry_reel_native")
    record = policy.normalize_record(
        WireRecord(
            start_terminal_board="X3",
            terminal_strip="X4",
            start_terminal="X3:19",
            end_terminal="K",
            drawing_function="GCR.1",
            drawing_page_number=8,
        ),
        {},
    )
    assert record.terminal_strip == "X3"
    assert record.drawing_page == "1H"
    assert record.end_terminal == "K"
    assert record.color is None and record.wire_number is None


def test_two_examples_per_operation_replay_field_by_field_through_fake_adapter() -> None:
    """Check transport/schema compatibility using scripted data, not inferred vision results."""

    async def check() -> None:
        profile = registry().bind("zh_gantry_reel", allow_experimental=True)
        stage1 = ASSETS / "examples_page_classification"
        wiring = ASSETS / "examples_wiring"
        specifications = [
            (stage1, case, "classification") for case in read(stage1 / "manifest.json")["cases"]
        ]
        specifications += [(wiring, case, "scan") for case in read(wiring / "manifest.json")["stage2_cases"]]
        specifications += [
            (wiring, case, "completion") for case in read(wiring / "manifest.json")["stage3_cases"]
        ]
        for directory, case, operation in specifications:
            expected = read(directory / case["expected"])
            gateway = FakeModelGateway([json.dumps(expected, ensure_ascii=False)])
            dispatcher = build_extraction_stage_dispatcher(
                AgentSettings(workspace_root=ROOT, default_model="fake"), gateway=gateway
            )
            page = DrawingPageInput(pdf_page_number=1, image_path=directory / case["images"][0]["path"])
            common = {"run_id": "offline-profile", "project_id": "offline", "profile": profile}
            if operation == "classification":
                result = await dispatcher.classify_page(PageClassificationRequest(**common, page=page))
                model = PageClassificationData
            elif operation == "scan":
                page = page.model_copy(update={"pdf_page_number": expected["pdf_page_number"]})
                result = await dispatcher.scan_page(PageScanRequest(**common, page=page))
                model = PageScanData
            else:
                task = read(directory / case["input"])
                source = page.model_copy(update={"pdf_page_number": task["source_pdf_page"]})
                target = DrawingPageInput(
                    pdf_page_number=task["target_pdf_page"], image_path=directory / case["images"][1]["path"]
                )
                result = await dispatcher.resolve_cross_page(
                    CrossPageCompletionRequest(
                        **common,
                        task_id=task["task_id"],
                        source_page=source,
                        target_page=target,
                        task_context=json.dumps(task, ensure_ascii=False),
                    )
                )
                model = CrossPageCompletionData
                parts = gateway.calls[0].messages[-1]["content"]
                assert sum(item.get("type") == "image_url" for item in parts) == 2
            assert result.model_dump(mode="json") == model.model_validate(expected).model_dump(mode="json"), (
                case["id"]
            )

    asyncio.run(check())
