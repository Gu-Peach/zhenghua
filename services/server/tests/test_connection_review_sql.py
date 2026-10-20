"""Opt-in disposable PostgreSQL review transactions; never the business database."""

from __future__ import annotations

import json
import os
from uuid import uuid4

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
MIGRATION = ROOT / "supabase/migrations/20261020010000_connection_review.sql"


def review(
    db: str,
    *,
    version: int = 1,
    key: str = "review-1",
    actor: str = OWNER,
    role: str = "service_role",
) -> dict:
    value = {
        "actor": actor,
        "project_id": PROJECT,
        "connection_id": ROW,
        "key": key,
        "body": {"record_version": version, "confirmed": True},
    }
    result = sql(
        db,
        f"set request.jwt.claim.role='{role}'; select review_extraction_connection({literal(value)});",
    )
    return json.loads(result.strip().splitlines()[-1])


def test_review_migration_on_empty_database() -> None:
    name = "profile_publish_test_" + uuid4().hex
    sql("postgres", f'create database "{name}";')
    try:
        sql(
            name,
            "create schema auth; create table auth.users(id uuid primary key); create function auth.uid() returns uuid language sql as 'select null::uuid'; create function auth.role() returns text language sql as 'select current_setting(''request.jwt.claim.role'',true)';",
        )
        sql(
            name,
            (
                ROOT
                / "supabase/migrations/20261014000000_create_simple_extraction_business_tables.sql"
            ).read_text(encoding="utf-8"),
        )
        sql(name, MIGRATION.read_text(encoding="utf-8"))
        assert "review_extraction_connection" in sql(
            name,
            "select proname from pg_proc where proname='review_extraction_connection';",
        )
    finally:
        sql("postgres", f'drop database "{name}";')


def test_review_on_existing_rows_is_atomic_audited_and_versioned(database: str) -> None:  # noqa: F811
    sql(
        database,
        f"update extraction_connection_rows set needs_review=true where id='{ROW}';",
    )
    sql(database, MIGRATION.read_text(encoding="utf-8"))
    version = int(
        sql(
            database,
            f"select record_version from extraction_connection_rows where id='{ROW}';",
        ).strip()
    )
    with pytest.raises(AssertionError, match="owner required"):
        review(database, actor=OTHER, version=version)
    with pytest.raises(AssertionError, match="Internal review"):
        review(database, role="authenticated", version=version)
    with pytest.raises(AssertionError, match="version changed"):
        review(database, version=version + 1)
    receipt = review(database, version=version)
    assert receipt["record_version"] == version + 1
    assert receipt["action"] == "review"
    assert review(database, version=version)["idempotent"] is True
    row = json.loads(
        sql(
            database,
            f"select row_to_json(r) from extraction_connection_rows r where id='{ROW}';",
        ).strip()
    )
    assert row["needs_review"] is False
    assert row["start_terminal"] == "XA:1" and row["end_terminal"] == "XD3:11"
    assert row["evidence"]["human_review"]["actor"] == OWNER
    assert row["evidence"]["record"]["source_note"] == "Original"
    audit = json.loads(
        sql(
            database,
            f"select drawing_index->'management'->'audit' from extraction_projects where id='{PROJECT}';",
        ).strip()
    )
    assert len(audit) == 1 and audit[0]["before"]["needs_review"] is True
    with pytest.raises(AssertionError, match="Idempotency key reused"):
        review(database, version=version + 1)
    with pytest.raises(AssertionError, match="already reviewed"):
        review(database, key="other", version=version + 1)
    sql(
        database,
        f"update extraction_projects set status='processing' where id='{PROJECT}';",
    )
    with pytest.raises(AssertionError, match="read only"):
        review(database, key="busy", version=version + 1)
    sql(
        database,
        f"update extraction_projects set status='ready', drawing_index=jsonb_set(drawing_index,'{{active_batch_id}}','\"new-batch\"') where id='{PROJECT}';",
    )
    with pytest.raises(AssertionError, match="version changed"):
        review(database, key="stale", version=version + 1)
