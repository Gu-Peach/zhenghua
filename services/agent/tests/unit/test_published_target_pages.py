"""A resolved page reference is independent of a confirmed physical end terminal."""

from copy import deepcopy

import pytest

from src.agent.explain_agent.rescan_candidates import build_candidate
from src.agent.extraction_agent.application.incremental import published_rows
from src.agent.extraction_agent.domain.models.wiring import WireRecord


def state_for(targets):
    return {
        "pages": [
            {"page_number": 48, "function": "002.C", "internal_page": 1},
            {"page_number": 541, "function": "098.M", "internal_page": 25},
            {"page_number": 562, "function": "100.M", "internal_page": 32},
        ],
        "wiring_records": {
            "u": [
                WireRecord(
                    unit_id="u",
                    connection_id="fo1",
                    pdf_page_number=48,
                    start_terminal="W1:FO1",
                    end_terminal=None,
                    needs_review=True,
                    start_terminal_coordinates={"x": 0.4, "y": 0.3, "pdf_page_number": 48},
                )
            ]
        },
        "cross_page_tasks": [
            {"task_id": f"fo1:{page}", "unit_id": "u", "connection_id": "fo1", "target_pdf_page": page}
            for page in targets
        ],
        "cross_page_results": {f"fo1:{page}": {"end": None} for page in targets},
    }


@pytest.mark.parametrize("targets,expected", [([541], 541), ([541, 562], None), ([999], None), ([], None)])
def test_page_is_preserved_only_when_current_connection_has_a_unique_indexed_target(targets, expected):
    state = state_for(targets)
    frozen = deepcopy(state)
    row = published_rows(state, project_id="p", run_id="r", profile={}, number=48)[0]
    assert row.target_pdf_page_number == expected
    assert row.target_drawing_page == ("098M25" if expected else None)
    assert row.end_terminal is None and row.end_terminal_coordinates is None and row.needs_review
    assert state == frozen


def test_confirmed_result_wins_over_an_unavailable_candidate_and_other_connections():
    state = state_for([541, 562])
    state["cross_page_results"]["fo1:541"] = {"end": {"terminal": "XD3:194"}}
    state["cross_page_tasks"].append(
        {"task_id": "other", "unit_id": "u", "connection_id": "fo2", "target_pdf_page": 562}
    )
    row = published_rows(state, project_id="p", run_id="r", profile={}, number=48)[0]
    assert row.target_pdf_page_number == 541
    assert row.end_terminal is None and row.needs_review


def test_rescan_candidate_updates_reference_page_and_keeps_unrecognized_terminal_empty():
    row = published_rows(state_for([541]), project_id="p", run_id="r", profile={}, number=48)[0].model_dump(
        mode="json"
    )
    old = {
        **row,
        "record_version": 1,
        "target_pdf_page_number": 562,
        "target_drawing_page": "100M32",
        "end_terminal": "XD3:194",
    }
    candidate = build_candidate(
        {
            "id": "r",
            "baseline": [old],
            "request": {"fields": "end", "scope": {"connection_ids": [old["id"]]}},
        },
        [row],
        [],
    )
    assert len(candidate.changes) == 1
    change = candidate.changes[0]
    assert change.after.target_pdf_page_number == 541 and change.after.target_drawing_page == "098M25"
    final = {**old, **change.after.model_dump(mode="json", exclude_unset=True)}
    assert final["end_terminal"] is None and final["needs_review"]
    assert change.source_pdf_page_number == 48
