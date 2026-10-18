"""Explicit opt-in; reuse the independent PostgreSQL container, never the user's Supabase."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from test_profile_publication_sql import (  # noqa: F401 -- pytest fixture registration
    isolated_cluster,
    sql,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("EXPLAIN_EDIT_SQL_TEST") != "1", reason="opt-in isolated SQL test"
)
ROOT = Path(__file__).resolve().parents[3]
OWNER = "00000000-0000-0000-0000-000000000011"
OTHER = "00000000-0000-0000-0000-000000000012"
PROJECT = "00000000-0000-0000-0000-000000000030"
ROW = "00000000-0000-0000-0000-000000000041"


def literal(value):
    return "'" + json.dumps(value, ensure_ascii=False).replace("'", "''") + "'::jsonb"


@pytest.fixture
def database():
    name = "profile_publish_test_" + uuid4().hex
    sql("postgres", f'create database "{name}";')
    try:
        sql(
            name,
            f"""create schema auth; create table auth.users(id uuid primary key);
        create function auth.uid() returns uuid language sql as 'select nullif(current_setting(''request.jwt.claim.sub'',true),'''')::uuid';
        create function auth.role() returns text language sql as 'select current_setting(''request.jwt.claim.role'',true)';
        grant usage on schema auth to authenticated,service_role;
        insert into auth.users values('{OWNER}'),('{OTHER}');""",
        )
        for file in (
            "20261014000000_create_simple_extraction_business_tables.sql",
            "20261016000000_simple_extraction_row_management.sql",
            "20261016010000_add_terminal_coordinates.sql",
            "20261018020000_explain_connection_edits.sql",
            "20261018040000_swap_endpoints_keep_origin.sql",
        ):
            sql(name, (ROOT / "supabase/migrations" / file).read_text(encoding="utf-8"))
        sql(
            name,
            f"""insert into extraction_profiles(id,profile_key,profile_version,checksum,resource_ref,display_name,created_by)
          values('00000000-0000-0000-0000-000000000020','test','1.0.0','sha256:'||repeat('0',64),'local://test','Test','{OWNER}');
          insert into extraction_projects(id,owner_id,name,profile_id,drawing_index) values('{PROJECT}','{OWNER}','Test','00000000-0000-0000-0000-000000000020',
          '{{"active_batch_id":"batch-a","pages":[{{"pdf_page_number":1,"drawing_page":"001A01","workspace_code":"001.A"}},{{"pdf_page_number":2,"drawing_page":"002B01","workspace_code":"002.B"}}]}}');
          insert into extraction_connection_rows(id,project_id,batch_id,page_item_id,row_order,workspace_code,source_drawing_page,source_pdf_page_number,
            target_pdf_page_number,target_drawing_page,principle_number,start_code,start_description,start_terminal,end_code,end_description,end_terminal,is_cross_page,start_terminal_coordinates,end_terminal_coordinates,evidence)
          values('{ROW}','{PROJECT}','batch-a','row-one',0,'001.A','001A01',1,2,'002B01','P1','A','Start','XA:1','B','End','XD3:11',true,
            '{{"x":0.1,"y":0.2,"pdf_page_number":1}}','{{"x":0.7,"y":0.8,"pdf_page_number":2}}','{{"record":{{"start_terminal":"XA:1","source_note":"Original"}}}}'),
          ('00000000-0000-0000-0000-000000000042','{PROJECT}','batch-a','row-two',1,'001.A','001A01',1,null,null,'P2','A','Start2','XA:2','C','End2','ABXD4:2',false,null,null,'{{}}');""",
        )
        yield name
    finally:
        sql("postgres", f'drop database "{name}";')


def prepare(db, operation, scope=None, identifier=None, actor=OWNER):
    value = {
        "proposal_id": identifier or str(uuid4()),
        "actor": actor,
        "project_id": PROJECT,
        "batch_id": "batch-a",
        "user_request": "用户明确修改线表",
        "request": {
            "scope": scope or {"workspace_code": "001.A"},
            "operation": operation,
            "reason": "用户确认前预览",
        },
    }
    return json.loads(
        sql(
            db,
            "set request.jwt.claim.role='service_role'; select public.prepare_explain_connection_edit("
            + literal(value)
            + ");",
        )
        .strip()
        .splitlines()[-1]
    )


def decide(db, proposal, accepted=True, actor=OWNER):
    value = {
        "proposal_id": proposal["proposal_id"],
        "project_id": PROJECT,
        "actor": actor,
        "checksum": proposal["checksum"],
        "accepted": accepted,
    }
    return json.loads(
        sql(
            db,
            "set request.jwt.claim.role='service_role'; select public.decide_explain_connection_edit("
            + literal(value)
            + ");",
        )
        .strip()
        .splitlines()[-1]
    )


def test_prefix_preview_and_atomic_commit_with_idempotent_receipt(database):
    p = prepare(
        database, {"kind": "remove_terminal_prefix", "endpoint": "end", "prefix": "XD"}
    )
    assert p["matched_count"] == 2 and p["changed_count"] == 1
    assert p["changes"][0]["after"]["end_terminal"] == "3:11"
    assert (
        sql(
            database,
            f"select end_terminal from extraction_connection_rows where id='{ROW}';",
        ).strip()
        == "XD3:11"
    )
    receipt = decide(database, p)
    assert receipt["versions"][ROW] == 2
    assert (
        sql(
            database,
            f"select end_terminal||'|'||start_terminal from extraction_connection_rows where id='{ROW}';",
        ).strip()
        == "3:11|XA:1"
    )
    assert (
        sql(
            database,
            "select end_terminal from extraction_connection_rows where principle_number='P2';",
        ).strip()
        == "ABXD4:2"
    )
    assert decide(database, p)["idempotent"] is True
    assert (
        sql(
            database,
            f"select evidence->'manual_change'->>'proposal_id' from extraction_connection_rows where id='{ROW}';",
        ).strip()
        == p["proposal_id"]
    )


def test_delete_removes_row_copies_and_related_proposals_but_keeps_retry_receipt(
    database,
):
    # First exercise the old function: deleted field values used to survive in audit/receipts.
    prefix = "set request.jwt.claim.role='service_role'; select public.manage_extraction_connection("
    edit = {
        "actor": OWNER,
        "project_id": PROJECT,
        "action": "edit",
        "key": "old-edit",
        "connection_id": ROW,
        "body": {
            "record_version": 1,
            "changes": {"end_terminal": "SECRET-DELETED-END"},
        },
    }
    sql(database, prefix + literal(edit) + ");")
    affected = prepare(database, {"kind": "swap_terminals"}, {"connection_ids": [ROW]})
    unaffected = prepare(
        database, {"kind": "swap_terminals"}, {"principle_numbers": ["P2"]}
    )
    migration = (
        ROOT / "supabase/migrations/20261018030000_connection_delete_no_snapshot.sql"
    )
    sql(database, migration.read_text(encoding="utf-8"))
    request = {
        "actor": OWNER,
        "project_id": PROJECT,
        "action": "remove",
        "key": "delete-one",
        "connection_id": ROW,
        "body": {"record_version": 2, "confirmed": True},
    }
    receipt = json.loads(
        sql(database, prefix + literal(request) + ");").strip().splitlines()[-1]
    )
    assert receipt["connection_id"] == ROW
    assert (
        sql(
            database,
            f"select count(*) from extraction_connection_rows where id='{ROW}';",
        ).strip()
        == "0"
    )
    management = json.loads(
        sql(
            database,
            f"select drawing_index->'management' from extraction_projects where id='{PROJECT}';",
        ).strip()
    )
    assert "SECRET-DELETED-END" not in json.dumps(management)
    assert management["audit"] == []
    assert set(management["receipts"]) == {"delete-one"}
    assert (
        json.loads(
            sql(database, prefix + literal(request) + ");").strip().splitlines()[-1]
        )["idempotent"]
        is True
    )
    assert (
        sql(
            database,
            f"select count(*) from connection_edit_proposals where proposal_id='{affected['proposal_id']}';",
        ).strip()
        == "0"
    )
    assert (
        sql(
            database,
            f"select count(*) from connection_edit_proposals where proposal_id='{unaffected['proposal_id']}';",
        ).strip()
        == "1"
    )
    assert (
        sql(
            database,
            "select count(*) from extraction_connection_rows where principle_number='P2';",
        ).strip()
        == "1"
    )
    request["body"]["confirmed"] = False
    with pytest.raises(AssertionError, match="Idempotency key reused"):
        sql(database, prefix + literal(request) + ");")


def test_delete_rejection_keeps_rows_and_proposals_unchanged(database):
    sql(
        database,
        (
            ROOT
            / "supabase/migrations/20261018030000_connection_delete_no_snapshot.sql"
        ).read_text(encoding="utf-8"),
    )
    proposal = prepare(database, {"kind": "swap_terminals"}, {"connection_ids": [ROW]})
    request = {
        "actor": OWNER,
        "project_id": PROJECT,
        "action": "remove",
        "key": "remove-rejected",
        "connection_id": ROW,
        "body": {"record_version": 1, "confirmed": True},
    }
    for actor, body, error in (
        (OTHER, {"record_version": 1, "confirmed": True}, "Project owner required"),
        (OWNER, {"record_version": 99, "confirmed": True}, "Record version changed"),
        (
            OWNER,
            {"record_version": 1, "confirmed": False},
            "Deletion confirmation required",
        ),
        (
            OWNER,
            {
                "record_version": 1,
                "confirmed": True,
                "end_terminal": "copy-not-allowed",
            },
            "Invalid deletion request",
        ),
    ):
        with pytest.raises(AssertionError, match=error):
            sql(
                database,
                "set request.jwt.claim.role='service_role'; select manage_extraction_connection("
                + literal({**request, "actor": actor, "body": body})
                + ");",
            )
    sql(
        database,
        f"update extraction_projects set status='processing' where id='{PROJECT}';",
    )
    with pytest.raises(AssertionError, match="read only while processing"):
        sql(
            database,
            "set request.jwt.claim.role='service_role'; select manage_extraction_connection("
            + literal(request)
            + ");",
        )
    assert (
        sql(
            database,
            f"select count(*) from extraction_connection_rows where id='{ROW}';",
        ).strip()
        == "1"
    )
    assert (
        sql(
            database,
            f"select status from connection_edit_proposals where proposal_id='{proposal['proposal_id']}';",
        ).strip()
        == "pending"
    )


def test_whole_endpoint_swap_keeps_origin_and_moves_only_endpoint_values(database):
    p = prepare(database, {"kind": "swap_endpoints"}, {"principle_numbers": ["P1"]})
    after = p["changes"][0]["after"]
    assert after["start_code"] == "B" and after["start_description"] == "End"
    assert not {
        "source_pdf_page_number",
        "source_drawing_page",
        "workspace_code",
        "target_pdf_page_number",
        "target_drawing_page",
    }.intersection(after)
    assert after["start_terminal_coordinates"]["pdf_page_number"] == 2
    decide(database, p)
    saved = json.loads(
        sql(
            database,
            f"select to_jsonb(t) from extraction_connection_rows t where id='{ROW}';",
        ).strip()
    )
    assert saved["start_terminal"] == "XD3:11" and saved["end_terminal"] == "XA:1"
    assert (
        saved["start_terminal_coordinates"]["x"] == 0.7
        and saved["end_terminal_coordinates"]["x"] == 0.1
    )
    assert (
        saved["page_item_id"] == "row-one"
        and saved["evidence"]["record"]["source_note"] == "Original"
    )
    assert saved["id"] == ROW and saved["source_drawing_page"] == "001A01"
    assert saved["source_pdf_page_number"] == 1 and saved["workspace_code"] == "001.A"
    assert (
        saved["target_drawing_page"] == "002B01"
        and saved["target_pdf_page_number"] == 2
    )
    decide(database, p)
    assert (
        sql(
            database,
            f"select record_version from extraction_connection_rows where id='{ROW}';",
        ).strip()
        == "2"
    )


def test_legacy_proposal_that_moves_origin_is_rejected_without_partial_updates(
    database,
):
    original = (
        ROOT / "supabase/migrations/20261018020000_explain_connection_edits.sql"
    ).read_text(encoding="utf-8")
    legacy_helper = original[
        original.index("create function public.explain_edit_fields(") : original.index(
            "create function public.prepare_explain_connection_edit("
        )
    ]
    sql(
        database,
        legacy_helper.replace("create function", "create or replace function", 1),
    )
    proposal = prepare(
        database, {"kind": "swap_endpoints"}, {"principle_numbers": ["P1"]}
    )
    sql(
        database,
        (
            ROOT / "supabase/migrations/20261018040000_swap_endpoints_keep_origin.sql"
        ).read_text(encoding="utf-8"),
    )
    with pytest.raises(AssertionError, match="EDIT_ORIGIN_CHANGE_FORBIDDEN"):
        decide(database, proposal)
    assert (
        sql(
            database,
            f"select source_drawing_page||'|'||start_terminal||'|'||record_version from extraction_connection_rows where id='{ROW}';",
        ).strip()
        == "001A01|XA:1|1"
    )


def test_restore_legacy_origin_preserves_confirmed_endpoints_and_coordinates(database):
    legacy = (
        ROOT / "supabase/migrations/20261018020000_explain_connection_edits.sql"
    ).read_text(encoding="utf-8")
    for start, end in (
        (
            "create function public.explain_edit_fields(",
            "create function public.prepare_explain_connection_edit(",
        ),
        (
            "create function public.decide_explain_connection_edit(",
            "revoke all on function public.explain_edit_public(",
        ),
    ):
        sql(
            database,
            legacy[legacy.index(start) : legacy.index(end)].replace(
                "create function", "create or replace function", 1
            ),
        )
    proposal = prepare(
        database, {"kind": "swap_endpoints"}, {"principle_numbers": ["P1"]}
    )
    decide(database, proposal)
    sql(
        database,
        (
            ROOT / "supabase/migrations/20261018040000_swap_endpoints_keep_origin.sql"
        ).read_text(encoding="utf-8"),
    )
    full_proposal = json.loads(
        sql(
            database,
            f"select to_jsonb(p) from connection_edit_proposals p where proposal_id='{proposal['proposal_id']}';",
        ).strip()
    )
    moved = json.loads(
        sql(
            database,
            f"select to_jsonb(r) from extraction_connection_rows r where id='{ROW}';",
        ).strip()
    )
    assert moved["source_drawing_page"] == "002B01"
    script = ROOT / "services/server/scripts/restore_explain_connection_origin.py"
    spec = importlib.util.spec_from_file_location("origin_restore", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    statement = module.restoration_sql(full_proposal, [moved])
    # The snapshot is mandatory; a later edit must abort the whole restoration.
    sql(
        database,
        f"update extraction_connection_rows set remark='Preserve later edit' where id='{ROW}';",
    )
    with pytest.raises(AssertionError, match="Row changed"):
        sql(database, statement)
    fresh = json.loads(
        sql(
            database,
            f"select to_jsonb(r) from extraction_connection_rows r where id='{ROW}';",
        ).strip()
    )
    sql(database, module.restoration_sql(full_proposal, [fresh]))
    saved = json.loads(
        sql(
            database,
            f"select to_jsonb(r) from extraction_connection_rows r where id='{ROW}';",
        ).strip()
    )
    assert (
        saved["source_drawing_page"] == "001A01" and saved["workspace_code"] == "001.A"
    )
    assert saved["source_pdf_page_number"] == 1 and saved["target_pdf_page_number"] == 2
    for field in (
        "id",
        "batch_id",
        "page_item_id",
        "row_order",
        "start_code",
        "end_code",
        "start_terminal",
        "end_terminal",
        "start_terminal_coordinates",
        "end_terminal_coordinates",
        "remark",
    ):
        assert saved[field] == fresh[field]
    assert saved["record_version"] == fresh["record_version"] + 2
    assert "source_drawing_page" not in saved["evidence"]["manual_change"]["fields"]


def test_row_conflict_rejects_entire_batch_and_scope_growth_is_not_ignored(database):
    p = prepare(database, {"kind": "set_fields", "changes": {"remark": "Changed"}})
    sql(
        database,
        "update extraction_connection_rows set remark='Concurrent' where principle_number='P2';",
    )
    with pytest.raises(AssertionError, match="version changed"):
        decide(database, p)
    assert (
        sql(
            database,
            f"select coalesce(remark,'NULL') from extraction_connection_rows where id='{ROW}';",
        ).strip()
        == "NULL"
    )
    p = prepare(
        database, {"kind": "remove_terminal_prefix", "endpoint": "end", "prefix": "XD"}
    )
    sql(
        database,
        f"insert into extraction_connection_rows(project_id,batch_id,page_item_id,row_order,source_pdf_page_number,workspace_code) values('{PROJECT}','batch-a','new',5,1,'001.A');",
    )
    with pytest.raises(AssertionError, match="scope or row version"):
        decide(database, p)


def test_permissions_rejection_expiry_processing_and_unknown_target(database):
    with pytest.raises(AssertionError, match="owner required"):
        prepare(database, {"kind": "swap_terminals"}, actor=OTHER)
    p = prepare(database, {"kind": "swap_terminals"})
    assert decide(database, p, False)["status"] == "rejected"
    with pytest.raises(AssertionError, match="already decided"):
        decide(database, p)
    p = prepare(database, {"kind": "swap_terminals"})
    sql(
        database,
        f"update connection_edit_proposals set expires_at=now()-interval '1 second' where proposal_id='{p['proposal_id']}';",
    )
    with pytest.raises(AssertionError, match="expired"):
        decide(database, p)
    sql(
        database,
        f"update extraction_projects set status='processing' where id='{PROJECT}';",
    )
    with pytest.raises(AssertionError, match="not editable"):
        prepare(database, {"kind": "swap_endpoints"})
    sql(
        database,
        f"update extraction_projects set status='ready' where id='{PROJECT}'; update extraction_connection_rows set target_pdf_page_number=null where id='{ROW}';",
    )
    proposal = prepare(
        database, {"kind": "swap_endpoints"}, {"principle_numbers": ["P1"]}
    )
    assert "target_pdf_page_number" not in proposal["changes"][0]["after"]
    decide(database, proposal)
    sql(
        database,
        "set role authenticated; do $$ begin begin perform public.prepare_explain_connection_edit('{}'); raise exception 'unexpected permission'; exception when insufficient_privilege then null; end; end $$;",
    )


def test_scope_limit_noop_and_drawing_index_guard(database):
    p = prepare(
        database,
        {"kind": "remove_terminal_prefix", "endpoint": "end", "prefix": "NOT_PRESENT"},
    )
    assert p["matched_count"] == 2 and p["changed_count"] == 0
    assert decide(database, p)["changed_count"] == 0
    p = prepare(database, {"kind": "swap_endpoints"}, {"principle_numbers": ["P1"]})
    sql(
        database,
        f"update extraction_projects set drawing_index=jsonb_set(drawing_index,'{{pages,1,drawing_page}}','\"CHANGED\"') where id='{PROJECT}';",
    )
    with pytest.raises(AssertionError, match="Drawing index changed"):
        decide(database, p)
    sql(
        database,
        f"insert into extraction_connection_rows(project_id,batch_id,page_item_id,row_order,source_pdf_page_number,workspace_code,end_terminal) select '{PROJECT}','batch-a','large-'||n,n,1,'LARGE','XD9:1' from generate_series(1,1001) n;",
    )
    with pytest.raises(AssertionError, match="EDIT_SCOPE_TOO_LARGE"):
        prepare(
            database,
            {"kind": "remove_terminal_prefix", "endpoint": "end", "prefix": "XD"},
            {"workspace_code": "LARGE"},
        )
    assert (
        sql(
            database,
            "select count(*) from connection_edit_proposals where request->'scope'->>'workspace_code'='LARGE';",
        ).strip()
        == "0"
    )


def test_proposal_rls_and_explicit_null_field_audit(database):
    p = prepare(
        database,
        {"kind": "set_fields", "changes": {"end_terminal": None}},
        {"principle_numbers": ["P1"]},
    )
    assert p["changes"][0]["after"]["needs_review"] is True
    assert p["changes"][0]["after"]["end_terminal_coordinates"] is None
    hidden = sql(
        database,
        f"set role authenticated; set request.jwt.claim.sub='{OTHER}'; select count(*) from connection_edit_proposals;",
    )
    assert hidden.strip().splitlines()[-1] == "0"
    visible = sql(
        database,
        f"set role authenticated; set request.jwt.claim.sub='{OWNER}'; select count(*) from connection_edit_proposals;",
    )
    assert visible.strip().splitlines()[-1] == "1"
    decide(database, p)
    saved = json.loads(
        sql(
            database,
            f"select to_jsonb(r) from extraction_connection_rows r where id='{ROW}';",
        ).strip()
    )
    assert (
        saved["end_terminal"] is None
        and saved["needs_review"] is True
        and saved["end_terminal_coordinates"] is None
    )
