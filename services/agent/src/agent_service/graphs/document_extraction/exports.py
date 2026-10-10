from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_service.application.document_extraction.runtime import (
    GraphRuntime,
)
from agent_service.domain.models.wiring import (
    WireRecord,
)
from agent_service.graphs.document_extraction.helpers import (
    _attach_drawing_page,
)
from agent_service.graphs.document_extraction.state import (
    GraphState,
)
from agent_service.infrastructure.document.checkpoint import (
    _diagnostics_dir,
)
from agent_service.infrastructure.document.excel import (
    table_to_xlsx_bytes,
)

TABLE_HEADERS = [
    "页码",
    "原理号",
    "电压等级",
    "起点代号",
    "起点描述",
    "起点端子",
    "终点代号",
    "终点描述",
    "终点端子",
    "电流",
    "备注",
]


def _assemble_table_node(state: GraphState, runtime: GraphRuntime) -> dict[str, Any]:
    """Build page-ordered frontend JSON and XLSX table outputs."""

    normalized: dict[str, list[WireRecord]] = {}
    rows_by_unit: dict[str, list[list[Any]]] = {}
    ordered_rows: list[tuple[tuple[str, int, int], int, list[Any]]] = []
    row_sequence = 0
    for unit_id, raw_records in state.get("wiring_records", {}).items():
        records: list[WireRecord] = []
        for raw_record in raw_records:
            record = (
                raw_record if isinstance(raw_record, WireRecord) else WireRecord.model_validate(raw_record)
            )
            _attach_drawing_page(record, state.get("drawing_index", {}))
            record = runtime.policy.normalize_record(record, runtime.settings.terminal_strip_mapping)
            runtime.validation_warnings.extend(
                runtime.policy.validate_record(record, runtime.settings.terminal_strip_mapping)
            )
            records.append(record)
        normalized[unit_id] = records
        rows = [_record_to_table_row(record) for record in records]
        rows_by_unit[unit_id] = rows
        for record, row in zip(records, rows, strict=True):
            ordered_rows.append((_table_record_page_sort_key(record), row_sequence, row))
            row_sequence += 1

    all_rows = [row for _, _, row in sorted(ordered_rows, key=lambda item: (item[0], item[1]))]

    output_root = Path(state["output_path"])
    if runtime.output_mode == "library" or output_root.is_dir():
        output_root.mkdir(parents=True, exist_ok=True)
        table_payload = {"headers": TABLE_HEADERS, "rows": all_rows}
        (output_root / "table.json").write_text(
            json.dumps(table_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_root / "table.xlsx").write_bytes(table_to_xlsx_bytes(TABLE_HEADERS, all_rows))
        groups_root = output_root / "groups"
        groups_root.mkdir(parents=True, exist_ok=True)
        for unit_id, records in normalized.items():
            group_dir = groups_root / unit_id
            group_dir.mkdir(parents=True, exist_ok=True)
            (group_dir / "records.json").write_text(
                json.dumps(
                    [record.model_dump(mode="json", exclude_none=False) for record in records],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (group_dir / "table.json").write_text(
                json.dumps(
                    {"headers": TABLE_HEADERS, "rows": rows_by_unit[unit_id]},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

    _write_agent_diagnostics(state, runtime)
    runtime.log(
        f"assemble_table: units={len(normalized)}, records={sum(len(items) for items in normalized.values())}"
    )
    return {
        "wiring_records": normalized,
        "table_headers": TABLE_HEADERS,
        "table_rows_by_unit": rows_by_unit,
    }


def _record_to_table_row(record: WireRecord) -> list[Any]:
    """Map one concrete connection to the exact 11-column frontend table."""
    drawing_page = _table_page_label(record)
    start_terminal = _table_terminal(record.start_device, record.start_terminal)
    end_terminal = _table_terminal(record.end_device, record.end_terminal)
    remark = record.remark or record.source_note
    return [
        drawing_page,
        record.line_number or record.wire_number,
        None,
        record.start_location or record.start_device,
        record.start_name or record.start_part,
        start_terminal,
        record.end_location or record.end_device,
        record.end_name or record.end_part,
        end_terminal,
        record.current,
        remark,
    ]


def _table_record_page_sort_key(record: WireRecord) -> tuple[str, int, int]:
    function = str(record.drawing_function or "~").strip().upper()
    drawing_page = int(record.drawing_page_number) if record.drawing_page_number is not None else 10**9
    source_page = min((int(value) for value in record.source_pages), default=10**9)
    return function, drawing_page, source_page


def _table_page_label(record: WireRecord) -> str | None:
    if record.drawing_function and record.drawing_page_number is not None:
        function = str(record.drawing_function).replace(".", "")
        return f"{function}{int(record.drawing_page_number):02d}"
    if record.drawing_page:
        return str(record.drawing_page).replace("/", "")
    return None


def _table_terminal(device: str | None, terminal: Any) -> Any:
    if terminal in (None, ""):
        return None
    value = str(terminal).strip()
    if value in {"*", "PE"} or ":" in value:
        return value
    return f"{device.lstrip('-')}:{value}" if device else value


def _write_agent_diagnostics(
    state: GraphState,
    runtime: GraphRuntime,
) -> None:

    output_path = Path(state["output_path"])
    diagnostics_dir = _diagnostics_dir(output_path, runtime.output_mode)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (diagnostics_dir / "segments.json").write_text(
        json.dumps(state["segments"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (diagnostics_dir / "drawing_index.json").write_text(
        json.dumps(state.get("drawing_index", {}), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (diagnostics_dir / "errors.json").write_text(
        json.dumps(runtime.extraction_errors or {}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (diagnostics_dir / "validation-warnings.json").write_text(
        json.dumps(runtime.validation_warnings or [], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (diagnostics_dir / "page-scan-results.json").write_text(
        json.dumps(state.get("page_scan_results", {}), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (diagnostics_dir / "wire-units.json").write_text(
        json.dumps(state.get("wire_units", {}), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (diagnostics_dir / "connection-records.json").write_text(
        json.dumps(state.get("connection_records", []), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (diagnostics_dir / "cross-page-tasks.json").write_text(
        json.dumps(state.get("cross_page_tasks", []), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (diagnostics_dir / "cross-page-results.json").write_text(
        json.dumps(state.get("cross_page_results", {}), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    stage2_table_path = diagnostics_dir / "stage2-table.json"
    if not stage2_table_path.is_file():
        stage2_table_path.write_text(
            json.dumps(
                {
                    "headers": state.get("table_headers", TABLE_HEADERS),
                    "rows_by_unit": state.get("table_rows_by_unit", {}),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    (diagnostics_dir / "plant-function-groups.json").write_text(
        json.dumps(state.get("plant_function_groups", {}), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (diagnostics_dir / "table.json").write_text(
        json.dumps(
            {
                "headers": state.get("table_headers", TABLE_HEADERS),
                "rows_by_unit": state.get("table_rows_by_unit", {}),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
