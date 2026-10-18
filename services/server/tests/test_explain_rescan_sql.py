"""Opt-in rescan integration in a disposable PostgreSQL, never the running business DB."""

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
    os.environ.get("EXPLAIN_RESCAN_SQL_TEST") != "1", reason="isolated SQL opt-in"
)
CONVERSATION = "00000000-0000-0000-0000-000000000051"


@pytest.fixture
def rescan_db(database):  # noqa: F811 -- pytest injects the imported seed fixture
    sql(
        database,
        (ROOT / "supabase/migrations/20261018050000_explain_rescan.sql").read_text(
            encoding="utf-8"
        ),
    )
    return database


def rpc(db, name, value):
    return json.loads(
        sql(
            db,
            "set request.jwt.claim.role='service_role'; select "
            + name
            + "("
            + literal(value)
            + ");",
        )
        .strip()
        .splitlines()[-1]
    )


def enqueue(db, **changes):
    value = {
        "id": str(uuid4()),
        "actor": OWNER,
        "project_id": PROJECT,
        "conversation_id": CONVERSATION,
        "batch_id": "batch-a",
        "attachment_ids": [],
        "request": {
            "scope": {"workspace_code": "001.A"},
            "fields": "all",
            "instructions": "重扫",
        },
    }
    value.update(changes)
    return rpc(db, "enqueue_connection_rescan", value)


def claim(db):
    return json.loads(
        sql(
            db,
            "set request.jwt.claim.role='service_role'; select claim_connection_rescan('test-worker');",
        )
        .strip()
        .splitlines()[-1]
    )


def candidate():
    return {
        "changes": [
            {
                "action": "update",
                "connection_id": ROW,
                "record_version": 1,
                "source_pdf_page_number": 1,
                "source_drawing_page": "001A01",
                "workspace_code": "001.A",
                "before": {"end_terminal": "XD3:11"},
                "after": {
                    "end_terminal": "X9:2",
                    "end_terminal_coordinates": {
                        "x": 0.3,
                        "y": 0.4,
                        "pdf_page_number": 2,
                    },
                    "needs_review": False,
                },
                "evidence": {"source_note": "原图定位"},
            }
        ],
        "warnings": [],
        "unmatched_ids": [],
    }


def ready(db, request=None, payload=None):
    run = enqueue(db, **({"request": request} if request else {}))
    job = claim(db)
    result = rpc(
        db,
        "advance_connection_rescan",
        {
            "id": job["id"],
            "token": job["lease_token"],
            "stage": "ready",
            "candidate": payload or candidate(),
        },
    )
    assert result["id"] == run["id"]
    return result


def decide(db, run, accepted=True, **changes):
    return rpc(
        db,
        "decide_connection_rescan",
        {
            "id": run["id"],
            "actor": OWNER,
            "project_id": PROJECT,
            "accepted": accepted,
            "checksum": run["checksum"],
            **changes,
        },
    )


def row(db):
    return json.loads(
        sql(
            db,
            f"select to_jsonb(r) from extraction_connection_rows r where id='{ROW}';",
        ).strip()
    )


def test_rescan_preparation_and_candidate_do_not_write_until_confirmation(rescan_db):
    before = row(rescan_db)
    run = ready(rescan_db)
    assert row(rescan_db) == before
    assert (
        run["profile"]["version"] == "1.0.0"
        and "baseline" not in run
        and "lease_token" not in run
    )
    result = decide(rescan_db, run)
    saved = row(rescan_db)
    assert saved["end_terminal"] == "X9:2" and result["versions"][ROW] == 2
    for name in (
        "id",
        "source_drawing_page",
        "source_pdf_page_number",
        "workspace_code",
        "start_terminal",
        "batch_id",
    ):
        assert saved[name] == before[name]
    decide(rescan_db, run)
    assert row(rescan_db)["record_version"] == 2


def test_rescan_versions_scope_and_checksum_are_atomic(rescan_db):
    run = ready(rescan_db)
    with pytest.raises(AssertionError, match="checksum changed"):
        decide(rescan_db, run, checksum="wrong")
    sql(
        rescan_db,
        "update extraction_connection_rows set remark='Concurrent' where principle_number='P2';",
    )
    with pytest.raises(AssertionError, match="versions changed"):
        decide(rescan_db, run)
    assert row(rescan_db)["end_terminal"] == "XD3:11"
    assert decide(rescan_db, run, False)["status"] == "rejected"


