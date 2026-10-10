from backend.app.schemas.wire import WireRecord
from backend.app.services.cross_page_merge import merge_cross_page_records


def test_missing_endpoint_is_kept_and_marked_for_review() -> None:
    records = [WireRecord(line_number="003G0121", start_device="-XD3", start_terminal="3", source_pages=[60])]
    merged = merge_cross_page_records(records)
    assert len(merged) == 1
    assert merged[0].external_source_required is True
    assert "终点未在当前批次确认" in (merged[0].remark or "")


def test_complete_record_is_not_joined_by_wire_number_only() -> None:
    records = [
        WireRecord(line_number="same", start_device="-XD3", start_terminal="3", end_device="-A", end_terminal="1", source_pages=[60]),
        WireRecord(line_number="same", start_device="-XD3", start_terminal="3", end_device="-B", end_terminal="1", source_pages=[403]),
    ]
    merged = merge_cross_page_records(records)
    assert len(merged) == 2
    assert all(record.external_source_required is False for record in merged)
