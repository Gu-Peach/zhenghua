from __future__ import annotations

from pathlib import Path

from backend.app.services.supabase_store import _build_rows


def test_build_supabase_rows_preserves_job_folder_paths(tmp_path: Path) -> None:
    job_dir = tmp_path / "job-1"
    (job_dir / "source").mkdir(parents=True)
    (job_dir / "pages").mkdir(parents=True)
    (job_dir / "groups" / "wire-table-001" / "pages").mkdir(parents=True)
    (job_dir / "source" / "drawing.pdf").write_bytes(b"pdf")
    (job_dir / "pages" / "page_001.png").write_bytes(b"page")
    (job_dir / "groups" / "wire-table-001" / "pages" / "page_001.png").write_bytes(b"page")
    (job_dir / "groups" / "wire-table-001" / "records.json").write_text("[]", encoding="utf-8")

    rows = _build_rows(
        {
            "name": "drawing",
            "source_filename": "drawing.pdf",
            "status": "success",
            "groups": [
                {
                    "group_id": "wire-table-001",
                    "title": "线表 1",
                    "pages": [1],
                    "records": [],
                    "record_count": 0,
                    "status": "success",
                }
            ],
        },
        job_dir,
        job_dir.name,
    )

    assert rows[0]["source_pdf_path"] == "job-1/source/drawing.pdf"
    assert rows[0]["page_paths"] == ["job-1/groups/wire-table-001/pages/page_001.png"]
    assert rows[0]["all_page_paths"] == ["job-1/pages/page_001.png"]
    assert rows[0]["records_path"] == "job-1/groups/wire-table-001/records.json"
