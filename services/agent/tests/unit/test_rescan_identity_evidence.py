"""Direction correction, identity ambiguity and supplementary-image role regression."""

import asyncio
import base64
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pymupdf
import pytest

from src.agent.explain_agent.rescan_candidates import build_candidate
from src.agent.explain_agent.rescan_execution import (
    CandidateSession,
    DetailGateway,
    active_pages,
    active_task,
    execute_rescan,
)
from src.config import AgentSettings
from src.harness.model_gateway import FakeModelGateway, ModelRequest


def point(x, page=3):
    return {"x": x, "y": 0.65, "pdf_page_number": page}


def test_full_rescan_matches_origin_pin_after_direction_correction_and_preserves_ids():
    numbers = {1: "LINE1", 2: "LINE2", 3: "SHARED", 6: "LINE6"}
    baseline = [
        {
            "id": str(uuid4()),
            "record_version": 7,
            "source_pdf_page_number": 3,
            "source_drawing_page": "003C01",
            "workspace_code": "003.C",
            "principle_number": numbers[pin],
            "start_code": "OLD",
            "start_terminal": "X3:1" if pin == 1 else f"XD3:{pin}",
            "end_code": "+PANEL",
            "end_terminal": f"X3:{pin}",
            "start_terminal_coordinates": None if pin == 1 else point(0.2, 2),
            "end_terminal_coordinates": point(x),
        }
        for pin, x in ((1, 0.356), (2, 0.376), (3, 0.396), (6, 0.456))
    ]
    saved = deepcopy(baseline)
    scanned = [
        {
            "source_pdf_page_number": 3,
            "source_drawing_page": "003C01",
            "workspace_code": "003.C",
            "principle_number": numbers.get(pin, "SHARED"),
            "start_code": "+PANEL",
            "start_terminal": f"X3:{pin}",
            "end_code": "+OTHER",
            "end_terminal": f"XD3:{pin + 100}",
            "start_terminal_coordinates": point(0.34 + pin * 0.04),
            "end_terminal_coordinates": point(0.3, 2),
        }
        for pin in range(1, 7)
    ]
    result = build_candidate(
        {
            "id": str(uuid4()),
            "baseline": baseline,
            "request": {"scope": {"drawing_page": "003C01"}, "fields": "all"},
        },
        scanned,
        [],
    )
    assert not result.unmatched_ids
    updates = {str(change.connection_id): change for change in result.changes if change.action == "update"}
    assert set(updates) == {row["id"] for row in baseline}
    for row, pin in zip(baseline, (1, 2, 3, 6), strict=True):
        final = {**row, **updates[row["id"]].after.model_dump(mode="json", exclude_unset=True)}
        assert final["start_terminal"] == f"X3:{pin}"
        assert updates[row["id"]].record_version == 7 and updates[row["id"]].source_pdf_page_number == 3
    assert updates[baseline[0]["id"]].after.start_terminal_coordinates is not None
    assert {change.after.start_terminal for change in result.changes if change.action == "insert"} == {
        "X3:4",
        "X3:5",
    }
    assert baseline == saved


def test_matching_unique_number_never_moves_an_existing_row_to_another_origin_page():
    original = {
        "id": str(uuid4()),
        "record_version": 1,
        "source_pdf_page_number": 3,
        "principle_number": "UNIQUE",
        "start_terminal": "X1:1",
    }
    new = {
        "source_pdf_page_number": 4,
        "principle_number": "UNIQUE",
        "start_terminal": "X1:1",
        "start_terminal_coordinates": point(0.2, 4),
        "end_terminal": "X2:1",
        "end_terminal_coordinates": point(0.3, 4),
    }
    result = build_candidate(
        {
            "id": str(uuid4()),
            "baseline": [original],
            "request": {"scope": {"workspace_code": "TEST"}, "fields": "all"},
        },
        [new],
        [],
    )
    assert [str(identifier) for identifier in result.unmatched_ids] == [original["id"]]
    assert len(result.changes) == 1 and result.changes[0].action == "insert"


