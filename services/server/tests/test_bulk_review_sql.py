"""Bulk confirmation in an opt-in disposable PostgreSQL, never the business DB."""

from __future__ import annotations

import json
import os

import pytest
from test_explain_edits_sql import (  # noqa: F401
    OTHER,
    OWNER,
    PROJECT,
    ROOT,
    ROW,
    database,
    literal,
)
from test_profile_publication_sql import isolated_cluster, sql  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("CONNECTION_REVIEW_SQL_TEST") != "1", reason="isolated SQL opt-in"
)
MIGRATION = ROOT / "supabase/migrations/20261020020000_bulk_connection_review.sql"


def stamp(db: str) -> str:
    return sql(
        db, f"select updated_at from extraction_projects where id='{PROJECT}';"
    ).strip()


def bulk(
    db: str,
    *,
    key: str = "bulk-1",
    scope: dict | None = None,
    expected: str | None = None,
    actor: str = OWNER,
    batch: str = "batch-a",
    confirmed: bool = True,
    role: str = "service_role",
) -> dict:
    value = {
        "project_id": PROJECT,
        "actor": actor,
        "key": key,
        "body": {
            "batch_id": batch,
            "expected_updated_at": expected or stamp(db),
            "confirmed": confirmed,
        },
        "scope": {
            "workspace_code": None,
            "pdf_page_number": None,
            "search": "",
            **(scope or {}),
        },
    }
    result = sql(
        db,
        f"set request.jwt.claim.role='{role}'; select review_extraction_scope({literal(value)});",
    )
    return json.loads(result.strip().splitlines()[-1])


@pytest.mark.parametrize("empty", [True, False])
def test_bulk_migration_preserves_empty_or_legacy_data(database, empty):  # noqa: F811
    if empty:
        sql(
            database,
            "delete from extraction_connection_rows; delete from extraction_projects; delete from extraction_profiles;",
        )
    before = sql(
        database,
        "select coalesce(jsonb_agg(to_jsonb(r) order by id),'[]') from extraction_connection_rows r;",
    )
    sql(database, MIGRATION.read_text(encoding="utf-8"))
    assert (
        sql(
            database,
            "select coalesce(jsonb_agg(to_jsonb(r) order by id),'[]') from extraction_connection_rows r;",
        )
        == before
    )
    assert (
        sql(
            database,
            "select not has_function_privilege('authenticated','review_extraction_scope(jsonb)','execute') and has_function_privilege('service_role','review_extraction_scope(jsonb)','execute');",
        ).strip()
        == "t"
    )


def test_bulk_reviews_all_pages_of_selected_scope_and_preserves_other_rows(database):  # noqa: F811
    sql(database, MIGRATION.read_text(encoding="utf-8"))
    sql(
        database,
        f"""update extraction_connection_rows set needs_review=true where id='{ROW}';
      insert into extraction_connection_rows(id,project_id,batch_id,page_item_id,row_order,workspace_code,source_drawing_page,source_pdf_page_number,start_terminal,end_terminal,needs_review)
        select gen_random_uuid(),'{PROJECT}','batch-a','bulk-'||n,n+10,'001.A','001A01',1,'XA:'||n,'XD:'||n,true from generate_series(1,104) n;
      insert into extraction_connection_rows(id,project_id,batch_id,page_item_id,row_order,workspace_code,source_drawing_page,source_pdf_page_number,start_terminal,needs_review)
        values(gen_random_uuid(),'{PROJECT}','batch-a','other-page',0,'002.B','002B01',2,'XA:outside',true),
        (gen_random_uuid(),'{PROJECT}','old-batch','old-row',0,'001.A','001A01',1,'XA:old',true);""",
    )
    expected = stamp(database)
    receipt = bulk(
        database,
        scope={"workspace_code": "001.A", "pdf_page_number": 1},
        expected=expected,
    )
    assert receipt["reviewed_count"] == 105
    assert (
        bulk(
            database,
            scope={"workspace_code": "001.A", "pdf_page_number": 1},
            expected=expected,
        )["idempotent"]
        is True
    )
    assert (
        sql(
            database,
            f"select count(*) from extraction_connection_rows where project_id='{PROJECT}' and needs_review;",
        ).strip()
        == "2"
    )
    assert (
        sql(
            database,
            f"select count(*) from extraction_connection_rows where project_id='{PROJECT}' and batch_id='batch-a' and source_pdf_page_number=1 and record_version=2;",
        ).strip()
        == "104"
    )
    original = json.loads(
        sql(
            database,
            f"select to_jsonb(r) from extraction_connection_rows r where id='{ROW}';",
        ).strip()
    )
    assert original["start_terminal"] == "XA:1" and original["end_terminal"] == "XD3:11"
    audit = json.loads(
        sql(
            database,
            f"select drawing_index->'management'->'audit' from extraction_projects where id='{PROJECT}';",
        ).strip()
    )
    assert len(audit) == 105 and all(
        item["before"]["needs_review"] and not item["after"]["needs_review"]
        for item in audit
    )
    # Already confirmed row-two is not touched, and the old batch/outside page remain pending.
    assert (
        sql(
            database,
            "select record_version from extraction_connection_rows where page_item_id='row-two';",
        ).strip()
        == "1"
    )


def test_bulk_conflicts_are_atomic_and_search_matches_table_fields(database):  # noqa: F811
    sql(database, MIGRATION.read_text(encoding="utf-8"))
    sql(database, "update extraction_connection_rows set needs_review=true;")
    expected = stamp(database)
    for options, message in [
        ({"actor": OTHER}, "owner required"),
        ({"role": "authenticated"}, "Internal review"),
        ({"batch": "wrong"}, "version changed"),
        ({"expected": "2000-01-01T00:00:00Z"}, "version changed"),
        ({"confirmed": False}, "Invalid bulk"),
        ({"scope": {"pdf_page_number": 999}}, "not in this project"),
    ]:
        with pytest.raises(AssertionError, match=message):
            bulk(database, **options)
    assert (
        sql(
            database,
            "select count(*) from extraction_connection_rows where needs_review;",
        ).strip()
        == "2"
    )
    receipt = bulk(
        database, key="search", scope={"search": "Start2"}, expected=expected
    )
    assert receipt["reviewed_count"] == 1
    assert (
        sql(
            database,
            f"select needs_review from extraction_connection_rows where id='{ROW}';",
        ).strip()
        == "t"
    )
    with pytest.raises(AssertionError, match="version changed"):
        bulk(database, key="stale", expected=expected)
    zero = bulk(database, key="none", scope={"search": "not-present"})
    assert zero["reviewed_count"] == 0
    sql(
        database,
        f"update extraction_projects set status='processing' where id='{PROJECT}';",
    )
    with pytest.raises(AssertionError, match="read only"):
        bulk(database, key="busy")