def test_worker_cancel_and_expired_lease_cannot_finish(rescan_db):
    run = enqueue(rescan_db)
    old = claim(rescan_db)
    sql(
        rescan_db,
        f"update connection_rescan_runs set lease_until=now()-interval '1 minute' where id='{run['id']}';",
    )
    fresh = claim(rescan_db)
    assert old["lease_token"] != fresh["lease_token"]
    with pytest.raises(AssertionError, match="lease lost"):
        rpc(
            rescan_db,
            "advance_connection_rescan",
            {"id": old["id"], "token": old["lease_token"], "candidate": candidate()},
        )
    cancelled = rpc(
        rescan_db,
        "decide_connection_rescan",
        {"id": run["id"], "actor": OWNER, "project_id": PROJECT, "action": "cancel"},
    )
    assert cancelled["status"] == "cancelled"
    with pytest.raises(AssertionError, match="cancelled"):
        rpc(
            rescan_db,
            "advance_connection_rescan",
            {
                "id": fresh["id"],
                "token": fresh["lease_token"],
                "candidate": candidate(),
            },
        )
    assert row(rescan_db)["record_version"] == 1


def test_scope_masks_and_origin_cannot_be_overwritten(rescan_db):
    payload = candidate()
    payload["changes"][0]["after"]["workspace_code"] = "OTHER"
    run = ready(rescan_db, payload=payload)
    with pytest.raises(AssertionError, match="Protected candidate"):
        decide(rescan_db, run)
    assert row(rescan_db)["workspace_code"] == "001.A"
    decide(rescan_db, run, False)
    payload = candidate()
    payload["changes"][0]["after"]["start_terminal"] = "Wrong"
    run = ready(
        rescan_db,
        request={
            "scope": {"connection_ids": [ROW]},
            "fields": "end",
            "instructions": "只重扫终点",
        },
        payload=payload,
    )
    with pytest.raises(AssertionError, match="exceeds requested"):
        decide(rescan_db, run)


def test_new_rows_require_full_page_scope_and_keep_business_batch(rescan_db):
    payload = candidate()
    new_id = str(uuid4())
    payload["changes"].append(
        {
            "action": "insert",
            "connection_id": new_id,
            "record_version": 0,
            "source_pdf_page_number": 1,
            "source_drawing_page": "001A01",
            "workspace_code": "001.A",
            "after": {
                "principle_number": "NEW",
                "start_terminal": "XA:20",
                "end_terminal": "XB:21",
                "needs_review": True,
            },
            "evidence": {},
        }
    )
    run = ready(rescan_db, payload=payload)
    result = decide(rescan_db, run)
    saved = json.loads(
        sql(
            rescan_db,
            f"select to_jsonb(r) from extraction_connection_rows r where id='{new_id}';",
        ).strip()
    )
    assert saved["batch_id"] == "batch-a" and saved["source_drawing_page"] == "001A01"
    assert result["versions"][new_id] == 1 and saved["needs_review"]
    decide(rescan_db, run)
    assert (
        sql(rescan_db, "select count(*) from extraction_connection_rows;").strip()
        == "3"
    )


def test_owner_attachments_and_deleted_row_copies(rescan_db):
    with pytest.raises(AssertionError, match="owner"):
        enqueue(rescan_db, actor=OTHER)
    with pytest.raises(AssertionError, match="Attachment outside"):
        enqueue(rescan_db, attachment_ids=[str(uuid4())])
    run = ready(rescan_db)
    with pytest.raises(AssertionError, match="owner"):
        decide(rescan_db, run, actor=OTHER)
    sql(
        rescan_db,
        f"set role authenticated; set request.jwt.claim.sub='{OTHER}'; select count(*) from connection_rescan_runs;",
    )
    assert (
        sql(
            rescan_db,
            f"set role authenticated; set request.jwt.claim.sub='{OTHER}'; select count(*) from connection_rescan_runs;",
        )
        .strip()
        .splitlines()[-1]
        == "0"
    )
    with pytest.raises(AssertionError, match="permission denied"):
        sql(
            rescan_db,
            "set role authenticated; select claim_connection_rescan('forged');",
        )
    sql(rescan_db, f"delete from extraction_connection_rows where id='{ROW}';")
    assert sql(rescan_db, "select count(*) from connection_rescan_runs;").strip() == "0"


def test_empty_indexed_page_is_included_and_profile_version_is_frozen(rescan_db):
    sql(
        rescan_db,
        f'update extraction_projects set drawing_index=jsonb_set(drawing_index,\'{{pages}}\',drawing_index->\'pages\'||\'[{{"pdf_page_number":3,"drawing_page":"001A02","workspace_code":"001.A"}}]\'::jsonb) where id=\'{PROJECT}\';',
    )
    run = enqueue(rescan_db)
    job = claim(rescan_db)
    assert len(job["project_snapshot"]["scan_pages"]) == 2
    assert run["profile"]["version"] == "1.0.0"


