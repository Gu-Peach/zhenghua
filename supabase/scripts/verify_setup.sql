-- Read-only installation diagnostics. Does not inspect user rows or secrets.
begin transaction read only;

with expected(name) as (values
  ('extraction_profiles'), ('extraction_projects'), ('extraction_connection_rows'),
  ('agent_runs'), ('agent_events'), ('agent_artifacts'), ('agent_checkpoints'),
  ('agent_run_queue'), ('agent_traces'), ('connection_edit_proposals'),
  ('connection_rescan_runs'), ('connection_rescan_assets'), ('profile_asset_gc'),
  ('assistant_conversations'), ('assistant_turns'), ('assistant_actions'),
  ('assistant_attachments'), ('assistant_asset_gc')
)
select e.name as table_name, c.oid is not null as present,
       coalesce(c.relrowsecurity, false) as rls_enabled
from expected e
left join pg_class c on c.oid = to_regclass('public.' || e.name)
order by e.name;

with expected(signature) as (values
  ('public.start_simple_extraction(uuid,uuid,uuid,boolean)'),
  ('public.claim_simple_extraction(text)'),
  ('public.renew_simple_extraction(uuid,text,text)'),
  ('public.commit_simple_extraction(uuid,text,text,text,jsonb)'),
  ('public.publish_extraction_profile(uuid,text,text,text,text,text)'),
  ('public.claim_connection_rescan(text)'),
  ('public.review_extraction_scope(jsonb)')
)
select signature, to_regprocedure(signature) is not null as present
from expected order by signature;

with expected(id) as (values ('project-assets'), ('agent-profile-assets'))
select e.id, b.id is not null as present, b.public, b.file_size_limit, b.allowed_mime_types,
       coalesce(not b.public and (
         e.id <> 'project-assets' or (
           (b.file_size_limit is null or b.file_size_limit >= 524288000)
           and (b.allowed_mime_types is null or b.allowed_mime_types @> array[
             'application/pdf', 'image/png', 'image/jpeg', 'application/json',
             'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
             'application/zip'
           ]::text[])
         )
       ), false) as configuration_ok
from expected e left join storage.buckets b on b.id = e.id
order by e.id;

-- Report history only if CLI has created the tracking table; never repair it here.
do $$
declare migration_count bigint; latest_version text;
begin
  if to_regclass('supabase_migrations.schema_migrations') is null then
    raise notice 'Migration history missing: reconcile manual deployments before using CLI migrations.';
  else
    execute 'select count(*), max(version) from supabase_migrations.schema_migrations'
      into migration_count, latest_version;
    raise notice 'recorded_migration_count=%, latest_version=%', migration_count, latest_version;
  end if;
end;
$$;

commit;
