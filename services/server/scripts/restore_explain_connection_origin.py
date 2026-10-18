"""Restore only an explicitly selected legacy proposal's origin; keep current endpoints."""

from __future__ import annotations

import argparse
import json
from typing import Any
from uuid import UUID

ORIGIN = (
    "workspace_code",
    "source_drawing_page",
    "source_pdf_page_number",
    "target_drawing_page",
    "target_pdf_page_number",
)


def literal(value: Any) -> str:
    return "'" + json.dumps(value, ensure_ascii=False).replace("'", "''") + "'::jsonb"


def restoration_sql(proposal: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    """Lock/check the snapshot, then restore origin without losing coordinates to invalidation."""
    project = str(UUID(proposal["project_id"]))
    identifier = str(UUID(proposal["proposal_id"]))
    if (
        proposal["status"] != "applied"
        or proposal["request"]["operation"]["kind"] != "swap_endpoints"
    ):
        raise ValueError("An applied legacy endpoint swap is required")
    changes = {change["connection_id"]: change for change in proposal["changes"]}
    if not rows or set(changes) != {row["id"] for row in rows}:
        raise ValueError("Exact proposal row set required")
    plan = []
    for row in rows:
        change = changes[row["id"]]
        if row["project_id"] != project or row["batch_id"] != proposal["batch_id"]:
            raise ValueError("Project or batch mismatch")
        if not all(
            key in change["before"] and key in change["after"] for key in ORIGIN
        ):
            raise ValueError("Legacy origin before/after is incomplete")
        if any(row.get(key) != change["after"][key] for key in ORIGIN):
            raise ValueError(
                "Current origin differs from the legacy proposal; inspect manually"
            )
        plan.append(
            {"expected": row, "origin": {key: change["before"][key] for key in ORIGIN}}
        )
    return f"""begin;
do $restore$
declare p extraction_projects; r extraction_connection_rows; saved extraction_connection_rows;
  item jsonb; plan jsonb:={literal(plan)}; audit jsonb:='[]'; corrected jsonb;
begin
  select * into p from extraction_projects where id='{project}' for update;
  if not found or p.status in ('processing','archived') then raise exception 'Project not editable'; end if;
  if coalesce(p.drawing_index->>'active_batch_id',{literal(proposal["batch_id"])}#>>'{{}}')
      is distinct from {literal(proposal["batch_id"])}#>>'{{}}' then raise exception 'Active batch changed'; end if;
  if not exists(select 1 from connection_edit_proposals where proposal_id='{identifier}'
      and project_id=p.id and created_by=p.owner_id and status='applied'
      and checksum={literal(proposal["checksum"])}#>>'{{}}') then raise exception 'Proposal changed'; end if;
  for item in select * from jsonb_array_elements(plan) loop
    select * into r from extraction_connection_rows where id=(item->'expected'->>'id')::uuid and project_id=p.id for update;
    if not found or to_jsonb(r) is distinct from item->'expected' then raise exception 'Row changed; no restoration applied'; end if;
  end loop;
  for item in select * from jsonb_array_elements(plan) loop
    select * into r from extraction_connection_rows where id=(item->'expected'->>'id')::uuid;
    saved:=jsonb_populate_record(r,item->'origin');
    -- First invalidate, then restore the exact known coordinate objects within this transaction.
    -- The established page-change trigger would otherwise clear unchanged coordinate values.
    update extraction_connection_rows set workspace_code=saved.workspace_code,
      source_drawing_page=saved.source_drawing_page,source_pdf_page_number=saved.source_pdf_page_number,
      target_drawing_page=saved.target_drawing_page,target_pdf_page_number=saved.target_pdf_page_number,
      start_terminal_coordinates=null,end_terminal_coordinates=null where id=r.id;
    corrected:=coalesce(r.evidence,'{{}}')||jsonb_build_object('origin_correction',jsonb_build_object(
      'proposal_id','{identifier}','time',now(),'reason','User requested original extraction page/workspace',
      'before',jsonb_build_object({",".join("'" + key + "',to_jsonb(r)->'" + key + "'" for key in ORIGIN)}),'after',item->'origin'));
    if jsonb_typeof(corrected->'manual_change'->'fields')='object' then
      corrected:=jsonb_set(corrected,'{{manual_change,fields}}',(corrected->'manual_change'->'fields')
        -array['workspace_code','source_drawing_page','source_pdf_page_number','target_drawing_page','target_pdf_page_number']);
    end if;
    update extraction_connection_rows set start_terminal_coordinates=r.start_terminal_coordinates,
      end_terminal_coordinates=r.end_terminal_coordinates,evidence=corrected where id=r.id returning * into saved;
    audit:=audit||jsonb_build_array(jsonb_build_object('action','restore_connection_origin','actor',p.owner_id,
      'time',now(),'before',to_jsonb(r),'after',to_jsonb(saved)));
  end loop;
  update extraction_projects set drawing_index=jsonb_set(drawing_index,'{{management}}',
    coalesce(drawing_index->'management','{{}}')||jsonb_build_object('audit',coalesce(drawing_index->'management'->'audit','[]')||audit)) where id=p.id;
end $restore$;
commit;"""


def main() -> None:
    import apply_explain_edits_migration as local

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=UUID, required=True)
    parser.add_argument("--proposal", type=UUID, required=True)
    parser.add_argument("--source-page", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--expected-count", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    label = local.command(
        [
            "docker",
            "inspect",
            "--format",
            '{{index .Config.Labels "com.supabase.cli.project"}}',
            local.CONTAINER,
        ]
    ).strip()
    if label != "zhenghua_test":
        raise RuntimeError("Local project label mismatch")
    proposal = json.loads(
        local.sql(
            f"select to_jsonb(p) from connection_edit_proposals p where project_id='{args.project}' and proposal_id='{args.proposal}';"
        ).strip()
    )
    rows = json.loads(
        local.sql(
            f"select jsonb_agg(to_jsonb(r) order by id) from extraction_connection_rows r where project_id='{args.project}' and id in (select (item->>'connection_id')::uuid from connection_edit_proposals p,jsonb_array_elements(p.changes) item where proposal_id='{args.proposal}');"
        ).strip()
    )
    if not isinstance(rows, list) or len(rows) != args.expected_count:
        raise RuntimeError("Expected row count changed")
    if not all(
        change["before"].get("source_drawing_page") == args.source_page
        and change["before"].get("workspace_code") == args.workspace
        for change in proposal["changes"]
    ):
        raise RuntimeError("Requested original page/workspace mismatch")
    statement = restoration_sql(proposal, rows)
    before = {row["id"]: row for row in rows}
    other_query = f"select md5(coalesce(string_agg(md5(to_jsonb(r)::text),'' order by id),'')) from extraction_connection_rows r where project_id='{args.project}' and id not in (select (item->>'connection_id')::uuid from connection_edit_proposals p,jsonb_array_elements(p.changes) item where proposal_id='{args.proposal}');"
    other_before = local.sql(other_query).strip()
    if args.apply:
        local.sql(statement)
        restored = json.loads(
            local.sql(
                f"select jsonb_agg(to_jsonb(r) order by id) from extraction_connection_rows r where project_id='{args.project}' and id in (select (item->>'connection_id')::uuid from connection_edit_proposals p,jsonb_array_elements(p.changes) item where proposal_id='{args.proposal}');"
            ).strip()
        )
        assert len(restored) == len(rows)
        for row in restored:
            unchanged = (
                set(row) - set(ORIGIN) - {"record_version", "updated_at", "evidence"}
            )
            assert all(row[key] == before[row["id"]][key] for key in unchanged)
            assert (
                row["source_drawing_page"] == args.source_page
                and row["workspace_code"] == args.workspace
            )
        assert local.sql(other_query).strip() == other_before
    print(
        json.dumps(
            {
                "applied": args.apply,
                "count": len(rows),
                "source_page": args.source_page,
                "workspace": args.workspace,
                "endpoint_values_preserved": True,
                "other_project_rows_preserved": True,
            }
        )
    )


if __name__ == "__main__":
    main()
