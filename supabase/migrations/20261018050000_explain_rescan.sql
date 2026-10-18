-- Explain rescan candidates are isolated from business rows until explicit confirmation.
-- Rollback after stopping callers: drop these RPCs, tables and trigger. Confirmed edits are not reversed.
begin;
create table public.connection_rescan_assets(
  id uuid primary key, project_id uuid not null references extraction_projects(id) on delete cascade,
  created_by uuid not null references auth.users(id), conversation_id uuid not null,
  pdf_page_number integer not null check(pdf_page_number>0), role text not null check(role in ('source','target')),
  checksum text not null check(checksum ~ '^sha256:[0-9a-f]{64}$'),
  storage_path text not null, width integer not null check(width>0), height integer not null check(height>0), uploaded boolean not null default false,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index rescan_assets_owner on connection_rescan_assets(project_id,created_by,conversation_id);
create table public.connection_rescan_runs(
  id uuid primary key, project_id uuid not null references extraction_projects(id) on delete cascade,
  created_by uuid not null references auth.users(id), conversation_id uuid not null, batch_id text not null,
  status text not null default 'queued' check(status in ('queued','running','ready','failed','cancelled','applied','rejected')),
  stage text not null default 'queued', request jsonb not null, attachment_ids jsonb not null default '[]',
  profile jsonb not null, project_snapshot jsonb not null, baseline jsonb not null,
  checkpoint jsonb not null default '{}', progress jsonb not null default '{}', versions jsonb not null default '{}',
  candidate jsonb, checksum text, error text, receipt jsonb,
  worker text, lease_token uuid, lease_until timestamptz, attempts integer not null default 0,
  expires_at timestamptz not null default now()+interval '24 hours',
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index rescan_run_claim on connection_rescan_runs(status,lease_until,created_at);
create index rescan_run_owner on connection_rescan_runs(project_id,created_by,conversation_id,created_at desc);
create function public.touch_connection_rescan() returns trigger language plpgsql set search_path=public as $$
begin new.updated_at:=now(); return new; end $$;
create trigger rescan_asset_updated before update on connection_rescan_assets for each row execute function touch_connection_rescan();
create trigger rescan_run_updated before update on connection_rescan_runs for each row execute function touch_connection_rescan();
revoke all on function touch_connection_rescan() from public,anon,authenticated;
alter table connection_rescan_assets enable row level security;
alter table connection_rescan_runs enable row level security;
create policy rescan_assets_read on connection_rescan_assets for select to authenticated using(
 created_by=auth.uid() and exists(select 1 from extraction_projects p where p.id=project_id and p.owner_id=auth.uid()));
create policy rescan_runs_read on connection_rescan_runs for select to authenticated using(
 created_by=auth.uid() and exists(select 1 from extraction_projects p where p.id=project_id and p.owner_id=auth.uid()));
revoke all on connection_rescan_assets,connection_rescan_runs from public,anon,authenticated;
grant select on connection_rescan_assets,connection_rescan_runs to authenticated;
grant all on connection_rescan_assets,connection_rescan_runs to service_role;

create function public.rescan_public(r connection_rescan_runs) returns jsonb language sql immutable as $$
select jsonb_build_object('id',r.id,'project_id',r.project_id,'conversation_id',r.conversation_id,'batch_id',r.batch_id,
 'status',r.status,'stage',r.stage,'request',r.request,'profile',r.profile,'progress',r.progress,
 'versions',r.versions,'candidate',r.candidate,'checksum',r.checksum,'error',r.error,'created_at',r.created_at,'updated_at',r.updated_at)
$$;

create function public.rescan_matches(r extraction_connection_rows, scope jsonb) returns boolean
language sql immutable set search_path=public as $$
select explain_edit_matches(r,scope) and (jsonb_array_length(coalesce(scope->'pdf_page_numbers','[]'))=0
 or exists(select 1 from jsonb_array_elements_text(scope->'pdf_page_numbers') n where n=r.source_pdf_page_number::text))
$$;

create function public.enqueue_connection_rescan(value jsonb) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare p extraction_projects; job connection_rescan_runs; ref extraction_profiles; rows jsonb; pages jsonb;
 actor uuid:=(value->>'actor')::uuid; project uuid:=(value->>'project_id')::uuid; bid text;
 scope jsonb:=value->'request'->'scope'; ids jsonb:=coalesce(value->'attachment_ids','[]'); hist jsonb;
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
 select * into ref from extraction_profiles where id=p.profile_id;
 select r->'evidence'->'profile' into hist from jsonb_array_elements(rows) r where r->'evidence'->'profile'->>'checksum' is not null limit 1;
 if hist is not null then
   if exists(select 1 from jsonb_array_elements(rows) r where r->'evidence'->'profile' is not null
      and r->'evidence'->'profile' is distinct from hist) then raise sqlstate 'PT422' using message='Mixed historical profiles'; end if;
   select * into ref from extraction_profiles where profile_key=hist->>'key' and profile_version=hist->>'version' and checksum=hist->>'checksum' limit 1;
 end if;
 if ref.id is null then raise sqlstate 'PT422' using message='Frozen profile unavailable'; end if;
 insert into connection_rescan_runs(id,project_id,created_by,conversation_id,batch_id,request,attachment_ids,profile,project_snapshot,baseline)
 values((value->>'id')::uuid,project,actor,(value->>'conversation_id')::uuid,bid,value->'request',ids,
 jsonb_build_object('key',ref.profile_key,'version',ref.profile_version,'checksum',ref.checksum),
 jsonb_build_object('pages',p.drawing_index->'pages','scan_pages',pages,'profile_ref',ref.resource_ref,'name',p.name),rows) returning * into job;
 update extraction_projects set updated_at=now() where id=project;
 return rescan_public(job);
end $$;

create function public.claim_connection_rescan(worker_name text) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare job connection_rescan_runs;
begin
 if auth.role() is distinct from 'service_role' then raise sqlstate 'PT403' using message='Worker only'; end if;
 update connection_rescan_runs set status='failed',stage='failed',error='重扫多次中断，请重新发起。',updated_at=now()
 where status='running' and lease_until<now() and attempts>=3;
 select * into job from connection_rescan_runs where status='queued' or (status='running' and lease_until<now() and attempts<3)
 order by created_at for update skip locked limit 1;
 if not found then return null; end if;
 update connection_rescan_runs set status='running',stage='preparing',worker=worker_name,lease_token=gen_random_uuid(),
 lease_until=now()+interval '90 seconds',attempts=attempts+1,updated_at=now() where id=job.id returning * into job;
 return to_jsonb(job);
end $$;

create function public.advance_connection_rescan(value jsonb) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare job connection_rescan_runs; incoming jsonb;
begin
 if auth.role() is distinct from 'service_role' then raise sqlstate 'PT403' using message='Worker only'; end if;
 select * into job from connection_rescan_runs where id=(value->>'id')::uuid for update;
 if not found or job.status<>'running' or job.lease_token is distinct from (value->>'token')::uuid or job.lease_until<now() then
   raise sqlstate 'PT409' using message='Rescan cancelled or lease lost'; end if;
 incoming:=value->'candidate';
 update connection_rescan_runs set stage=coalesce(value->>'stage',stage),
 checkpoint=checkpoint||coalesce(value->'checkpoint','{}'),progress=progress||coalesce(value->'progress','{}'),
 candidate=coalesce(incoming,job.candidate),
 checksum=case when incoming is not null then 'sha256:'||encode(sha256(convert_to(jsonb_build_array(job.id,job.baseline,job.profile,incoming)::text,'UTF8')),'hex') else job.checksum end,
 status=case when incoming is not null then 'ready' when value->>'stage'='failed' then 'failed' else 'running' end,
 error=value->>'error',lease_until=now()+interval '90 seconds',updated_at=now(),expires_at=now()+interval '24 hours'
 where id=job.id returning * into job;
 return rescan_public(job);
end $$;

create function public.decide_connection_rescan(value jsonb) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare job connection_rescan_runs; p extraction_projects; item jsonb; current_rows jsonb; fields jsonb;
 r extraction_connection_rows; changed extraction_connection_rows; receipt jsonb; updated_versions jsonb:='{}'; audit jsonb:='[]'; key text;
 accepted boolean:=(value->>'accepted')::boolean;
begin
 if auth.role() is distinct from 'service_role' then raise sqlstate 'PT403' using message='Server only'; end if;
 select * into p from extraction_projects where id=(value->>'project_id')::uuid for update;
 if not found or p.owner_id::text is distinct from value->>'actor' then raise sqlstate 'PT403' using message='Project owner required'; end if;
 select * into job from connection_rescan_runs where id=(value->>'id')::uuid and project_id=p.id and created_by=p.owner_id for update;
 if not found then raise sqlstate 'PT404' using message='Rescan not found'; end if;
 if value->>'action'='cancel' and job.status in ('queued','running','failed') then
   update connection_rescan_runs set status='cancelled',stage='cancelled',updated_at=now() where id=job.id returning * into job;
   return rescan_public(job);
 end if;
 if accepted is null or value->>'checksum' is distinct from job.checksum then raise sqlstate 'PT409' using message='Candidate checksum changed'; end if;
 if job.status in ('applied','rejected') then
   if (job.status='applied') is distinct from accepted then raise sqlstate 'PT409' using message='Already decided'; end if;
   return rescan_public(job);
 end if;
 if job.status<>'ready' then raise sqlstate 'PT409' using message='Rescan not ready'; end if;
 if accepted then
   if p.status in ('processing','archived') or job.expires_at<now() then raise sqlstate 'PT409' using message='Project busy or candidate expired'; end if;
   if coalesce(p.drawing_index->>'active_batch_id',(select batch_id from extraction_connection_rows where project_id=p.id order by created_at desc,id desc limit 1)) is distinct from job.batch_id
      or p.drawing_index->'pages' is distinct from job.project_snapshot->'pages' then raise sqlstate 'PT409' using message='Batch or drawing index changed'; end if;
   perform 1 from extraction_connection_rows x where x.project_id=p.id and x.batch_id=job.batch_id and rescan_matches(x,job.request->'scope') order by id for update;
   select coalesce(jsonb_agg(to_jsonb(x) order by id),'[]') into current_rows from extraction_connection_rows x
     where x.project_id=p.id and x.batch_id=job.batch_id and rescan_matches(x,job.request->'scope');
   if (select coalesce(jsonb_agg(jsonb_build_object('id',x->'id','version',x->'record_version') order by x->>'id'),'[]') from jsonb_array_elements(current_rows) x)
      is distinct from (select coalesce(jsonb_agg(jsonb_build_object('id',x->'id','version',x->'record_version') order by x->>'id'),'[]') from jsonb_array_elements(job.baseline) x) then
     raise sqlstate 'PT409' using message='Scope or row versions changed'; end if;
   for item in select * from jsonb_array_elements(job.candidate->'changes') loop
     fields:=item->'after';
     for key in select jsonb_object_keys(fields) loop
       if key not in ('principle_number','terminal_strip','start_code','start_description','start_terminal','end_code','end_description','end_terminal',
         'start_terminal_coordinates','end_terminal_coordinates','current_value','remark','target_pdf_page_number','target_drawing_page','is_cross_page','needs_review') then
         raise sqlstate 'PT422' using message='Protected candidate field'; end if;
       if job.request->>'fields'='end' and key not in ('end_code','end_description','end_terminal','end_terminal_coordinates','target_pdf_page_number','target_drawing_page','is_cross_page','needs_review')
         or job.request->>'fields'='start' and key not in ('start_code','start_description','start_terminal','start_terminal_coordinates','needs_review') then
         raise sqlstate 'PT422' using message='Candidate exceeds requested endpoint'; end if;
     end loop;
     for key in select unnest(array['start_terminal_coordinates','end_terminal_coordinates']) loop
       if fields->key is not null and fields->key<>'null'::jsonb and not exists(
         select 1 from jsonb_array_elements(job.project_snapshot->'pages') page where page->'pdf_page_number'=fields->key->'pdf_page_number') then
         raise sqlstate 'PT422' using message='Coordinate page outside project'; end if;
     end loop;
     if fields->>'target_pdf_page_number' is not null and not exists(
       select 1 from jsonb_array_elements(job.project_snapshot->'pages') page where page->'pdf_page_number'=fields->'target_pdf_page_number') then
       raise sqlstate 'PT422' using message='Target page outside project'; end if;
     if item->>'action'='update' then
       select * into r from extraction_connection_rows where id=(item->>'connection_id')::uuid and project_id=p.id;
       if not found or r.record_version<>(item->>'record_version')::integer or not exists(select 1 from jsonb_array_elements(job.baseline) b where b->>'id'=r.id::text) then
         raise sqlstate 'PT409' using message='Candidate row changed'; end if;
       changed:=jsonb_populate_record(r,fields);
       -- A re-read can correct a label at the same pin. Preserve the explicitly revalidated
       -- coordinates instead of letting the legacy stale-coordinate trigger erase them.
       if (fields ? 'start_terminal_coordinates' and changed.start_terminal is distinct from r.start_terminal
           and changed.start_terminal_coordinates is not null and changed.start_terminal_coordinates is not distinct from r.start_terminal_coordinates)
         or (fields ? 'end_terminal_coordinates' and changed.end_terminal is distinct from r.end_terminal
           and changed.end_terminal_coordinates is not null and changed.end_terminal_coordinates is not distinct from r.end_terminal_coordinates) then
         update extraction_connection_rows set start_terminal_coordinates=null,end_terminal_coordinates=null where id=r.id;
       end if;
       update extraction_connection_rows set principle_number=changed.principle_number,terminal_strip=changed.terminal_strip,
         start_code=changed.start_code,start_description=changed.start_description,start_terminal=changed.start_terminal,
         end_code=changed.end_code,end_description=changed.end_description,end_terminal=changed.end_terminal,
         start_terminal_coordinates=changed.start_terminal_coordinates,end_terminal_coordinates=changed.end_terminal_coordinates,
         target_pdf_page_number=changed.target_pdf_page_number,target_drawing_page=changed.target_drawing_page,is_cross_page=changed.is_cross_page,
         current_value=changed.current_value,remark=changed.remark,needs_review=changed.needs_review,
         evidence=coalesce(r.evidence,'{}')||jsonb_build_object('processing_status','completed','review_reasons',coalesce(item->'evidence'->'review_reasons','[]'),
           'rescan',jsonb_build_object('run_id',job.id,'profile',job.profile,
           'attachments',job.attachment_ids,'evidence',item->'evidence','time',now())) where id=r.id returning * into changed;
     elsif item->>'action'='insert' then
       if job.request->>'fields'<>'all' or jsonb_array_length(coalesce(job.request->'scope'->'connection_ids','[]'))>0 then raise sqlstate 'PT422' using message='Insert outside full-page rescan'; end if;
       if not exists(select 1 from jsonb_array_elements(job.project_snapshot->'scan_pages') page where page->'pdf_page_number'=item->'source_pdf_page_number'
          and page->>'drawing_page' is not distinct from item->>'source_drawing_page' and page->>'workspace_code' is not distinct from item->>'workspace_code') then
         raise sqlstate 'PT422' using message='Insert origin outside scope'; end if;
       r:=null; r.id:=(item->>'connection_id')::uuid; r.project_id:=p.id; r.batch_id:=job.batch_id;
       r.page_item_id:='rescan:'||job.id::text||':'||r.id::text;
       r.source_pdf_page_number:=(item->>'source_pdf_page_number')::integer; r.source_drawing_page:=item->>'source_drawing_page'; r.workspace_code:=item->>'workspace_code';
       select coalesce(max(row_order),-1)+1 into r.row_order from extraction_connection_rows where project_id=p.id and batch_id=job.batch_id and source_pdf_page_number=r.source_pdf_page_number;
       r.record_version:=1; r.created_at:=now(); r.updated_at:=now(); r.is_cross_page:=false; r.needs_review:=true;
       r.evidence:=jsonb_build_object('profile',job.profile,'rescan',jsonb_build_object('run_id',job.id,'attachments',job.attachment_ids,'evidence',item->'evidence'));
       changed:=jsonb_populate_record(r,fields);
       insert into extraction_connection_rows select changed.* returning * into changed;
     else raise sqlstate 'PT422' using message='Invalid candidate operation'; end if;
     audit:=audit||jsonb_build_array(jsonb_build_object('action','rescan','actor',p.owner_id,'time',now(),'before',case when item->>'action'='update' then to_jsonb(r) else null end,'after',to_jsonb(changed)));
     updated_versions:=updated_versions||jsonb_build_object(changed.id::text,changed.record_version);
   end loop;
   update extraction_projects set drawing_index=jsonb_set(drawing_index,'{management}',coalesce(drawing_index->'management','{}')||
     jsonb_build_object('audit',coalesce(drawing_index->'management'->'audit','[]')||audit)),updated_at=now() where id=p.id;
 end if;
 update connection_rescan_runs set status=case when accepted then 'applied' else 'rejected' end,stage='finished',
 versions=updated_versions,receipt=jsonb_build_object('versions',updated_versions),updated_at=now() where id=job.id returning * into job;
 return rescan_public(job);
end $$;

create function public.remove_rescan_row_copies() returns trigger
language plpgsql security definer set search_path=public,pg_temp as $$
begin
 delete from connection_rescan_runs job where job.project_id=old.project_id and
 (exists(select 1 from jsonb_array_elements(job.baseline) item where item->>'id'=old.id::text)
  or exists(select 1 from jsonb_array_elements(coalesce(job.candidate->'changes','[]')) item where item->>'connection_id'=old.id::text));
 return old;
end $$;
create trigger remove_rescan_row_copies after delete on extraction_connection_rows for each row execute function remove_rescan_row_copies();
revoke all on function remove_rescan_row_copies() from public,anon,authenticated;
revoke all on function rescan_public(connection_rescan_runs),rescan_matches(extraction_connection_rows,jsonb),enqueue_connection_rescan(jsonb),claim_connection_rescan(text),advance_connection_rescan(jsonb),decide_connection_rescan(jsonb) from public,anon,authenticated;
grant execute on function enqueue_connection_rescan(jsonb),claim_connection_rescan(text),advance_connection_rescan(jsonb),decide_connection_rescan(jsonb) to service_role;
notify pgrst,'reload schema';
commit;
