"""Opt-in disposable PostgreSQL: switching only new jobs to the selected published rule."""

import json
import os

import pytest
from test_explain_edits_sql import (  # noqa: F401
    OTHER,
    OWNER,
    PROJECT,
    ROOT,
    database,
    literal,
)
from test_explain_rescan_sql import enqueue, rescan_db, rpc  # noqa: F401
from test_profile_publication_sql import isolated_cluster, sql  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("EXPLAIN_RESCAN_SQL_TEST") != "1", reason="isolated SQL opt-in"
)
MIGRATION = ROOT / "supabase/migrations/20261019030000_rescan_project_profile.sql"
NEW = "00000000-0000-0000-0000-000000000021"
OLD = "00000000-0000-0000-0000-000000000020"


@pytest.fixture
def upgraded(rescan_db):  # noqa: F811 -- pytest injects imported fixture
    db = rescan_db
    # Simulate historical rows and an existing queued task before applying the new migration.
    sql(
        db,
        f"""update extraction_connection_rows set evidence=evidence||jsonb_build_object('profile',
        jsonb_build_object('key','test','version','1.0.0','checksum','sha256:'||repeat('0',64)));
        insert into extraction_profiles(id,profile_key,profile_version,checksum,resource_ref,display_name,created_by)
        values('{NEW}','zh','2.3.0','sha256:'||repeat('2',64),'storage://project-assets/profiles/{OWNER}/zh/2.3.0/'||repeat('2',64)||'.zip','ZH','{OWNER}');""",
    )
    old = enqueue(db)
    sql(db, MIGRATION.read_text(encoding="utf-8"))
    sql(db, f"update extraction_projects set profile_id='{NEW}' where id='{PROJECT}';")
    return db, old


def enable(db):
    sql(
        db,
        f"update extraction_projects set drawing_index=drawing_index||'{{\"rescan_profile_source\":\"project_reference\"}}'::jsonb where id='{PROJECT}';",
    )


def test_opt_in_uses_new_package_and_old_job_stays_frozen(upgraded):
    db, old = upgraded
    enable(db)
    job = enqueue(db)
    assert job["profile"]["key"] == "zh" and job["profile"]["version"] == "2.3.0"
    snapshot = json.loads(
        sql(
            db,
            f"select project_snapshot from connection_rescan_runs where id='{job['id']}';",
        ).strip()
    )
    assert (
        snapshot["profile_source"] == "project_reference"
        and snapshot["profile_id"] == NEW
    )
    assert snapshot["profile_ref"].endswith("/zh/2.3.0/" + "2" * 64 + ".zip")
    assert enqueue(db, id=old["id"]) == old
    assert (
        json.loads(
            sql(
                db,
                f"select profile from connection_rescan_runs where id='{old['id']}';",
            ).strip()
        )["key"]
        == "test"
    )
    # Changing the project later must not rebind this existing job, and its package remains pinned.
    sql(db, f"update extraction_projects set profile_id='{OLD}' where id='{PROJECT}';")
    assert enqueue(db, id=job["id"])["profile"]["version"] == "2.3.0"
    assert sql(db, f"select profile_version_in_use('{NEW}');").strip() == "t"


def test_without_opt_in_preserves_historical_selection(upgraded):
    db, _ = upgraded
    assert enqueue(db)["profile"]["key"] == "test"


def test_opt_in_can_rescan_rows_from_different_historical_versions(upgraded):
    db, _ = upgraded
    sql(db, """update extraction_connection_rows set evidence=evidence||
        '{"profile":{"key":"retired","version":"0.1.0","checksum":"old-unavailable"}}'::jsonb
        where row_order=1;""")
    enable(db)
    assert enqueue(db)["profile"]["version"] == "2.3.0"


def test_opt_in_rejects_local_package_and_foreign_owner(upgraded):
    db, _ = upgraded
    enable(db)
    with pytest.raises(AssertionError, match="Project owner required"):
        enqueue(db, actor=OTHER)
    sql(db, f"update extraction_projects set profile_id='{OLD}' where id='{PROJECT}';")
    with pytest.raises(AssertionError, match="requires published package"):
        enqueue(db)


def test_migration_applies_to_empty_business_tables(rescan_db):  # noqa: F811
    sql(rescan_db, f"delete from extraction_projects where id='{PROJECT}';")
    sql(rescan_db, MIGRATION.read_text(encoding="utf-8"))
    assert sql(rescan_db, "select count(*) from connection_rescan_runs;").strip() == "0"