@pytest.mark.parametrize(
    "same_position,terminal,conflict",
    [(False, "X3:5", True), (True, "X3:5", False), (False, "PE-BAR", False)],
)
def test_duplicate_endpoint_positions_are_reviewed_but_shared_pin_and_bus_are_allowed(
    same_position, terminal, conflict
):
    scanned = [
        {
            "source_pdf_page_number": 3,
            "start_terminal": f"X3:{i + 1}",
            "start_terminal_coordinates": point(0.2 + i * 0.04),
            "end_terminal": terminal,
            "end_code": "+OTHER",
            "end_terminal_coordinates": point(0.2 if same_position else 0.2 + i * 0.2, 2),
        }
        for i in range(2)
    ]
    before = deepcopy(scanned)
    result = build_candidate(
        {
            "id": str(uuid4()),
            "baseline": [],
            "request": {"scope": {"drawing_page": "003C01"}, "fields": "all"},
        },
        scanned,
        [],
    )
    assert len(result.changes) == 2
    assert all(change.after.needs_review is conflict for change in result.changes)
    if conflict:
        assert all(change.after.end_terminal_coordinates is None for change in result.changes)
        assert all(
            change.evidence["review_reasons"][0]["code"] == "rescan_endpoint_position_conflict"
            for change in result.changes
        )
        assert result.warnings
    assert scanned == before


def test_completion_keeps_primary_target_after_auxiliary_images_and_binds_one_source(tmp_path):
    async def run():
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20))
        pix.clear_with(255)
        png = pix.tobytes("png")
        paths = {n: tmp_path / f"{n}.png" for n in (2, 3)}
        for path in paths.values():
            path.write_bytes(png)

        async def ensure(_):
            return None

        async def advance(**kwargs):
            return None

        session = SimpleNamespace(
            job={"request": {"instructions": "X3:1到X3:6全部重扫"}}, metrics=[], advance=advance
        )
        catalog = SimpleNamespace(
            paths=paths,
            details=[{"id": "detail", "role": "source", "pdf_page_number": 3, "content": png}],
            session=session,
            ensure=ensure,
        )
        gateway = FakeModelGateway(["{}"])
        request = ModelRequest(
            agent_name="page_scan",
            run_id="test",
            messages=[
                {"role": "system", "content": "schema"},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "PRIMARY_TARGET image_view"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()},
                        },
                    ],
                },
            ],
        )
        pages_token = active_pages.set((2, 3))
        task_token = active_task.set(
            {
                "task_id": "one",
                "source_pdf_page": 3,
                "target_pdf_page": 2,
                "frozen_start_terminal": "X3:1",
                "references": [{"raw": "SIGNAL_X3_1"}],
            }
        )
        try:
            await DetailGateway(gateway, catalog, AgentSettings()).invoke(request)
        finally:
            active_task.reset(task_token)
            active_pages.reset(pages_token)
        result = gateway.calls[0]
        image_messages = [message for message in result.messages if isinstance(message.get("content"), list)]
        assert "PRIMARY_TARGET" in image_messages[-1]["content"][0]["text"]
        texts = str(image_messages[0])
        assert "本条终点所在的目标页" in texts and "本条已冻结起点所在的来源页" in texts
        assert "禁止当作目标页读取终点" in texts
        assert result.metadata["rescan_task"]["frozen_start_terminal"] == "X3:1"
        assert result.metadata["rescan_input_contract"] == 4
        assert all(image["kind"] == "input" for image in result.metadata["vision_images"])

    asyncio.run(run())


@pytest.mark.parametrize("contract", ["rescan-v1", "rescan-v3"])
def test_legacy_input_cache_cannot_mix_with_reordered_completion_evidence(contract):
    async def run():
        gateway = FakeModelGateway([])
        session = CandidateSession(None, {"checkpoint": {"configuration": {"contract": contract}}})
        with pytest.raises(ValueError, match="create a new task"):
            await execute_rescan(session, AgentSettings(), gateway=gateway)
        assert not gateway.calls

    asyncio.run(run())
