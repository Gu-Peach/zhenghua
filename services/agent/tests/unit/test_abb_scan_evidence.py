"""ABB model evidence must not alter other Profiles or the public output contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.agent.extraction_agent.domain.table_output import TABLE_HEADERS
from src.agent.extraction_agent.infrastructure.abb_scan_evidence import (
    AbbExampleReadings,
    AbbScanResponse,
    finalize_abb_scan,
    raw_abb_scan_example,
)
from src.agent.extraction_agent.infrastructure.abb_vlm_stages import AbbVlmExtractionStageAdapter
from src.config import AgentSettings
from src.harness.model_gateway import FakeModelGateway
from src.profiles.registry import ProfileRegistry

BASE = Path(__file__).resolve().parents[2] / "src/agent/extraction_agent/prompts/abb/examples_wiring/lv11"


def _raw(start: str | None, end: str | None, *, sheet: int | None = 205) -> AbbScanResponse:
    return AbbScanResponse.model_validate(
        {
            "pdf_page_number": 9,
            "drawing_page_number": sheet,
            "units": [
                {
                    "unit_id": "u",
                    "connections": [
                        {
                            "endpoint_role": "source",
                            "direction_basis": "visible bus feed",
                            "start_marker_number": start,
                            "end_marker_number": end,
                            "line_number": "IGNORE_MODEL_COMPOSED_VALUE",
                            "start": {"terminal": "L1"},
                            "end": {"device": "-Q3", "terminal": "Q3:1"},
                        }
                    ],
                }
            ],
        }
    )


@pytest.mark.parametrize(
    "start,end,expected",
    [
        ("224", "224", "224205"),
        ("007", None, "007205"),
        (None, "225", "225205"),
        ("122", "121", "122205"),
        (None, None, "Q3:1205"),
    ],
)
def test_principle_uses_raw_digits_or_full_terminal_not_model_number(
    start: str | None,
    end: str | None,
    expected: str,
) -> None:
    result = finalize_abb_scan(_raw(start, end), source_sheet=None)
    connection = result.units[0].connections[0]
    assert connection.line_number == expected
    assert connection.source_note and json.dumps(start) in connection.source_note
    assert "start_marker_number" not in connection.model_dump()
    assert len(TABLE_HEADERS) == 14


def test_unknown_sheet_does_not_use_physical_page_or_drop_connection() -> None:
    connection = finalize_abb_scan(_raw("224", None, sheet=None), source_sheet=None).units[0].connections[0]
    assert connection.line_number is None
    assert any(item.field == "page" for item in connection.uncertainties)


def test_reference_address_is_not_a_marker_reading() -> None:
    with pytest.raises(ValidationError):
        _raw("205.2D", None)


def test_unreadable_marker_does_not_silently_use_terminal_fallback() -> None:
    raw = _raw(None, None)
    raw.units[0].connections[0].marker_numbers_unreadable = True
    connection = finalize_abb_scan(raw, source_sheet=None).units[0].connections[0]
    assert connection.line_number is None
    assert connection.uncertainties


def test_old_pinned_profiles_without_opt_in_keep_the_public_scan_contract() -> None:
    repo = Path(__file__).resolve().parents[4]
    registry = ProfileRegistry(
        profile_root=repo / "services/agent/src/agent/extraction_agent/profiles",
        workspace_root=repo,
        allow_legacy_references=True,
    )
    registry.load_all()
    binding = registry.bind("abb")
    adapter = AbbVlmExtractionStageAdapter(AgentSettings(default_model="fake"), FakeModelGateway([]))
    assert adapter._uses_marker_readings(binding)
    old = binding.model_copy(
        update={
            "resolved_resources": {
                k: v
                for k, v in binding.resolved_resources.items()
                if k != "scan_evidence_rules"
            },
        }
    )
    assert not adapter._uses_marker_readings(old)


def test_full_page_fixture_roundtrip_retains_field_level_results() -> None:
    expected = json.loads((BASE / "stage2/lv11_205.expected.json").read_text(encoding="utf-8"))
    evidence = AbbExampleReadings.model_validate_json(
        (BASE / "stage2/lv11_205.markers.json").read_text(encoding="utf-8")
    )
    raw = AbbScanResponse.model_validate(raw_abb_scan_example(expected, evidence))
    result = finalize_abb_scan(raw, source_sheet=None)
    rows = {c.local_connection_id: c for u in result.units for c in u.connections}
    assert len(rows) == 57
    for unit in expected["units"]:
        for connection in unit["connections"]:
            actual = rows[connection["local_connection_id"]]
            assert actual.line_number == connection["line_number"]
            assert actual.current == connection.get("current")
            for side in ("start", "end"):
                endpoint = getattr(actual, side)
                assert (endpoint.model_dump(exclude_none=True) if endpoint else None) == connection.get(side)
    assert {"205-q7-input-1", "205-f50-input-1", "205-x1-q102-11"} <= set(rows)
