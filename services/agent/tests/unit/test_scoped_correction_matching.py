from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from src.domain.errors import AgentServiceError
from src.agent.extraction_agent.tools.extraction_runner import _replace_scoped


def stored(terminal: str, location: str = "+10F01") -> dict[str, Any]:
    return {
        "connection_id": terminal,
        "start_code": location,
        "start_device": "-XD3",
        "start_location": location,
        "start_terminal_board": "XD3",
        "start_terminal": terminal,
        "start": {"device": location, "terminal": terminal},
        "end_terminal": "999",
    }


def scanned(terminal: str, answer: str | None, location: str = "+10F01") -> dict[str, Any]:
    return {
        "connection_id": "local-" + terminal,
        "start": {"device": "-XD3", "location": location, "terminal": terminal},
        "end": {"terminal": answer} if answer else None,
        "is_cross_page": "same_page" if answer else "cross_page",
        "references": [] if answer else [{"target_function": "006.C", "target_drawing_page": 1}],
    }


def test_same_page_matches_device_and_location_without_changing_source() -> None:
    original = stored("XD3:260")
    inputs = [scanned("XD3:251", "2"), scanned("XD3:260", "1")]
    snapshot = deepcopy(inputs)
    result = _replace_scoped([original], inputs, ["XD3:260"], ["end_terminal"])
    assert result[0]["end_terminal"] == "1"
    assert result[0]["start"] == original["start"]
    assert original["end_terminal"] == "999"
    assert inputs == snapshot


def test_cross_page_singleton_matches_and_preserves_fresh_reference() -> None:
    result = _replace_scoped(
        [stored("XD3:113", "+01F11.3")],
        [scanned("XD3:113", None, "+01F11.3")],
        ["XD3:113"],
        ["end_terminal"],
    )
    assert result[0]["connection_id"] == "XD3:113"
    assert result[0]["is_cross_page"] == "cross_page"
    assert result[0]["references"][0]["target_function"] == "006.C"


@pytest.mark.parametrize("field,value", [("location", "+OTHER"), ("device", "-XD4")])
def test_same_terminal_at_different_source_is_rejected(field: str, value: str) -> None:
    item = scanned("XD3:260", "1")
    item["start"][field] = value
    item["connection_id"] = "XD3:260"  # Model-supplied DB IDs do not bypass source checks.
    with pytest.raises(AgentServiceError):
        _replace_scoped([stored("XD3:260")], [item], ["XD3:260"], ["end_terminal"])


def test_missing_target_is_not_silently_discarded() -> None:
    with pytest.raises(AgentServiceError, match="未找到"):
        _replace_scoped([stored("XD3:260")], [scanned("XD3:251", "2")], ["XD3:260"])


def test_empty_scan_is_rejected() -> None:
    with pytest.raises(AgentServiceError):
        _replace_scoped([stored("XD3:260")], [], ["XD3:260"])


def test_ambiguous_source_and_duplicate_outputs_are_rejected() -> None:
    first = stored("XD3:260")
    second = {**first, "connection_id": "other-id"}
    with pytest.raises(AgentServiceError, match="多个"):
        _replace_scoped([first, second], [scanned("XD3:260", "1")], ["XD3:260", "other-id"])
    with pytest.raises(AgentServiceError, match="重复"):
        _replace_scoped([first], [scanned("XD3:260", "1"), scanned("XD3:260", "2")], ["XD3:260"])


def test_target_not_first_and_unrelated_rows_remain_unchanged() -> None:
    unrelated = stored("XD3:251")
    target = stored("XD3:260")
    result = _replace_scoped([unrelated, target], [scanned("XD3:260", "1")], ["XD3:260"])
    assert result[0] == unrelated
    assert result[1]["end_terminal"] == "1"


def test_qualified_and_separate_board_terminal_forms_match() -> None:
    item = scanned("260", "1")
    item["start"].update(device="XD3", terminal_board="-XD3")
    result = _replace_scoped([stored("XD3:260")], [item], ["XD3:260"], ["end_terminal"])
    assert result[0]["end_terminal"] == "1"


def test_missing_source_cannot_be_guessed_from_singleton() -> None:
    with pytest.raises(AgentServiceError):
        _replace_scoped([stored("XD3:260")], [{"end": {"terminal": "1"}}], ["XD3:260"])


def test_known_location_cannot_be_omitted_in_reextract() -> None:
    item = scanned("XD3:260", "1")
    del item["start"]["location"]
    with pytest.raises(AgentServiceError):
        _replace_scoped([stored("XD3:260")], [item], ["XD3:260"])


def test_conflicting_board_and_qualified_terminal_are_rejected() -> None:
    item = scanned("XD3:260", "1")
    item["start"]["terminal_board"] = "XD4"
    with pytest.raises(AgentServiceError):
        _replace_scoped([stored("XD3:260")], [item], ["XD3:260"])


def test_numeric_zero_terminal_is_preserved_for_identity() -> None:
    original = stored("XD3:0")
    item = scanned("0", "1")
    item["start"].update(terminal=0, terminal_board="XD3")
    result = _replace_scoped([original], [item], ["XD3:0"], ["end_terminal"])
    assert result[0]["end_terminal"] == "1"
