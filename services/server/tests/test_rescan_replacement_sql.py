"""Range replacement in a disposable PostgreSQL; never the user's business database."""

import json
import os
from uuid import uuid4

import pytest
import test_explain_rescan_sql as seed
from test_explain_rescan_sql import (
    OTHER,
    PROJECT,
    ROOT,
    ROW,
    claim,
    decide,
    enqueue,
    literal,
    rpc,
)
from test_profile_publication_sql import sql

database = seed.database
isolated_cluster = seed.isolated_cluster
pytestmark = pytest.mark.skipif(
    os.environ.get("EXPLAIN_RESCAN_SQL_TEST") != "1", reason="isolated SQL opt-in"
)
NEW = ROOT / "supabase/migrations/20261019010000_rescan_scope_replacement.sql"
FIELDS = [
    "principle_number",
    "terminal_strip",
    "start_code",
    "start_description",
    "start_terminal",
    "end_code",
    "end_description",
    "end_terminal",
    "current_value",
    "remark",
    "start_terminal_coordinates",
    "end_terminal_coordinates",
    "target_pdf_page_number",
    "target_drawing_page",
    "is_cross_page",
    "needs_review",
]


def rows(db):
    return json.loads(
        sql(
            db,
            f"select coalesce(jsonb_agg(to_jsonb(r) order by id),'[]') from extraction_connection_rows r where project_id='{PROJECT}';",
        ).strip()
    )


def install(db):
    before = rows(db)
    sql(
        db,
        (ROOT / "supabase/migrations/20261018050000_explain_rescan.sql").read_text(
            encoding="utf-8"
        ),
    )
    sql(db, NEW.read_text(encoding="utf-8"))
    assert rows(db) == before


@pytest.fixture
def replacement_db(database):
    install(database)
    return database


def replacement_request(**kwargs):
    return {
        "scope": {"workspace_code": "001.A"},
        "fields": "all",
        "instructions": "全部替换",
        "result_mode": "replace_scope",
        **kwargs,
    }


def replacement_ready(db, count=2, request=None):
    run = enqueue(db, request=request or replacement_request())
    job = claim(db)
    baseline = job["baseline"]
    removed = [
        {
            "connection_id": r["id"],
            "record_version": r["record_version"],
            "source_pdf_page_number": r["source_pdf_page_number"],
            "source_drawing_page": r["source_drawing_page"],
            "workspace_code": r["workspace_code"],
            "principle_number": r["principle_number"],
            "before": {field: r.get(field) for field in FIELDS},
        }
        for r in baseline
    ]
    changes = [
        {
            "action": "insert",
            "connection_id": str(uuid4()),
            "record_version": 0,
            "source_pdf_page_number": 1,
            "source_drawing_page": "001A01",
            "workspace_code": "001.A",
            "principle_number": f"NEW{i}",
            "before": {},
            "after": {
                "principle_number": f"NEW{i}",
                "start_terminal": f"X1:{i}",
                "end_terminal": f"X2:{i}",
                "start_terminal_coordinates": {
                    "x": 0.2,
                    "y": 0.3,
                    "pdf_page_number": 1,
                },
                "end_terminal_coordinates": {"x": 0.5, "y": 0.6, "pdf_page_number": 2},
                "needs_review": False,
            },
            "evidence": {},
        }
        for i in range(count)
    ]
    candidate = {
        "changes": changes,
        "warnings": [],
        "unmatched_ids": [],
        "replacement": {"version": 1, "scanned_pages": [1], "removed": removed},
    }
    ready = rpc(
        db,
        "advance_connection_rescan",
        {
            "id": job["id"],
            "token": job["lease_token"],
            "candidate": candidate,
            "stage": "ready",
        },
    )
    assert ready["id"] == run["id"]
    return ready


