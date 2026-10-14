"""Offline reproductions of the 002.C/002.M audit, without VLM/DB calls."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from src.agent.extraction_agent.agents.page_scanner import PageScannerAgent
from src.agent.extraction_agent.application.page_workflow_extraction import run_page_workflow_extraction
from src.config import AgentSettings
from src.agent.extraction_agent.domain.models.extraction_stages import (
    CrossPageCompletionData,
    DrawingPageInput,
    PageClassificationData,
    PageScanData,
    PageScanRequest,
    ScannedWireUnit,
)
from src.agent.extraction_agent.domain.models.wiring import WireConnection
from src.agent.extraction_agent.graphs.document_extraction.cross_page import _apply_terminal_task_results
from src.agent.extraction_agent.graphs.document_extraction.helpers import _connection_identity
from src.harness.model_gateway import FakeModelGateway
from src.agent.extraction_agent.infrastructure.abb_vlm_stages import AbbVlmExtractionStageAdapter
from src.agent.extraction_agent.infrastructure.zh_gantry_reel_vlm_stages import ZhGantryReelVlmAdapter
from src.agent.extraction_agent.infrastructure.zh_vlm_stages import (
    ZhVlmExtractionStageAdapter,
    _normalize_cross_page,
    _normalize_page_scan,
)
from src.profiles import ProfileRegistry
from src.agent.extraction_agent.profiles.zh.policy import ZhExtractionPolicy
from src.agent.extraction_agent.profiles.zh.references import prepare_reference

ROOT = Path(__file__).resolve().parents[4]
ASSETS = ROOT / "services/agent/src/agent/extraction_agent/prompts/zh/examples_wiring/002c"


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("Quality smoke tests must not contact provider/database")

    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)
    monkeypatch.setattr(httpx.Client, "request", forbidden)


def binding():
    registry = ProfileRegistry(
        profile_root=ROOT / "services/agent/src/agent/extraction_agent/profiles", workspace_root=ROOT, allow_legacy_references=True
    )
    registry.load_all()
    return registry.bind("zh")


@pytest.mark.parametrize("role,basis", [(None, None), ("source", None), (None, "arrow leaves terminal")])
def test_c02_missing_direction_never_defaults_to_confirmed_source(role, basis) -> None:
    row = {
        "start": {"device": "-Q1", "terminal": "L1"},
        "end": {"device": "-K2", "terminal": "L1"},
        "status": "resolved",
    }
    if role:
        row["endpoint_role"] = role
    if basis:
        row["direction_basis"] = basis
    result = PageScanData.model_validate(
        _normalize_page_scan({"units": [{"connections": [row]}]}, 49, require_direction=True)
    )
    connection = result.units[0].connections[0]
    assert connection.endpoint_role == "unknown"
    assert connection.status == "needs_review"
    assert result.needs_review
    assert connection.end.terminal == "L1"  # Preserve facts; uncertainty does not stop later pages.


def test_fake_vlm_contract_and_receiver_filter(tmp_path: Path) -> None:
    async def check() -> None:
        gateway = FakeModelGateway(
            [
                json.dumps(
                    {
                        "units": [
                            {
                                "connections": [
                                    {
                                        "endpoint_role": "receiver",
                                        "direction_basis": "arrow enters Q1",
                                        "start": {"device": "-Q1", "terminal": "L1"},
                                    },
                                    {
                                        "endpoint_role": "source",
                                        "direction_basis": "arrow leaves K2",
                                        "start": {"device": "-K2", "terminal": "L1"},
                                        "references": [{"raw": "5.1 / -K2_L1"}],
                                        "status": "needs_reference",
                                    },
                                ]
                            }
                        ]
                    }
                )
            ]
        )
        image = tmp_path / "source.png"
        image.write_bytes(b"fake query image")
        adapter = ZhVlmExtractionStageAdapter(AgentSettings(default_model="fake"), gateway)
        result = await PageScannerAgent(stages=adapter).run(
            PageScanRequest(
                run_id="quality",
                project_id="offline",
                profile=binding(),
                page=DrawingPageInput(pdf_page_number=49, image_path=image),
            )
        )
        assert [c.start.device for u in result.units for c in u.connections] == ["-K2"]
        prompt = gateway.calls[0].messages[0]["content"]
        schema = json.loads(prompt.split("输出 JSON Schema：\n", 1)[1])
        assert {"endpoint_role", "direction_basis"} <= set(schema["$defs"]["ScannedConnection"]["required"])
        assert not AbbVlmExtractionStageAdapter.enforce_evidence_contract
        assert not ZhGantryReelVlmAdapter.enforce_evidence_contract

    asyncio.run(check())


@pytest.mark.parametrize(
    "raw,function,page",
    [
        ("/11.1", "002.C", 11),
        ("5.1 / -K2_L1", "002.C", 5),
        ("=.M+01F11.3/3.1", "002.M", 3),
        ("=M+01F11.3/23.1", "002.M", 23),
        ("=080.C+01F12.1/42.1", "080.C", 42),
        ("=005.C+01F25/1.2 / -TA1_W2", "005.C", 1),
    ],
)
def test_literal_wire_address_overrides_model_guess(raw, function, page) -> None:
    result = prepare_reference(
        {"raw": raw, "target_function": "001.F", "target_drawing_page": 999, "target_pdf_page": 999},
        source_page={"page_number": 52, "function": "002.C"},
        drawing_index={"page_lookup": {f"{function}:{page}": 100}},
    )
    assert result["target_function"] == function
    assert result["target_drawing_page"] == page
    assert result["target_pdf_page"] == 100
    assert result["external"] is False


@pytest.mark.parametrize(
    "terminal,device,board",
    [
        ("I92.1", "-KP1-8", None),
        ("Q70.4", "-KP1-11", None),
        ("FC1:FC1_L1.1", "-FC1", None),
        ("FC112_+", "-FC112", None),
        ("5", None, None),
        (None, "-TA1", "X1"),
    ],
)
def test_signal_names_and_bare_unidentified_pins_cannot_be_complete(terminal, device, board) -> None:
    row = WireConnection(
        endpoint_role="source",
        direction_basis="arrow leaves source",
        start={"device": "-K2", "terminal": "L1"},
        end={"device": device, "terminal_board": board, "terminal": terminal},
        status="resolved",
    )
    result, reversed_direction = ZhExtractionPolicy().orient_connection(row)
    assert result is not None and result.status == "needs_review"
    assert not reversed_direction
    assert result.end.terminal == (terminal if terminal in (None, "5") else None)


@pytest.mark.parametrize("terminal,device", [("L1", "-K2"), ("1R", "-TF41"), ("22", "-KP1-8")])
def test_real_non_xd_endpoints_remain_allowed(terminal, device) -> None:
    row = WireConnection(
        endpoint_role="source",
        direction_basis="arrow leaves source",
        start={"device": "-TA1", "terminal": "U2"},
        end={"device": device, "terminal": terminal},
    )
    assert ZhExtractionPolicy().orient_connection(row)[0].status == "complete"


def test_nonempty_end_without_trace_evidence_remains_review() -> None:
    result = CrossPageCompletionData.model_validate(
        _normalize_cross_page(
            {"end": {"device": "-TF41", "terminal": "2R"}, "status": "resolved"},
            "fo2",
            require_evidence=True,
        )
    )
    assert result.status == "needs_review" and result.needs_review
    assert result.end.terminal == "2R"


def test_m03_separate_branches_preserve_both_ends_and_ambiguous_multi_reference_stays_review() -> None:
    branches = [
        WireConnection(
            line_number="003G0121",
            start={"device": "-XD3", "terminal": "16"},
            references=[{"raw": f"=.C+00/{page}.3"}],
        )
        for page in (5, 6)
    ]
    assert _connection_identity("u", branches[0]) != _connection_identity("u", branches[1])
    assert _connection_identity("u", branches[0]) == _connection_identity("u", branches[0].model_copy())
    units = {
        "u": {
            "connections": [
                {"connection_id": "ta1", "start": {"device": "-XD3", "terminal": "16"}},
                {"connection_id": "ta2", "start": {"device": "-XD3", "terminal": "16"}},
                {"connection_id": "ambiguous", "start": {"device": "-XD3", "terminal": "16"}},
            ]
        }
    }
    tasks, results = [], {}
    for name, page in [("ta1", 51), ("ta2", 52)]:
        result = {"end": {"device": "-" + name.upper(), "terminal": "X1:6"}, "status": "resolved"}
        for cid in (name, "ambiguous"):
            tid = f"{cid}:{page}"
            tasks.append(
                {
                    "task_id": tid,
                    "unit_id": "u",
                    "connection_id": cid,
                    "source_pdf_page": 56,
                    "target_pdf_page": page,
                }
            )
            results[tid] = result
    _apply_terminal_task_results(units, tasks, results)
    connections = units["u"]["connections"]
    assert [c["end"]["device"] for c in connections[:2]] == ["-TA1", "-TA2"]
    assert connections[2]["end"] is None and connections[2]["status"] == "needs_review"


def test_multiple_literal_addresses_do_not_choose_first_target() -> None:
    result = prepare_reference(
        {"raw": "=.C+00/5.3 / =.C+00/6.3", "target_pdf_page": 51},
        source_page={"page_number": 56, "function": "002.M"},
        drawing_index={},
    )
    assert result["target_pdf_page"] is None and result["external"]


def test_fan_out_survives_full_page_graph_and_saved_resume(tmp_path: Path) -> None:
    import pymupdf

    class Stages:
        def __init__(self):
            self.calls = []

        async def classify_page(self, request):
            return PageClassificationData(
                plant_function="002.C", drawing_page_number=request.page.pdf_page_number
            )

        async def scan_page(self, request):
            number = request.page.pdf_page_number
            self.calls.append(f"scan:{number}")
            if number != 1:
                return PageScanData()
            return PageScanData(
                units=[
                    ScannedWireUnit(
                        unit_id="branches",
                        connections=[
                            WireConnection(
                                local_connection_id=f"branch-{page}",
                                line_number="003G0121",
                                endpoint_role="source",
                                direction_basis="each branch arrow leaves XD3:16",
                                start={"device": "-XD3", "terminal": "XD3:16"},
                                references=[
                                    {
                                        "raw": f"{page}.1 / branch",
                                        "target_drawing_page": page,
                                        "target_function": "002.C",
                                    }
                                ],
                                status="needs_reference",
                            )
                            for page in (2, 3)
                        ],
                    )
                ]
            )

        async def resolve_cross_page(self, request):
            page = request.target_page.pdf_page_number
            self.calls.append(f"complete:{page}")
            return CrossPageCompletionData(
                end={"device": "-TA1" if page == 2 else "-TA2", "terminal": "X1:6"},
                status="resolved",
                source_note="matched branch along wire to X1:6",
            )

    async def check() -> None:
        pdf = tmp_path / "source.pdf"
        document = pymupdf.open()
        for number in (1, 2, 3):
            document.new_page().insert_text((30, 50), f"Plant Function: 002.C\nPage Number: {number}")
        document.save(pdf)
        document.close()
        stages = Stages()
        kwargs = dict(
            pdf_path=pdf,
            output_dir=tmp_path / "run",
            profile=binding(),
            settings=AgentSettings(workspace_root=ROOT),
            run_id="fan-out",
            project_id="offline",
        )
        with patch(
            "src.agent.extraction_agent.application.page_workflow_extraction.build_extraction_stage_dispatcher",
            return_value=stages,
        ):
            run = await run_page_workflow_extraction(**kwargs)
            records = [r for rows in run.execution.state["wiring_records"].values() for r in rows]
            assert [(r.start_terminal, r.end_device, r.end_terminal) for r in records] == [
                ("XD3:16", "-TA1", "X1:6"),
                ("XD3:16", "-TA2", "X1:6"),
            ]
            assert all(r.status == "resolved" for r in records)
            assert len({r.connection_id for r in records}) == 2
            assert stages.calls == ["scan:1", "complete:2", "complete:3", "scan:2", "scan:3"]
            await run_page_workflow_extraction(**kwargs)
            assert len(stages.calls) == 5  # Completed pages restore both branches without new calls.

    asyncio.run(check())


def test_fixed_actual_image_cases_validate_fields_and_manifest_paths() -> None:
    manifest = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
    for section in ("stage2_cases", "stage3_cases"):
        for case in manifest[section]:
            assert (ASSETS / case["expected"]).is_file()
            for image in case["images"]:
                assert (ASSETS / image["path"]).is_file()
            payload = json.loads((ASSETS / case["expected"]).read_text(encoding="utf-8"))
            if section == "stage3_cases":
                CrossPageCompletionData.model_validate(payload)
                assert (ASSETS / case["input"]).is_file()
            else:
                PageScanData.model_validate(payload)

    def connections(path):
        return (
            PageScanData.model_validate(json.loads((ASSETS / path).read_text(encoding="utf-8")))
            .units[0]
            .connections
        )

    c02 = connections("stage2/002c02.expected.json")
    assert [(c.start.device, c.line_number, c.references[0].target_drawing_page) for c in c02] == [
        (device, prefix + str(i) if i < 4 else "PE", page)
        for device, prefix, page in [("-K2", "002C020", 5), ("-K3", "002C021", 6)]
        for i in range(1, 5)
    ]
    m03 = connections("stage2/002m03_branches.expected.json")
    assert len({c.local_connection_id for c in m03}) == 2
    assert [(c.start.terminal, c.references[0].target_drawing_page) for c in m03] == [
        ("XD3:16", 5),
        ("XD3:16", 6),
    ]
    optical = CrossPageCompletionData.model_validate(
        json.loads((ASSETS / "completion/w1_fo2_to_tf41.expected.json").read_text(encoding="utf-8"))
    )
    assert (optical.end.device, optical.end.terminal) == ("-TF41", "1R")


def test_quality_asset_and_validator_checksums() -> None:
    provenance = json.loads((ASSETS / "quality-provenance.json").read_text(encoding="utf-8"))
    assert provenance["version"] == binding().profile.version == "2.0.2"
    for section, directory in [("assets", ASSETS), ("policy_sources", ROOT)]:
        for entry in provenance[section]:
            assert (
                "sha256:" + hashlib.sha256((directory / entry["path"]).read_bytes()).hexdigest()
                == entry["checksum"]
            )


def test_fixed_cases_survive_fake_adapter_without_field_loss() -> None:
    async def check() -> None:
        manifest = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
        cases = manifest["stage2_cases"]
        for case in cases:
            response = (ASSETS / case["expected"]).read_text(encoding="utf-8")
            gold = PageScanData.model_validate_json(response)
            gateway = FakeModelGateway([response])
            result = await PageScannerAgent(
                stages=ZhVlmExtractionStageAdapter(
                    AgentSettings(default_model="fake"),
                    gateway,
                )
            ).run(
                PageScanRequest(
                    run_id="fixed-regression",
                    project_id="offline",
                    profile=binding(),
                    page=DrawingPageInput(pdf_page_number=1, image_path=ASSETS / case["images"][0]["path"]),
                )
            )
            assert [c.model_dump(mode="json") for u in result.units for c in u.connections] == [
                c.model_dump(mode="json") for u in gold.units for c in u.connections
            ], case["id"]

    asyncio.run(check())
