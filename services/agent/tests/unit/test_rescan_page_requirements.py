"""Run the existing page Graph with Fake vision; only candidates may be written."""

import asyncio
import copy
import json
from uuid import uuid4

import pymupdf
import pytest

from src.agent.explain_agent.rescan_execution import CandidateSession, execute_rescan
from src.config import AgentSettings
from src.harness.model_gateway import FakeModelGateway
from src.profiles import ProfileRegistry

from .test_explain_agent import OWNER, PROJECT
from .test_explain_rescan import ROOT, MemoryRescan
from .test_rescan_requirements import requirements


def setup():
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 150))
    pixmap.clear_with(255)
    image = pixmap.tobytes("png")
    repository = MemoryRescan(image, image)
    settings = AgentSettings(default_model="fake")
    registry = ProfileRegistry(
        profile_root=settings.profile_root, workspace_root=ROOT, allow_legacy_references=True
    )
    registry.load_all()
    binding = registry.bind("zh", allow_experimental=True)
    starts = ["XA:4", "XA:5", "XA:6", "XA:7", "PE-BAR"]
    baseline = [
        {
            "id": str(uuid4()),
            "record_version": 1,
            "source_pdf_page_number": 1,
            "source_drawing_page": "002C01",
            "workspace_code": "002.C",
            "start_terminal": terminal,
            "principle_number": None,
            "end_terminal": "OLD",
            "is_cross_page": False,
            "start_terminal_coordinates": {"x": 0.1 + i * 0.1, "y": 0.2, "pdf_page_number": 1},
        }
        for i, terminal in enumerate(starts[:4])
    ]
    job = {
        "id": str(uuid4()),
        "project_id": str(PROJECT),
        "created_by": str(OWNER),
        "conversation_id": str(uuid4()),
        "batch_id": "batch-a",
        "lease_token": str(uuid4()),
        "attachment_ids": [],
        "profile": binding.profile.model_dump(mode="json"),
        "baseline": baseline,
        "request": {
            "scope": {"drawing_page": "002C01"},
            "fields": "all",
            "result_mode": "replace_scope",
            "instructions": "核对起点集合，同页追线并读取原理号",
            "requirements": requirements(
                connection_set="rebuild",
                expected_start_terminals=starts,
                required_fields=["start_terminal", "end_terminal", "principle_number"],
            ),
        },
        "project_snapshot": {
            "pages": [
                {
                    "pdf_page_number": n,
                    "workspace_code": "002.C",
                    "drawing_page": f"002C0{n}",
                    "image_path": f"projects/{PROJECT}/pages/{n}.png",
                }
                for n in (1, 2)
            ],
            "scan_pages": [{"pdf_page_number": 1}],
        },
    }
    scan = {
        "units": [
            {
                "unit_id": "u",
                "connections": [
                    {
                        "connection_id": str(i),
                        "endpoint_role": "source",
                        "direction_basis": "visible marked segment",
                        "line_number": f"002C01{i + 1:02d}",
                        "start": {
                            "terminal": terminal,
                            "terminal_coordinates": {"x": 0.1 + i * 0.1, "y": 0.2, "pdf_page_number": 1},
                        },
                        "end": {
                            "terminal": f"XD1:{i + 1}",
                            "terminal_coordinates": {"x": 0.1 + i * 0.1, "y": 0.7, "pdf_page_number": 1},
                        },
                        "is_cross_page": "same_page",
                    }
                    for i, terminal in enumerate(starts)
                ],
            }
        ]
    }
    return repository, settings, binding, job, scan


def test_full_page_rebuild_adds_missing_fifth_start_and_reads_principle_numbers_without_completion():
    async def run():
        repository, settings, binding, job, scan = setup()
        original = copy.deepcopy(job["baseline"])
        gateway = FakeModelGateway([json.dumps(scan)])
        await execute_rescan(CandidateSession(repository, job), settings, binding=binding, gateway=gateway)
        candidate = next(event["candidate"] for event in repository.events if "candidate" in event)
        assert len(candidate["replacement"]["removed"]) == 4 and len(candidate["changes"]) == 5
        assert {change["after"]["start_terminal"] for change in candidate["changes"]} == {
            "XA:4",
            "XA:5",
            "XA:6",
            "XA:7",
            "PE-BAR",
        }
        assert all(change["after"]["principle_number"] for change in candidate["changes"])
        assert len(gateway.calls) == 1 and gateway.calls[0].metadata["rescan_task"] is None
        assert gateway.calls[0].metadata["rescan_operation"] == "page_extraction"
        assert job["baseline"] == original

    asyncio.run(run())


def test_same_page_constraint_never_uses_cross_page_vlm_when_scan_returns_a_reference():
    async def run():
        repository, settings, binding, job, scan = setup()
        connection = scan["units"][0]["connections"][0]
        connection.update(
            is_cross_page="cross_page",
            references=[{"target_function": "002.C", "target_drawing_page": 2}],
        )
        gateway = FakeModelGateway([json.dumps(scan)])
        await execute_rescan(CandidateSession(repository, job), settings, binding=binding, gateway=gateway)
        candidate = next(event["candidate"] for event in repository.events if "candidate" in event)
        assert len(gateway.calls) == 1
        assert any("终点端子" in text for text in candidate["warnings"])
        assert all(change["after"]["needs_review"] for change in candidate["changes"])

    asyncio.run(run())


def test_local_end_mask_keeps_start_id_origin_and_principle_number_and_does_not_add_unselected_rows():
    async def run():
        repository, settings, binding, job, scan = setup()
        old = job["baseline"][0]
        old["principle_number"] = "KEEP"
        job["baseline"] = [old]
        job["request"] = {
            "scope": {"connection_ids": [old["id"]]},
            "fields": "end",
            "instructions": "保留起点，只重新识别同页终点",
            "result_mode": "patch",
            "requirements": requirements(expected_start_terminals=[old["start_terminal"]]),
        }
        gateway = FakeModelGateway([json.dumps(scan)])
        await execute_rescan(CandidateSession(repository, job), settings, binding=binding, gateway=gateway)
        candidate = next(event["candidate"] for event in repository.events if "candidate" in event)
        assert len(candidate["changes"]) == 1 and not candidate.get("replacement")
        change = candidate["changes"][0]
        assert change["connection_id"] == old["id"] and change["source_pdf_page_number"] == 1
        assert change["after"]["end_terminal"] == "XD1:1"
        assert "start_terminal" not in change["after"] and "principle_number" not in change["after"]
        assert old["principle_number"] == "KEEP" and len(gateway.calls) == 1
        assert gateway.calls[0].metadata["rescan_operation"] == "same_page_endpoint_scan"

    asyncio.run(run())


def test_old_v6_checkpoint_is_not_reused_with_the_new_execution_route():
    async def run():
        repository, settings, binding, job, scan = setup()
        job["checkpoint"] = {"configuration": {"contract": "rescan-v6"}}
        gateway = FakeModelGateway([])
        with pytest.raises(ValueError, match="configuration changed"):
            await execute_rescan(
                CandidateSession(repository, job), settings, binding=binding, gateway=gateway
            )
        assert not gateway.calls

    asyncio.run(run())
