"""One ZH-compatible main-table contract for every drawing Profile and runner."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, TypedDict

TABLE_HEADERS = [
    "页码",
    "原理号",
    "端子排",
    "起点元件",
    "起点描述",
    "起点端子",
    "终点元件",
    "终点描述",
    "终点端子",
    "电流",
    "色标",
    "备注",
    "起点端子坐标",
    "终点端子坐标",
]


class TableStyle(TypedDict):
    font: str
    size: float
    body_height: float
    header_fill: str
    widths: list[float]


TABLE_STYLE: TableStyle = {
    "font": "宋体",
    "size": 9.0,
    "body_height": 21.6,
    "header_fill": "#C0C0C0",
    "widths": [
        8.89,
        10.44,
        8.89,
        18.11,
        22.11,
        13.33,
        15.44,
        19.44,
        13.56,
        8.89,
        8.89,
        20.78,
        42,
        42,
    ],
}


def output_fields(record: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical business projection shared by the 14-column table and publication DTO."""
    function, number = record.get("drawing_function"), record.get("drawing_page_number")
    page = f"{str(function).replace('.', '')}{int(number):02d}" if function and number is not None else None
    return {
        "source_drawing_page": page,
        "principle_number": record.get("line_number"),
        "terminal_strip": record.get("terminal_strip"),
        "start_code": record.get("start_device") or record.get("start_location"),
        "start_description": record.get("start_name"),
        "start_terminal": record.get("start_terminal"),
        "end_code": record.get("end_device") or record.get("end_location"),
        "end_description": record.get("end_name"),
        "end_terminal": record.get("end_terminal"),
        "current_value": record.get("current"),
        "color_mark": None,
        "remark": record.get("remark"),
        "start_terminal_coordinates": record.get("start_terminal_coordinates"),
        "end_terminal_coordinates": record.get("end_terminal_coordinates"),
    }


def table_row(record: Mapping[str, Any]) -> list[Any]:
    """Render normalized facts; never synthesize terminals, coordinates or remarks."""
    values = output_fields(record)
    return [
        _coordinate_cell(value) if field.endswith("_coordinates") else value
        for field, value in values.items()
    ]


def _coordinate_cell(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    return json.dumps(value, ensure_ascii=False)
