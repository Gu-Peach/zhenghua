-- User explicitly authorized discarding these old business tables on 2026-10-14.
-- Irreversible: old business rows are deleted without data migration.
-- Requires 20261014000000 first. Preserves Agent/Auth/Storage rows and new tables.
-- Application APIs/RPCs still require adaptation; this is not an app rollout.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '90s';

do $$
begin
  if to_regclass('public.extraction_profiles') is null
     or to_regclass('public.extraction_projects') is null
     or to_regclass('public.extraction_connection_rows') is null then
    raise exception 'Create the three new extraction tables before retiring old business tables';
  end if;
end;
$$;

-- Snapshot retained rows inside this transaction, and prevent concurrent changes.
lock table public.agent_artifacts, public.agent_checkpoints, public.agent_events,
  public.agent_run_queue, public.agent_runs, public.agent_traces,
  auth.users, storage.objects in share mode;
create temporary table retained_extraction_cleanup_state (
  relation_name text primary key,
  row_count bigint not null,
  content_hash text not null
) on commit drop;

do $$
declare relation_name text; row_count bigint; content_hash text;
begin
  foreach relation_name in array array[
    'public.agent_artifacts','public.agent_checkpoints','public.agent_events',
    'public.agent_run_queue','public.agent_runs','public.agent_traces',
    'auth.users','storage.objects'
  ] loop
    execute format(
      'select count(*), md5(coalesce(string_agg(to_jsonb(t)::text, chr(10) order by to_jsonb(t)::text), '''')) from %s t',
      relation_name::regclass
    ) into row_count, content_hash;
    insert into retained_extraction_cleanup_state values (relation_name,row_count,content_hash);
  end loop;
end;
$$;

-- Preserve the Agent rows, including their old UUIDs, rather than cascade-delete them.
alter table public.agent_runs drop constraint if exists agent_runs_project_id_fkey;
alter table public.agent_runs drop constraint if exists agent_runs_source_document_project_fk;
alter table public.agent_traces drop constraint if exists agent_traces_project_id_fkey;

-- Keep existing Agent read policies functional; old project UUIDs do not grant access.
create or replace function public.is_project_member(target_project_id uuid)
returns boolean language sql stable security definer
set search_path = public, pg_temp as $$
  select exists (
    select 1 from public.extraction_projects project
    where project.id = target_project_id and project.owner_id = auth.uid()
  );
$$;

drop policy if exists project_assets_member_read on storage.objects;
create policy extraction_project_assets_owner_read on storage.objects
  for select to authenticated using (
    bucket_id = 'project-assets'
    and (storage.foldername(name))[1] = 'projects'
    and exists (
      select 1 from public.extraction_projects project
      where project.id::text = (storage.foldername(objects.name))[2]
        and project.owner_id = (select auth.uid())
    )
  );

drop view if exists public.wiring_connection_rows restrict;
drop table if exists
  public.connection_evidence,
  public.document_files,
  public.drawings,
  public.evaluation_reports,
  public.feedback_items,
  public.profile_candidate_audit,
  public.profile_candidate_reviews,
  public.profile_candidates,
  public.profile_resource_packages,
  public.project_members,
  public.projects,
  public.result_proposals,
  public.result_versions,
  public.result_wire_number_counters,
  public.wiring_connections,
  public.wiring_tables,
  public.wiring_units,
  public.workspaces
restrict;

-- Abort all changes if any retained row changed. No raw row contents are printed.
do $$
declare saved record; row_count bigint; content_hash text;
begin
  for saved in select * from retained_extraction_cleanup_state loop
    execute format(
      'select count(*), md5(coalesce(string_agg(to_jsonb(t)::text, chr(10) order by to_jsonb(t)::text), '''')) from %s t',
      saved.relation_name::regclass
    ) into row_count, content_hash;
    if row_count <> saved.row_count or content_hash <> saved.content_hash then
      raise exception 'Retained data changed: %', saved.relation_name;
    end if;
  end loop;
end;
$$;
select relation_name, row_count, 'unchanged' as retained_data
from retained_extraction_cleanup_state order by relation_name;

notify pgrst, 'reload schema';
commit;
