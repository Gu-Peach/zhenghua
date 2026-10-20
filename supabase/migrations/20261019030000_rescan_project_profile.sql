-- Explicit project opt-in only. Old jobs and batch packages remain immutable.
begin;

create or replace function public.enqueue_connection_rescan(value jsonb) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare p extraction_projects; job connection_rescan_runs; ref extraction_profiles; rows jsonb; pages jsonb;
 actor uuid:=(value->>'actor')::uuid; project uuid:=(value->>'project_id')::uuid; bid text;
 scope jsonb:=value->'request'->'scope'; ids jsonb:=coalesce(value->'attachment_ids','[]'); hist jsonb;
 profile_source text;
begin
 if auth.role() is distinct from 'service_role' then raise sqlstate 'PT403' using message='Internal rescan only'; end if;
 select * into p from extraction_projects where id=project for update;
 if not found or p.owner_id is distinct from actor then raise sqlstate 'PT403' using message='Project owner required'; end if;
 if p.status in ('processing','archived') then raise sqlstate 'PT409' using message='Project not editable'; end if;
 bid:=coalesce(p.drawing_index->>'active_batch_id',(select batch_id from extraction_connection_rows where project_id=project order by created_at desc,id desc limit 1));
 if bid is null or bid is distinct from value->>'batch_id' then raise sqlstate 'PT409' using message='Active batch changed'; end if;
 if jsonb_typeof(scope) is distinct from 'object' or not (
   nullif(scope->>'workspace_code','') is not null or nullif(scope->>'drawing_page','') is not null
   or jsonb_array_length(coalesce(scope->'connection_ids','[]'))>0 or jsonb_array_length(coalesce(scope->'principle_numbers','[]'))>0
   or jsonb_array_length(coalesce(scope->'pdf_page_numbers','[]'))>0)
   or value->'request'->>'fields' not in ('all','start','end') then raise sqlstate 'PT422' using message='Exact rescan scope required'; end if;
 select * into job from connection_rescan_runs where id=(value->>'id')::uuid;
 if found then
   if job.project_id<>project or job.created_by<>actor or job.batch_id<>bid
     or job.request is distinct from value->'request' or job.conversation_id::text<>value->>'conversation_id'
     or job.attachment_ids is distinct from ids then raise sqlstate 'PT409' using message='Rescan id reused'; end if;
   return rescan_public(job);
 end if;
 if jsonb_typeof(ids)<>'array' or jsonb_array_length(ids)>6 or exists(
   select 1 from jsonb_array_elements_text(ids) i where not exists(select 1 from connection_rescan_assets a
    where a.id::text=i and a.project_id=project and a.created_by=actor and a.uploaded and a.conversation_id::text=enqueue_connection_rescan.value->>'conversation_id')) then
   raise sqlstate 'PT403' using message='Attachment outside conversation'; end if;
 select coalesce(jsonb_agg(to_jsonb(r) order by id),'[]') into rows from extraction_connection_rows r
   where r.project_id=project and r.batch_id=bid and rescan_matches(r,scope);
 if jsonb_array_length(rows)>1000 then raise sqlstate 'PT422' using message='Rescan scope exceeds 1000 rows'; end if;
 if jsonb_array_length(coalesce(scope->'connection_ids','[]'))>0 and jsonb_array_length(rows)<>jsonb_array_length(scope->'connection_ids') then
   raise sqlstate 'PT409' using message='Selected rows changed'; end if;
 select coalesce(jsonb_agg(page),'[]') into pages from jsonb_array_elements(coalesce(p.drawing_index->'pages','[]')) page
 where (nullif(scope->>'workspace_code','') is null or page->>'workspace_code'=scope->>'workspace_code')
 and (nullif(scope->>'drawing_page','') is null or page->>'drawing_page'=scope->>'drawing_page')
 and (jsonb_array_length(coalesce(scope->'pdf_page_numbers','[]'))=0 or exists(select 1 from jsonb_array_elements_text(scope->'pdf_page_numbers') n where n=page->>'pdf_page_number'))
 and (jsonb_array_length(coalesce(scope->'connection_ids','[]'))=0 and jsonb_array_length(coalesce(scope->'principle_numbers','[]'))=0
   or exists(select 1 from jsonb_array_elements(rows) r where r->'source_pdf_page_number'=page->'pdf_page_number'));
 if jsonb_array_length(pages)=0 then raise sqlstate 'PT422' using message='No indexed pages in scope'; end if;
 select * into ref from extraction_profiles where id=p.profile_id for share;
 profile_source:=case when p.drawing_index->>'rescan_profile_source'='project_reference' then 'project_reference' else 'historical' end;
 if profile_source='project_reference' then
   if ref.id is null or ref.checksum !~ '^sha256:[0-9a-f]{64}$'
      or ref.resource_ref !~ '^storage://project-assets/profiles/[0-9a-f-]{36}/'
      or ref.resource_ref <> 'storage://project-assets/profiles/'||split_part(ref.resource_ref,'/',5)||'/'||ref.profile_key||'/'||ref.profile_version||'/'||substring(ref.checksum from 8)||'.zip' then
     raise sqlstate 'PT422' using message='Selected rescan profile requires published package';
   end if;
 else
   select r->'evidence'->'profile' into hist from jsonb_array_elements(rows) r where r->'evidence'->'profile'->>'checksum' is not null limit 1;
   if hist is not null then
     if exists(select 1 from jsonb_array_elements(rows) r where r->'evidence'->'profile' is not null
        and r->'evidence'->'profile' is distinct from hist) then raise sqlstate 'PT422' using message='Mixed historical profiles'; end if;
     select * into ref from extraction_profiles where profile_key=hist->>'key' and profile_version=hist->>'version' and checksum=hist->>'checksum' limit 1;
   end if;
 end if;
 if ref.id is null then raise sqlstate 'PT422' using message='Frozen profile unavailable'; end if;
 insert into connection_rescan_runs(id,project_id,created_by,conversation_id,batch_id,request,attachment_ids,profile,project_snapshot,baseline)
 values((value->>'id')::uuid,project,actor,(value->>'conversation_id')::uuid,bid,value->'request',ids,
 jsonb_build_object('key',ref.profile_key,'version',ref.profile_version,'checksum',ref.checksum),
 jsonb_build_object('pages',p.drawing_index->'pages','scan_pages',pages,'profile_ref',ref.resource_ref,
   'profile_source',profile_source,'profile_id',ref.id,'name',p.name),rows) returning * into job;
 update extraction_projects set updated_at=now() where id=project;
 return rescan_public(job);
end $$;

-- A task-pinned package must remain available even after the project selects another version.
create or replace function public.profile_version_in_use(target uuid) returns boolean
language plpgsql security definer set search_path=public as $$
declare p public.extraction_profiles; active boolean := false;
begin
  if exists(select 1 from public.extraction_projects where profile_id=target) then return true; end if;
  select * into p from public.extraction_profiles where id=target;
  if not found then return false; end if;
  if exists(select 1 from public.connection_rescan_runs where project_snapshot->>'profile_ref'=p.resource_ref) then return true; end if;
  if to_regclass('public.agent_runs') is not null then
    execute 'select exists(select 1 from public.agent_runs where status::text in (''QUEUED'',''RUNNING'',''WAITING_INPUT'',''FAILED'') and profile->>''key''=$1 and profile->>''version''=$2 and profile->>''checksum''=$3)'
    into active using p.profile_key,p.profile_version,p.checksum;
  end if;
  return active;
end $$;
revoke all on function public.profile_version_in_use(uuid) from public,anon,authenticated;
grant execute on function public.profile_version_in_use(uuid) to service_role;

commit;