def rewrite_candidate(db, run, mutate):
    candidate = run["candidate"]
    mutate(candidate)
    checksum = "changed-preview"
    sql(
        db,
        f"update connection_rescan_runs set candidate={literal(candidate)},checksum='{checksum}' where id='{run['id']}';",
    )
    return {**run, "candidate": candidate, "checksum": checksum}


def test_full_scope_is_physically_replaced_only_after_confirmation_and_is_idempotent(
    replacement_db,
):
    db = replacement_db
    sql(
        db,
        f"insert into extraction_connection_rows(id,project_id,batch_id,page_item_id,row_order,workspace_code,source_drawing_page,source_pdf_page_number) values('{uuid4()}','{PROJECT}','batch-a','outside',0,'002.B','002B01',2);",
    )
    before = rows(db)
    run = replacement_ready(db, count=3)
    assert rows(db) == before
    other = enqueue(db)
    saved = decide(db, run)
    after = rows(db)
    assert len(after) == 4 and not {
        r["id"] for r in before if r["source_pdf_page_number"] == 1
    }.intersection(r["id"] for r in after)
    assert [r for r in after if r["source_pdf_page_number"] == 2] == [
        r for r in before if r["source_pdf_page_number"] == 2
    ]
    assert len(saved["versions"]) == 3 and saved["status"] == "applied"
    assert (
        sql(
            db, f"select count(*) from connection_rescan_runs where id='{other['id']}';"
        ).strip()
        == "0"
    )
    stored = json.loads(
        sql(
            db,
            f"select to_jsonb(r) from connection_rescan_runs r where id='{run['id']}';",
        ).strip()
    )
    assert len(stored["baseline"]) == 2 and stored["receipt"]["replacement"] is True
    assert decide(db, run)["versions"] == saved["versions"] and rows(db) == after


def test_empty_result_can_replace_scope_with_empty_after_explicit_confirmation(
    replacement_db,
):
    db = replacement_db
    before = rows(db)
    run = replacement_ready(db, count=0)
    assert rows(db) == before and len(run["candidate"]["replacement"]["removed"]) == 2
    saved = decide(db, run)
    assert rows(db) == [] and saved["status"] == "applied" and saved["versions"] == {}
    assert decide(db, run)["status"] == "applied"


def test_rejection_preserves_entire_old_scope(replacement_db):
    before = rows(replacement_db)
    run = replacement_ready(replacement_db)
    assert decide(replacement_db, run, accepted=False)["status"] == "rejected"
    assert rows(replacement_db) == before


@pytest.mark.parametrize(
    "kind",
    [
        "missing_delete",
        "wrong_preview",
        "wrong_pages",
        "existing_id",
        "duplicate_id",
        "missing_changes",
        "wrong_origin",
        "protected_field",
    ],
)
def test_invalid_or_out_of_scope_replacement_rolls_everything_back(
    replacement_db, kind
):
    db = replacement_db
    run = replacement_ready(db)
    before = rows(db)

    def mutate(c):
        if kind == "missing_delete":
            c["replacement"]["removed"].pop()
        elif kind == "wrong_preview":
            c["replacement"]["removed"][0]["before"]["start_terminal"] = "FAKE"
        elif kind == "wrong_pages":
            c["replacement"]["scanned_pages"] = [2]
        elif kind == "existing_id":
            c["changes"][0]["connection_id"] = ROW
        elif kind == "duplicate_id":
            c["changes"][1]["connection_id"] = c["changes"][0]["connection_id"]
        elif kind == "missing_changes":
            c.pop("changes")
        elif kind == "wrong_origin":
            c["changes"][0]["source_pdf_page_number"] = 2
        else:
            c["changes"][0]["after"]["workspace_code"] = "OUTSIDE"

    run = rewrite_candidate(db, run, mutate)
    with pytest.raises(AssertionError):
        decide(db, run)
    assert rows(db) == before
    stored = json.loads(
        sql(
            db,
            f"select to_jsonb(r) from connection_rescan_runs r where id='{run['id']}';",
        ).strip()
    )
    assert stored["status"] == "ready" and len(stored["baseline"]) == 2


