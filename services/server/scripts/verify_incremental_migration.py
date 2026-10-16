"""Explicit local Docker acceptance in disposable databases; never writes the project DB."""

from __future__ import annotations

import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
CONTAINER = "supabase_db_zhenghua_test"


def docker(*args: str, content: bytes | None = None) -> bytes:
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            CONTAINER,
            "sh",
            "-c",
            'export PGPASSWORD="$POSTGRES_PASSWORD"; exec "$@"',
            "--",
            *args,
        ],
        input=content,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace")[-3000:])
    return result.stdout


def sql(database: str, content: str) -> str:
    return docker(
        "psql",
        "-U",
        "supabase_admin",
        "-d",
        database,
        "-v",
        "ON_ERROR_STOP=1",
        "-At",
        content=content.encode(),
    ).decode()


SEED = """
insert into auth.users(id) values ('11111111-1111-4111-8111-111111111111');
insert into public.extraction_profiles(id,profile_key,profile_version,checksum,resource_ref,display_name,created_by)
values('22222222-2222-4222-8222-222222222222','synthetic','1.0.0','sha256:'||repeat('a',64),'local://synthetic','synthetic','11111111-1111-4111-8111-111111111111');
insert into public.extraction_projects(id,owner_id,name,profile_id,drawing_index)
values('33333333-3333-4333-8333-333333333333','11111111-1111-4111-8111-111111111111','synthetic','22222222-2222-4222-8222-222222222222',
'{"upload_state":"saved","source":{"page_count":2,"checksum":"sha256:fixture"}}');
insert into public.extraction_connection_rows(project_id,batch_id,page_item_id,row_order,source_pdf_page_number,start_terminal)
values('33333333-3333-4333-8333-333333333333','old-batch','old-row',0,1,'old-terminal');
"""

CHECK = """
do $$
declare project uuid:='33333333-3333-4333-8333-333333333333';
  actor uuid:='11111111-1111-4111-8111-111111111111'; run uuid:='44444444-4444-4444-8444-444444444444';
  job jsonb; token text; value jsonb; row jsonb; answer jsonb;
begin
  begin
    perform public.start_simple_extraction(project,'55555555-5555-4555-8555-555555555555',run);
    raise exception 'owner check failed';
  exception when sqlstate 'PT403' then null; end;
  perform public.start_simple_extraction(project,actor,run);
  perform public.start_simple_extraction(project,actor,run);
  if (select count(*) from public.agent_runs where id=run)<>1 then raise exception 'duplicate run'; end if;
  job:=public.claim_simple_extraction('test-worker'); token:=job->'lease'->>'token';
  if job->'run'->>'id'<>run::text then raise exception 'claim mismatch'; end if;
  if public.claim_simple_extraction('second-worker') is not null then raise exception 'lease claimed twice'; end if;
  value:=jsonb_build_object('kind','rendered','stage','render','page',
    jsonb_build_object('pdf_page_number',1,'workspace_code','','status','rendered','image_path','projects/'||project||'/pages/1.png'));
  perform public.commit_simple_extraction(run,'test-worker',token,'render:1',value);
  value:=jsonb_set(value,'{kind}','"classified"'::jsonb);
  value:=jsonb_set(value,'{stage}','"classification"'::jsonb);
  value:=jsonb_set(value,'{page,status}','"classified"'::jsonb);
  value:=jsonb_set(value,'{page,workspace_code}','"002.C"'::jsonb);
  perform public.commit_simple_extraction(run,'test-worker',token,'classify:1',value);
  if jsonb_array_length((select drawing_index->'pages' from public.extraction_projects where id=project))<>1 then
    raise exception 'duplicate indexed page'; end if;
  row:=jsonb_build_object('id','66666666-6666-4666-8666-666666666666','project_id',project,
    'batch_id',run::text,'page_item_id','one','row_order',0,'source_pdf_page_number',1,
    'start_terminal','X3:1','end_terminal',null,'is_cross_page',true,'needs_review',false,
    'evidence',jsonb_build_object('processing_status','pending_completion'));
  value:=jsonb_build_object('kind','scan','stage','scan','pdf_page_number',1,'rows',jsonb_build_array(row));
  perform public.commit_simple_extraction(run,'test-worker',token,'scan:1',value);
  answer:=public.commit_simple_extraction(run,'test-worker',token,'scan:1',value);
  if answer->>'idempotent'<>'true' then raise exception 'replay failed'; end if;
  begin
    perform public.commit_simple_extraction(run,'test-worker','wrong-token','bad',value);
    raise exception 'fencing failed';
  exception when sqlstate 'PT409' then null; end;
  row:=row||'{"end_terminal":"XD21:7","evidence":{"processing_status":"completed"}}'::jsonb;
  value:=jsonb_build_object('kind','completion','stage','completion','pdf_page_number',1,'rows',jsonb_build_array(row));
  perform public.commit_simple_extraction(run,'test-worker',token,'completion:1',value);
  if (select count(*) from public.extraction_connection_rows where batch_id=run::text)<>1 then raise exception 'duplicate row'; end if;
  if (select record_version from public.extraction_connection_rows where batch_id=run::text)<>2 then raise exception 'row version mismatch'; end if;
  if (select end_terminal from public.extraction_connection_rows where batch_id=run::text)<>'XD21:7' then raise exception 'end missing'; end if;
  value:=jsonb_build_object('kind','page_completed','stage','page_completed','page',
    jsonb_build_object('pdf_page_number',1,'workspace_code','002.C','status','completed','image_path','projects/'||project||'/pages/1.png'),
    'rows',jsonb_build_array(row));
  perform public.commit_simple_extraction(run,'test-worker',token,'page:1',value);
  if (select record_version from public.extraction_connection_rows where batch_id=run::text)<>2 then raise exception 'unchanged row rewritten'; end if;
  -- Simulate an out-of-band manual update; the Worker must not overwrite it.
  update public.extraction_connection_rows set end_terminal='manual' where batch_id=run::text;
  begin
    perform public.commit_simple_extraction(run,'test-worker',token,'late',value);
    raise exception 'manual version guard failed';
  exception when sqlstate 'PT409' then null; end;
  if not exists(select 1 from public.extraction_connection_rows where batch_id='old-batch' and start_terminal='old-terminal') then
    raise exception 'historical rows changed'; end if;
  if has_function_privilege('authenticated','public.commit_simple_extraction(uuid,text,text,text,jsonb)','execute') then
    raise exception 'browser can call internal RPC'; end if;
  perform public.commit_simple_extraction(run,'test-worker',token,'failed:test','{"kind":"failed","stage":"failed"}');
  perform public.start_simple_extraction(project,actor,run,true);
  job:=public.claim_simple_extraction('replacement-worker');
  begin
    perform public.commit_simple_extraction(run,'test-worker',token,'stale',value);
    raise exception 'old worker still owns lease';
  exception when sqlstate 'PT409' then null; end;
  token:=job->'lease'->>'token';
  value:=jsonb_build_object('kind','page_completed','stage','page_completed','rows','[]'::jsonb,'page',
    jsonb_build_object('pdf_page_number',2,'workspace_code','002.C','status','needs_review','image_path','projects/'||project||'/pages/2.png'));
  perform public.commit_simple_extraction(run,'replacement-worker',token,'page:2',value);
  perform public.commit_simple_extraction(run,'replacement-worker',token,'finish','{"kind":"finished","stage":"finished"}');
  perform public.commit_simple_extraction(run,'replacement-worker',token,'finish','{"kind":"finished","stage":"finished"}');
  if (select status from public.agent_runs where id=run)<>'NEEDS_REVIEW' then raise exception 'page review lost'; end if;
end $$;
"""


