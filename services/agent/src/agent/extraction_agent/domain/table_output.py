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


def table_row(record: Mapping[str, Any]) -> list[Any]:
    """Render normalized facts; never synthesize terminals, coordinates or remarks."""
    function, number = record.get("drawing_function"), record.get("drawing_page_number")
    page = f"{str(function).replace('.', '')}{int(number):02d}" if function and number is not None else None
    return [
        page,
        record.get("line_number"),
        record.get("terminal_strip"),
        record.get("start_device") or record.get("start_location"),
        record.get("start_name"),
        record.get("start_terminal"),
        record.get("end_device") or record.get("end_location"),
        record.get("end_name"),
        record.get("end_terminal"),
        record.get("current"),
        None,
        record.get("remark"),
        _coordinate_cell(record.get("start_terminal_coordinates")),
        _coordinate_cell(record.get("end_terminal_coordinates")),
    ]


def _coordinate_cell(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    return json.dumps(value, ensure_ascii=False)
