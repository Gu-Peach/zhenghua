"""Main-table compatibility across Profiles; no model or database execution."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest

from src.profiles import ProfileRegistry

# isort: split
from src.agent.extraction_agent.domain.models.wiring import WireRecord
from src.agent.extraction_agent.domain.table_output import TABLE_HEADERS, table_row
from src.agent.extraction_agent.graphs.document_extraction.exports import _record_to_table_row
from src.agent.extraction_agent.infrastructure.document.excel import records_to_xlsx_bytes


@pytest.mark.parametrize("function,page", [("002.C", 1), ("LV11", 205), ("GCR.1", 5)])
def test_every_profile_uses_the_same_main_columns_and_cell_semantics(function: str, page: int) -> None:
    start = {"x": 0.2, "y": 0.5, "pdf_page_number": 1}
    end = {"x": 0.3, "y": 0.4, "pdf_page_number": 2}
    record = WireRecord(
        drawing_function=function,
        drawing_page_number=page,
        line_number="actual-line",
        start_device="actual-source",
        start_location="source-location",
        start_terminal="X1:4",
        end_device="actual-target",
        end_location="target-location",
        end_terminal="2",
        current=0,
        color="must-not-fill-color-column",
        source_note="diagnostic text",
        start_terminal_coordinates=start,
        end_terminal_coordinates=end,
    )
    expected = table_row(record.model_dump(mode="json"))
    assert len(expected) == len(TABLE_HEADERS) == 14
    assert TABLE_HEADERS[3] == "起点元件" and TABLE_HEADERS[10:] == [
        "色标",
        "备注",
        "起点端子坐标",
        "终点端子坐标",
    ]
    assert expected[3] == "actual-source" and expected[6] == "actual-target"
    assert expected[5] == "X1:4" and expected[8] == "2"
    assert expected[9] == 0 and expected[10] is None and expected[11] is None
    assert json.loads(expected[12]) == start and json.loads(expected[13]) == end
    assert _record_to_table_row(record) == expected
    workbook = openpyxl.load_workbook(BytesIO(records_to_xlsx_bytes([record])), data_only=True)
    assert list(workbook.worksheets[0].values) == [tuple(TABLE_HEADERS), tuple(expected)]


def test_unknown_coordinates_stay_empty_and_do_not_use_page_or_terminal_numbers() -> None:
    row = table_row({"drawing_function": "LV21", "drawing_page_number": 281, "start_terminal": "X1:4"})
    assert row[12:] == [None, None]


def test_all_three_local_profiles_remain_bindable() -> None:
    root = Path(__file__).resolve().parents[4]
    registry = ProfileRegistry(
        profile_root=root / "services/agent/src/agent/extraction_agent/profiles",
        workspace_root=root,
        allow_legacy_references=True,
    )
    registry.load_all()
    for name in ("zh", "abb", "zh_gantry_reel"):
        assert registry.resolve(name, allow_experimental=True).manifest.key == name