def test_revalidated_same_pin_survives_label_correction_and_invalid_page_is_rejected(
    rescan_db,
):
    payload = candidate()
    payload["changes"][0]["after"]["end_terminal_coordinates"] = {
        "x": 0.7,
        "y": 0.8,
        "pdf_page_number": 2,
    }
    run = ready(rescan_db, payload=payload)
    saved = decide(rescan_db, run)
    assert row(rescan_db)["end_terminal_coordinates"] == {
        "x": 0.7,
        "y": 0.8,
        "pdf_page_number": 2,
    }
    assert row(rescan_db)["start_terminal_coordinates"] == {
        "x": 0.1,
        "y": 0.2,
        "pdf_page_number": 1,
    }
    assert saved["versions"][ROW] == row(rescan_db)["record_version"]
    payload = candidate()
    payload["changes"][0]["record_version"] = row(rescan_db)["record_version"]
    payload["changes"][0]["after"]["end_terminal_coordinates"]["pdf_page_number"] = 999
    run = ready(rescan_db, payload=payload)
    with pytest.raises(AssertionError, match="Coordinate page outside"):
        decide(rescan_db, run)


def test_assets_must_finish_upload_and_belong_to_same_conversation(rescan_db):
    identifier = str(uuid4())
    sql(
        rescan_db,
        f"insert into connection_rescan_assets(id,project_id,created_by,conversation_id,pdf_page_number,role,checksum,storage_path,width,height) values('{identifier}','{PROJECT}','{OWNER}','{CONVERSATION}',1,'source','sha256:'||repeat('a',64),'projects/test/assets/detail.png',1,1);",
    )
    with pytest.raises(AssertionError, match="Attachment outside"):
        enqueue(rescan_db, attachment_ids=[identifier])
    sql(
        rescan_db,
        f"update connection_rescan_assets set uploaded=true where id='{identifier}';",
    )
    with pytest.raises(AssertionError, match="Attachment outside"):
        enqueue(rescan_db, conversation_id=str(uuid4()), attachment_ids=[identifier])
    assert enqueue(rescan_db, attachment_ids=[identifier])["status"] == "queued"


def test_migration_applies_without_business_rows():
    name = "profile_publish_test_" + uuid4().hex
    sql("postgres", f'create database "{name}";')
    try:
        sql(
            name,
            "create schema auth; create table auth.users(id uuid primary key); create function auth.uid() returns uuid language sql as 'select null::uuid'; create function auth.role() returns text language sql as 'select current_setting(''request.jwt.claim.role'',true)'; grant usage on schema auth to authenticated,service_role;",
        )
        for file in (
            "20261014000000_create_simple_extraction_business_tables.sql",
            "20261016000000_simple_extraction_row_management.sql",
            "20261016010000_add_terminal_coordinates.sql",
            "20261018020000_explain_connection_edits.sql",
            "20261018050000_explain_rescan.sql",
        ):
            sql(name, (ROOT / "supabase/migrations" / file).read_text(encoding="utf-8"))
        assert sql(name, "select count(*) from connection_rescan_runs;").strip() == "0"
    finally:
        sql("postgres", f'drop database "{name}";')


def test_physical_page_scope_can_rescan_and_insert_into_empty_page(rescan_db):
    run = enqueue(
        rescan_db,
        request={
            "scope": {"pdf_page_numbers": [2]},
            "fields": "all",
            "instructions": "补漏空页",
        },
    )
    job = claim(rescan_db)
    assert not job["baseline"] and [
        p["pdf_page_number"] for p in job["project_snapshot"]["scan_pages"]
    ] == [2]
    identifier = str(uuid4())
    payload = {
        "changes": [
            {
                "action": "insert",
                "connection_id": identifier,
                "record_version": 0,
                "source_pdf_page_number": 2,
                "source_drawing_page": "002B01",
                "workspace_code": "002.B",
                "after": {
                    "start_terminal": "X1:1",
                    "end_terminal": "X2:2",
                    "needs_review": True,
                },
            }
        ],
        "warnings": [],
        "unmatched_ids": [],
    }
    result = rpc(
        rescan_db,
        "advance_connection_rescan",
        {
            "id": run["id"],
            "token": job["lease_token"],
            "candidate": payload,
            "stage": "ready",
        },
    )
    assert decide(rescan_db, result)["versions"][identifier] == 1
