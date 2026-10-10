from __future__ import annotations

from typing import Any

from agent_service.application.document_extraction.runtime import (
    GraphRuntime,
)
from agent_service.domain.models.wiring import (
    WireConnection,
    WireRecord,
    parse_wire_unit,
)
from agent_service.graphs.document_extraction.exports import (
    _record_to_table_row,
)
from agent_service.graphs.document_extraction.helpers import (
    _connection_identity,
    _merge_connection_data,
    _unique_strings,
    _wire_record_from_connection,
)
from agent_service.graphs.document_extraction.state import (
    GraphState,
)


def _normalize_and_deduplicate_node(state: GraphState, runtime: GraphRuntime) -> dict[str, Any]:
    """Flatten logical units into one XLSX/API row per concrete connection."""

    page_by_number = {int(page["page_number"]): page for page in state.get("pages", [])}
    normalized_units: dict[str, dict[str, Any]] = {}
    records_by_unit: dict[str, list[WireRecord]] = {}
    connection_records: list[dict[str, Any]] = []
    rejected_connections = 0
    reversed_connections = 0
    for unit_id, raw_unit in (state.get("wire_units") or {}).items():
        unit = parse_wire_unit(raw_unit)
        unique_connections: list[WireConnection] = []
        seen: dict[str, WireConnection] = {}
        for raw_connection in unit.connections:
            connection = (
                raw_connection
                if isinstance(raw_connection, WireConnection)
                else WireConnection.model_validate(raw_connection)
            )
            oriented, reversed_direction = runtime.policy.orient_connection(connection)
            if oriented is None:
                rejected_connections += 1
                continue
            connection = oriented
            if reversed_direction:
                reversed_connections += 1
            connection.current = runtime.policy.validated_current(
                connection.current,
                connection.current_basis,
                connection.current_source_text,
            )
            key = _connection_identity(unit_id, connection)
            if key in seen:
                _merge_connection_data(seen[key], connection)
            else:
                seen[key] = connection
                unique_connections.append(connection)
        unit.connections = unique_connections
        if not unique_connections:
            continue
        unit.source_pages = sorted({int(page) for page in unit.source_pages})
        unit.source_drawing_pages = _unique_strings(unit.source_drawing_pages)
        if any(connection.status not in {"complete", "resolved"} for connection in unique_connections):
            unit.status = "needs_review"
        normalized_units[unit_id] = unit.model_dump(mode="json", exclude_none=False)

        records: list[WireRecord] = []
        for connection in unique_connections:
            record = _wire_record_from_connection(
                unit,
                connection,
                page_by_number=page_by_number,
                terminal_strip_mapping=runtime.settings.terminal_strip_mapping,
            )
            record = runtime.policy.normalize_record(record, runtime.settings.terminal_strip_mapping)
            runtime.validation_warnings.extend(
                runtime.policy.validate_record(record, runtime.settings.terminal_strip_mapping)
            )
            records.append(record)
            connection_records.append(record.model_dump(mode="json", exclude_none=False))
        records_by_unit[unit_id] = records

    runtime.log(
        f"terminal_filter: rejected={rejected_connections} reversed={reversed_connections} "
        f"kept={sum(len(records) for records in records_by_unit.values())}"
    )

    table_rows_by_unit = {
        unit_id: [_record_to_table_row(record) for record in records]
        for unit_id, records in records_by_unit.items()
    }
    return {
        "wire_units": normalized_units,
        "wiring_records": records_by_unit,
        "connection_records": connection_records,
        "table_rows_by_unit": table_rows_by_unit,
    }
