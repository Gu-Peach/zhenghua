"""Only a complete, explicitly selected range produces physical replacement candidates."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.agent.explain_agent.models import ExplainActor, ExplainTurn, RescanRequest
from src.agent.explain_agent.rescan_candidates import build_candidate
from src.agent.explain_agent.rescan_execution import CandidateSession, execute_rescan
from src.agent.explain_agent.tools.rescan import RescanConnectionsTool
from src.config import AgentSettings
from src.harness.model_gateway import FakeModelGateway


def job():
    return {
        "id": str(uuid4()),
        "request": {"scope": {"workspace_code": "001.A"}, "fields": "all", "result_mode": "replace_scope"},
        "project_snapshot": {"scan_pages": [{"pdf_page_number": 1}]},
        "completed_scan_pages": [1],
        "baseline": [
            {
                "id": str(uuid4()),
                "record_version": 3,
                "source_pdf_page_number": 1,
                "source_drawing_page": "001A01",
                "workspace_code": "001.A",
                "principle_number": "P",
                "start_terminal": "OLD",
                "end_terminal": "OLD-END",
            }
            for _ in range(7)
        ],
    }


def scanned():
    return [
        {
            "source_pdf_page_number": 1,
            "source_drawing_page": "001A01",
            "workspace_code": "001.A",
            "principle_number": "P",
            "start_terminal": f"X1:{i}",
            "end_terminal": f"X2:{i}",
            "start_terminal_coordinates": {"x": 0.1, "y": 0.2, "pdf_page_number": 1},
            "end_terminal_coordinates": {"x": 0.3, "y": 0.4, "pdf_page_number": 2},
        }
        for i in range(6)
    ]


def test_all_scope_removes_seven_old_rows_and_writes_exactly_six_even_with_ambiguous_old_identity():
    work = job()
    before = deepcopy(work)
    result = build_candidate(work, scanned(), [])
    assert result.replacement is not None and len(result.replacement.removed) == 7
    assert result.model_dump(mode="json", exclude_unset=True)["replacement"]["version"] == 1
    assert len(result.changes) == 6 and not result.unmatched_ids
    assert all(change.action == "insert" and change.record_version == 0 for change in result.changes)
    assert not {str(change.connection_id) for change in result.changes}.intersection(
        row["id"] for row in work["baseline"]
    )
    assert work == before


def test_empty_completed_scan_explicitly_previews_deletion_of_old_scope():
    result = build_candidate(job(), [], [])
    assert not result.changes and len(result.replacement.removed) == 7
    assert any("替换为空表" in warning for warning in result.warnings)


@pytest.mark.parametrize("fault", ["missing_page", "extra_page", "outside_output", "row_scope", "end_fields"])
def test_failed_incomplete_or_partial_input_cannot_generate_range_deletion(fault):
    work = job()
    values = scanned()
    if fault == "missing_page":
        work["completed_scan_pages"] = []
    elif fault == "extra_page":
        work["completed_scan_pages"].append(2)
    elif fault == "outside_output":
        values[0]["source_pdf_page_number"] = 2
    elif fault == "row_scope":
        work["request"]["scope"]["connection_ids"] = [work["baseline"][0]["id"]]
    else:
        work["request"]["fields"] = "end"
    with pytest.raises(ValueError):
        build_candidate(work, values, [])


@pytest.mark.parametrize(
    "scope,fields,mode",
    [
        ({"workspace_code": "A"}, "all", "replace_scope"),
        ({"drawing_page": "001A01"}, "all", "replace_scope"),
        ({"pdf_page_numbers": [1, 2]}, "all", "replace_scope"),
        ({"connection_ids": [str(uuid4())]}, "all", "patch"),
        ({"principle_numbers": ["P1"]}, "all", "patch"),
        ({"workspace_code": "A"}, "end", "patch"),
    ],
)
def test_tool_programmatically_owns_mode_instead_of_the_model(scope, fields, mode):
    async def run():
        repo = SimpleNamespace(start_rescan=AsyncMock(return_value=None))
        request = RescanRequest(
            scope=scope, fields=fields, result_mode="patch" if mode == "replace_scope" else "replace_scope"
        )
        await RescanConnectionsTool.execute(
            repo,
            ExplainTurn(project_id=uuid4(), connection_id=uuid4()),
            ExplainActor(user_id=uuid4()),
            request,
        )
        assert repo.start_rescan.await_args.args[3].result_mode == mode
        assert "result_mode" not in RescanConnectionsTool.definition()["function"]["parameters"]["properties"]

    asyncio.run(run())


def test_partial_row_patch_never_adds_other_scanned_rows_or_deletes_selected_row():
    work = job()
    work["baseline"] = [work["baseline"][0]]
    old = work["baseline"][0]
    old.update(principle_number="ROW1", start_terminal="X1:0")
    work["request"].update(result_mode="patch", scope={"connection_ids": [old["id"]]})
    values = scanned()
    values[0]["principle_number"] = "ROW1"
    result = build_candidate(work, values, [])
    assert result.replacement is None and len(result.changes) == 1
    assert result.changes[0].action == "update" and str(result.changes[0].connection_id) == old["id"]


def test_legacy_queued_full_scan_is_stopped_before_spending_model_calls():
    async def run():
        work = job()
        work["request"].pop("result_mode")
        gateway = FakeModelGateway([])
        with pytest.raises(ValueError, match="before model calls"):
            await execute_rescan(CandidateSession(None, work), AgentSettings(), gateway=gateway)
        assert not gateway.calls

    asyncio.run(run())


def test_partial_facts_preserve_explicit_empty_field_without_inventing_other_edits():
    from src.agent.explain_agent.graph import rescan_facts
    from src.agent.explain_agent.models import RescanRun

    value = RescanRun.model_validate(
        {
            "id": str(uuid4()),
            "project_id": str(uuid4()),
            "conversation_id": str(uuid4()),
            "batch_id": "b",
            "status": "ready",
            "stage": "ready",
            "request": {"scope": {"connection_ids": [str(uuid4())]}, "fields": "end"},
            "profile": {},
            "created_at": "now",
            "updated_at": "now",
            "candidate": {
                "changes": [
                    {
                        "action": "update",
                        "connection_id": str(uuid4()),
                        "record_version": 1,
                        "source_pdf_page_number": 1,
                        "after": {"end_terminal": None},
                    }
                ]
            },
        }
    )
    after = rescan_facts(value)["candidate"]["changes"][0]["after"]
    assert after == {"end_terminal": None}