def run() -> None:
    # Schema-only snapshot includes no keys, credentials, JWTs or real user data.
    schema = docker(
        "pg_dump",
        "-U",
        "supabase_admin",
        "-d",
        "postgres",
        "--schema-only",
        "--no-owner",
        "--no-privileges",
    )
    migration = (
        ROOT / "supabase/migrations/20261016020000_incremental_extraction.sql"
    ).read_text(encoding="utf-8")
    for seeded in (False, True):
        database = f"incremental_test_{uuid4().hex}"
        docker("createdb", "-U", "supabase_admin", "-T", "template0", database)
        try:
            docker(
                "psql",
                "-U",
                "supabase_admin",
                "-d",
                database,
                "-v",
                "ON_ERROR_STOP=1",
                content=schema,
            )
            if seeded:
                sql(database, SEED)
            sql(
                database,
                """insert into storage.buckets(id,name,public,allowed_mime_types)
                values('project-assets','project-assets',false,array['image/png','application/pdf','application/json']);""",
            )
            sql(database, migration)
            sql(
                database,
                """do $$ begin
              if not exists(select 1 from storage.buckets where id='project-assets'
                and 'application/zip'=any(allowed_mime_types) and not public) then
                raise exception 'private Profile package MIME unavailable'; end if;
              end $$;""",
            )
            if not seeded:
                sql(database, SEED)
            create = """begin; select public.start_simple_extraction(
              '33333333-3333-4333-8333-333333333333','11111111-1111-4111-8111-111111111111',
              '44444444-4444-4444-8444-444444444444'); select pg_sleep(0.4); commit;"""
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(sql, database, create) for _ in range(2)]
                for future in futures:
                    assert "QUEUED" in future.result()
            sql(database, CHECK)
            print(
                f"PASS: {'existing synthetic rows' if seeded else 'empty tables'} migration, ownership, lease, replay, stable rows, version fencing, old-batch retention, RPC grants"
            )
        finally:
            # Exact newly generated database name, fixed container; no project DB removal.
            docker("dropdb", "-U", "supabase_admin", database)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allow-local-database-test", required=True, action="store_true"
    )
    parser.parse_args()
    run()