@pytest.mark.parametrize(
    "kind", ["version", "new_row", "removed_row", "batch", "index", "expired"]
)
def test_concurrent_scope_or_project_changes_are_rejected(replacement_db, kind):
    db = replacement_db
    run = replacement_ready(db)
    if kind == "version":
        sql(
            db,
            f"update extraction_connection_rows set start_terminal='OTHER' where id='{ROW}';",
        )
    elif kind == "new_row":
        sql(
            db,
            f"insert into extraction_connection_rows(id,project_id,batch_id,page_item_id,row_order,workspace_code,source_drawing_page,source_pdf_page_number) values('{uuid4()}','{PROJECT}','batch-a','new',9,'001.A','001A01',1);",
        )
    elif kind == "removed_row":
        sql(db, f"delete from extraction_connection_rows where id='{ROW}';")
    elif kind == "batch":
        sql(
            db,
            f"update extraction_projects set drawing_index=jsonb_set(drawing_index,'{{active_batch_id}}','\"other\"') where id='{PROJECT}';",
        )
    elif kind == "index":
        sql(
            db,
            f"update extraction_projects set drawing_index=jsonb_set(drawing_index,'{{pages}}','[]') where id='{PROJECT}';",
        )
    else:
        sql(
            db,
            f"update connection_rescan_runs set expires_at=now()-interval '1 minute' where id='{run['id']}';",
        )
    before = rows(db)
    with pytest.raises(AssertionError):
        decide(db, run)
    assert rows(db) == before


def test_patch_only_changes_selected_fields_without_removing_other_rows(replacement_db):
    db = replacement_db
    run = seed.ready(
        db,
        request={
            "scope": {"connection_ids": [ROW]},
            "fields": "end",
            "result_mode": "patch",
        },
    )
    before = rows(db)
    saved = decide(db, run)
    after = rows(db)
    assert len(after) == len(before) and ROW in saved["versions"]
    assert next(r for r in after if r["id"] == ROW)["start_terminal"] == "XA:1"
    assert next(r for r in after if r["id"] == ROW)["end_terminal"] == "X9:2"
    assert [r for r in after if r["id"] != ROW] == [r for r in before if r["id"] != ROW]


def test_legacy_ready_full_scope_cannot_be_confirmed_as_merge(database):
    db = database
    sql(
        db,
        (ROOT / "supabase/migrations/20261018050000_explain_rescan.sql").read_text(
            encoding="utf-8"
        ),
    )
    run = seed.ready(db)
    before = rows(db)
    sql(db, NEW.read_text(encoding="utf-8"))
    with pytest.raises(AssertionError, match="Legacy full rescan"):
        decide(db, run)
    assert rows(db) == before
    assert decide(db, run, accepted=False)["status"] == "rejected"


def test_migration_works_without_business_rows_and_restricts_private_helper(database):
    db = database
    sql(
        db,
        "delete from extraction_connection_rows; delete from extraction_projects; delete from extraction_profiles;",
    )
    install(db)
    assert (
        sql(
            db,
            "select has_function_privilege('authenticated','decide_connection_rescan(jsonb)','execute'),has_function_privilege('service_role','decide_connection_rescan(jsonb)','execute'),has_function_privilege('service_role','decide_connection_rescan_patch(jsonb)','execute');",
        ).strip()
        == "f|t|f"
    )
    assert (
        sql(
            db,
            "set request.jwt.claim.role='service_role'; select rescan_replacement_contract();",
        )
        .strip()
        .splitlines()[-1]
        == "1"
    )


def test_other_owner_cannot_confirm_scope_replacement(replacement_db):
    db = replacement_db
    run = replacement_ready(db)
    before = rows(db)
    with pytest.raises(AssertionError):
        decide(db, run, actor=OTHER)
    assert rows(db) == before
