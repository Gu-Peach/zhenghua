"""ABB-only model readings and deterministic principle numbers; public rows stay unchanged."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field

from src.agent.extraction_agent.domain.models.extraction_stages import (
    DrawingEndpoint,
    PageScanData,
    ScannedConnection,
)
from src.agent.extraction_agent.domain.models.review import VisualUncertainty
from src.agent.extraction_agent.infrastructure.zh_vlm_stages import _filter_schema
from src.domain.models.common import StrictModel

MarkerNumber = Annotated[str, Field(pattern=r"^[0-9]+$")]


class AbbScannedConnection(ScannedConnection):
    marker_numbers_unreadable: bool = Field(default=False, description="可见标记数字但两侧均无法辨认时为true")
    start_marker_number: MarkerNumber | None = Field(
        description="本段起点侧小圆点旁数字，无编号或不可读为null",
    )
    end_marker_number: MarkerNumber | None = Field(
        description="本段终点侧小圆点旁数字，无编号或不可读为null",
    )
    endpoint_role: Literal["source", "receiver", "unknown"] = Field(description="本页发出、接收或方向不明")
    direction_basis: str | None = Field(description="当前段可见的方向依据，不按端子编号决定")


class AbbScanUnit(StrictModel):
    """Private VLM envelope; business metadata receives public model defaults after projection."""

    unit_id: str = Field(min_length=1)
    wire_number: str | None = None
    project_no: str | None = None
    drawing_prefix: str | None = None
    connections: list[AbbScannedConnection] = Field(description="当前单元的实际连接，无连接为显式空数组")


class AbbScanResponse(StrictModel):
    pdf_page_number: int | None = Field(default=None, ge=1)
    drawing_function: str | None = None
    drawing_page_number: int | None = Field(default=None, ge=1)
    drawing_object_location: str | None = None
    blank: bool = False
    units: list[AbbScanUnit] = Field(description="整页适用放线单元，无连接时显式返回空数组")
    uncertainties: list[VisualUncertainty] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AbbMarkerReading(StrictModel):
    local_connection_id: str = Field(min_length=1)
    start_marker_number: MarkerNumber | None
    end_marker_number: MarkerNumber | None
    marker_numbers_unreadable: bool = False


class AbbExampleReadings(StrictModel):
    version: Literal[1] = 1
    connections: list[AbbMarkerReading]


class AbbScanEvidenceContract(StrictModel):
    version: Literal[1]
    response_contract: Literal["abb_two_side_marker_readings_v1"]


def load_abb_readings(folder: Path, relative: str) -> AbbExampleReadings:
    """Keep package-owned evidence references inside the configured example directory."""
    path = (folder / relative).resolve()
    if not relative or not path.is_relative_to(folder.resolve()):
        raise ValueError("ABB marker evidence must be inside the example directory")
    return AbbExampleReadings.model_validate_json(path.read_text(encoding="utf-8"))


def _full_terminal(endpoint: DrawingEndpoint | None) -> str | None:
    if endpoint is None or endpoint.terminal in (None, ""):
        return None
    terminal = str(endpoint.terminal).strip().removeprefix("-")
    if ":" in terminal:
        return terminal
    # A bare bus potential is evidence of connectivity, not a device/pin identity.
    if terminal.upper() in {"L1", "L2", "L3", "N", "PE"}:
        return None
    board = endpoint.terminal_board or endpoint.device
    return f"{board.strip().removeprefix('-')}:{terminal}" if board else None


def finalize_abb_scan(
    response: AbbScanResponse,
    *,
    source_sheet: int | None,
) -> PageScanData:
    """Assemble numbers from observed digits, never from a model-composed number or PDF page."""
    payload = response.model_dump(mode="python")
    sheet = source_sheet or response.drawing_page_number
    payload["drawing_page_number"] = sheet
    for raw_unit, unit in zip(response.units, payload["units"], strict=True):
        for raw, connection in zip(raw_unit.connections, unit["connections"], strict=True):
            selected = raw.start_marker_number or raw.end_marker_number
            rule = "start_marker" if raw.start_marker_number else "end_marker"
            if selected is None and not raw.marker_numbers_unreadable:
                selected = _full_terminal(raw.start) or _full_terminal(raw.end)
                rule = "actual_terminal"
            connection["line_number"] = f"{selected}{sheet}" if selected and sheet else None
            evidence = {
                "start": raw.start_marker_number,
                "end": raw.end_marker_number,
                "selected": selected,
                "sheet": sheet,
                "rule": rule,
                "unreadable": raw.marker_numbers_unreadable,
            }
            connection["source_note"] = "; ".join(
                filter(
                    None,
                    [
                        raw.source_note,
                        "ABB marker evidence: " + json.dumps(evidence, ensure_ascii=False),
                    ],
                )
            )
            if sheet is None:
                connection["uncertainties"].append(
                    {
                        "field": "page",
                        "detail": "来源Sheet无法确认，原理号留空",
                    }
                )
            elif selected is None:
                connection["uncertainties"].append(
                    {
                        "field": "connection",
                        "detail": (
                            "标记数字可见但无法辨认，原理号留空"
                            if raw.marker_numbers_unreadable
                            else "本段无可确认标记编号或完整实际端子，原理号留空"
                        ),
                    }
                )
    return PageScanData.model_validate(_filter_schema(PageScanData, payload))


def raw_abb_scan_example(expected: dict[str, Any], evidence: AbbExampleReadings) -> dict[str, Any]:
    """Render the final fixture as the same raw-reading contract used by live requests."""
    readings = {item.local_connection_id: item for item in evidence.connections}
    if len(readings) != len(evidence.connections):
        raise ValueError("ABB example contains duplicate marker reading identities")
    payload = deepcopy(expected)
    seen: set[str] = set()
    for unit in payload.get("units", []):
        for connection in unit.get("connections", []):
            identity = connection.get("local_connection_id")
            if identity not in readings or identity in seen:
                raise ValueError("ABB example has missing or duplicate connection marker evidence")
            seen.add(identity)
            reading = readings[identity]
            connection.update(
                start_marker_number=reading.start_marker_number,
                end_marker_number=reading.end_marker_number,
                line_number=None,
            )
            if reading.marker_numbers_unreadable:
                connection["marker_numbers_unreadable"] = True
    if seen != set(readings):
        raise ValueError("ABB example has marker evidence for an unknown connection")
    filtered = _filter_schema(AbbScanResponse, payload)
    AbbScanResponse.model_validate(filtered)
    return dict(filtered)
