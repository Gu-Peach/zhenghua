"""No real model: explicitly supplied pages must drive frozen-start completion."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.agent.explain_agent.models import RescanRequest
from src.agent.explain_agent.rescan_execution import rescan_ends
from src.agent.extraction_agent.domain.models.extraction_stages import CrossPageCompletionData


def context():
    rows = [
        {
            "id": str(uuid4()),
            "source_pdf_page_number": 52,
            "source_drawing_page": "002C06",
            "workspace_code": "002.C",
            "record_version": 1,
            "start_terminal": pin,
            "start_code": "+00",
            "principle_number": f"P{i}",
            "is_cross_page": True,
            "start_terminal_coordinates": {"x": 0.1 + i * 0.01, "y": 0.2, "pdf_page_number": 52},
            "target_pdf_page_number": None,
            "end_terminal": None,
        }
        for i, pin in enumerate(["U2", "V2", "W2", "N", "PE", "X1:6", "X1:5", "X1:3", "X1:1"])
    ]
    session = SimpleNamespace(
        job={
            "profile": {},
            "baseline": rows,
            "request": {
                "fields": "end",
                "target_bindings": [
                    {"connection_ids": [r["id"] for r in rows[:5]], "drawing_page": "002C11"},
                    {"connection_ids": [r["id"] for r in rows[5:]], "drawing_page": "002M03"},
                ],
            },
        },
        warnings=[],
        endpoint_rows=[],
    )

    async def advance(**kw):
        return None

    session.advance = advance
    catalog = SimpleNamespace(
        metadata={
            52: {"function": "002.C", "internal_page": 6, "workspace_page": "002C06"},
            53: {"function": "002.C", "internal_page": 11, "workspace_page": "002C11"},
            56: {"function": "002.M", "internal_page": 3, "workspace_page": "002M03"},
        },
        paths={52: "source", 53: "target1", 56: "target2"},
        details=[],
    )
    calls = []

    class Client:
        async def resolve_cross_page(self, target, **kwargs):
            import json

            task = json.loads(kwargs["task_context"])
            calls.append(task)
            return CrossPageCompletionData.model_validate(
                {
                    "task_id": task["task_id"],
                    "end": {
                        "terminal": "X:1",
                        "terminal_coordinates": {
                            "pdf_page_number": target.page_number,
                            "x": 0.5,
                            "y": 0.5,
                        },
                    },
                }
            )

    return session, catalog, Client(), calls, rows


def test_given_two_business_pages_complete_all_nine_frozen_sources():
    session, catalog, client, calls, rows = context()
    before = deepcopy(rows)
    missing = asyncio.run(rescan_ends(session, catalog, client, rows))
    assert not missing
    assert [task["target_pdf_page"] for task in calls] == [53] * 5 + [56] * 4
    assert [task["source_record"]["start_terminal"] for task in calls] == [r["start_terminal"] for r in rows]
    assert rows == before
    assert [r["target_drawing_page"] for r in session.endpoint_rows] == ["002C11"] * 5 + ["002M03"] * 4


def test_wrong_inherited_source_workspace_reports_actual_target_before_extraction():
    session, catalog, client, calls, _ = context()
    session.job["request"]["target_bindings"][1]["workspace_code"] = "002.C"
    with pytest.raises(ValueError, match=r"002M03.*002.M.*56.*002.C"):
        asyncio.run(rescan_ends(session, catalog, client, session.job["baseline"]))
    assert not calls and not session.endpoint_rows


def test_existing_resolved_reference_is_used_without_rescanning_start():
    session, catalog, client, calls, rows = context()
    session.job["request"]["target_bindings"] = []
    rows[0]["evidence"] = {"record": {"references": [{"target_pdf_page": 53, "external": False}]}}
    missing = asyncio.run(rescan_ends(session, catalog, client, rows))
    assert len(calls) == 1 and calls[0]["target_pdf_page"] == 53
    assert set(missing) == {r["id"] for r in rows[1:]}
    assert len(session.warnings) >= 8


@pytest.mark.parametrize("case", ["unknown_page", "ambiguous_page", "outside_scope"])
def test_bad_explicit_binding_fails_before_any_model_call(case):
    session, catalog, client, calls, rows = context()
    if case == "unknown_page":
        session.job["request"]["target_bindings"][0]["drawing_page"] = "002M33"
    elif case == "ambiguous_page":
        catalog.metadata[57] = {**catalog.metadata[53]}
    else:
        session.job["request"]["target_bindings"][0]["connection_ids"] = [str(uuid4())]
    with pytest.raises(ValueError):
        asyncio.run(rescan_ends(session, catalog, client, rows))
    assert not calls


def test_request_target_binding_is_typed_and_conflicting_row_assignments_rejected():
    session, _, _, _, rows = context()
    body = {"scope": {"connection_ids": [r["id"] for r in rows]}, **session.job["request"]}
    assert len(RescanRequest.model_validate(body).target_bindings) == 2
    body["target_bindings"][1]["connection_ids"].append(rows[0]["id"])
    with pytest.raises(ValidationError):
        RescanRequest.model_validate(body)


def test_one_completion_failure_is_reported_and_other_rows_continue():
    session, catalog, client, calls, rows = context()
    original = client.resolve_cross_page

    async def failing(target, **kwargs):
        if len(calls) == 0:
            calls.append({"failed": True})
            raise ValueError("do not expose provider details")
        return await original(target, **kwargs)

    client.resolve_cross_page = failing
    missing = asyncio.run(rescan_ends(session, catalog, client, rows))
    assert missing == [rows[0]["id"]] and len(session.endpoint_rows) == 8
    assert session.warnings and "provider details" not in str(session.warnings)


def test_wrong_page_coordinates_are_rejected_without_changing_row():
    session, catalog, client, calls, rows = context()

    async def wrong(target, **kwargs):
        return CrossPageCompletionData.model_validate({"task_id": "bad", "end": {
            "terminal": "X:1", "terminal_coordinates": {"x": .5, "y": .5, "pdf_page_number": 999},
        }})

    client.resolve_cross_page = wrong
    missing = asyncio.run(rescan_ends(session, catalog, client, rows))
    assert len(missing) == 9 and not session.endpoint_rows and session.warnings
