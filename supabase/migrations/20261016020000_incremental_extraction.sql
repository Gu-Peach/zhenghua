-- Incremental extraction uses the existing three business tables and agent_* tables.
-- Rollback in a new migration: stop these Workers; restore prior gate_a_guard and
-- manage_extraction_connection definitions; drop the four new RPCs and claim index.
-- Existing completed results are retained. No old business tables/RPCs are restored.
begin;

-- Frozen rule packages share the existing private project bucket.
update storage.buckets set allowed_mime_types=array(
  select distinct unnest(allowed_mime_types||array['application/zip']))
  where id='project-assets' and allowed_mime_types is not null;

create index agent_runs_simple_claim_idx on public.agent_runs(status,created_at,id)
  where options->>'workflow'='simple_extraction_v1';
create unique index agent_runs_simple_active_project_idx on public.agent_runs(project_id)
  where options->>'workflow'='simple_extraction_v1' and status in ('QUEUED','RUNNING','WAITING_INPUT');

-- Retain legacy protocol fencing while routing the new workflow around retired business tables.
create or replace function public.gate_a_guard() returns trigger
language plpgsql security definer set search_path=public,pg_temp as $$
declare rid uuid; version integer; generation bigint; state text; project uuid; workflow text;
begin
  if tg_table_name='agent_runs' then rid:=new.id;
  elsif tg_table_name='result_versions' then
    begin rid:=new.agent_run_id::uuid; exception when invalid_text_representation then return new; end;
  else rid:=new.agent_run_id; end if;
  select protocol_version,lease_generation,status,project_id,options->>'workflow'
    into version,generation,state,project,workflow from public.agent_runs where id=rid;
  if version=1 and workflow='simple_extraction_v1' then return new; end if;
  if current_setting('gate_a.deleting_project',true)=project::text then return new; end if;
  if project is not null and not exists(select 1 from public.projects where id=project) then return new; end if;
  if version=2 and current_setting('gate_a.authorized',true) is distinct from rid::text then
    if tg_table_name='agent_events' then
      if new.event_type='RUN_CREATED' and generation=0 and state='QUEUED' then return new; end if;
    end if;
    raise exception 'protocol 2 requires fenced mutation' using errcode='42501';
  end if;
  return new;
end $$;

create function public.start_simple_extraction(project uuid, actor uuid, requested_run uuid, retry boolean default false)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare p public.extraction_projects; r public.agent_runs; profile_row public.extraction_profiles; progress jsonb;
begin
  -- Serialize concurrent retries before checking an as-yet-uncreated stable run ID.
  perform pg_advisory_xact_lock(hashtextextended('simple-extraction:'||requested_run::text,0));
  select * into r from public.agent_runs where id=requested_run for update;
  select * into p from public.extraction_projects where id=project for update;
  if not found or actor is null or p.owner_id is distinct from actor then raise sqlstate 'PT403' using message='Project access denied'; end if;
  if p.status='archived' or p.drawing_index->>'upload_state' is distinct from 'saved' then
    raise sqlstate 'PT409' using message='Source is not available';
  end if;
  if r.id is not null then
    if r.project_id<>project or r.requested_by<>actor or r.options->>'workflow'<>'simple_extraction_v1' then
      raise sqlstate 'PT409' using message='Run identity conflict';
    end if;
    if not retry or r.status<>'FAILED' then return jsonb_build_object('run_id',r.id,'status',r.status); end if;
    update public.agent_runs set status='QUEUED',error=null,options=options-'simple_lease',updated_at=now() where id=r.id;
  else
    if exists(select 1 from public.agent_runs where project_id=project and status in ('QUEUED','RUNNING','WAITING_INPUT')) then
      raise sqlstate 'PT409' using message='Project already has an active run';
    end if;
    select * into profile_row from public.extraction_profiles where id=p.profile_id;
    insert into public.agent_runs(id,idempotency_key,request_fingerprint,run_type,status,project_id,
      source_document_id,requested_by,scope,options,profile,protocol_version)
    values(requested_run,'simple:'||requested_run::text,p.drawing_index->'source'->>'checksum',
      'FULL_EXTRACTION','QUEUED',project,project,actor,jsonb_build_object('type','PROJECT','id',project),
      jsonb_build_object('workflow','simple_extraction_v1','source_checksum',p.drawing_index->'source'->>'checksum'),
      jsonb_build_object('key',profile_row.profile_key,'version',profile_row.profile_version,'checksum',profile_row.checksum),1);
  end if;
  -- No agent_run_queue row: legacy queue consumers must not claim this workflow.
  progress:=coalesce(p.drawing_index->'processing','{}'::jsonb)||jsonb_build_object(
    'run_id',requested_run,'stage','queued','total_pages',coalesce((p.drawing_index->'source'->>'page_count')::int,0),
    'error',null);
  update public.extraction_projects set status='processing',drawing_index=p.drawing_index||jsonb_build_object(
    'active_batch_id',requested_run::text,'processing',progress) where id=project;
  return jsonb_build_object('run_id',requested_run,'status','QUEUED');
end $$;

create function public.claim_simple_extraction(worker text) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare r public.agent_runs; p public.extraction_projects; lease jsonb; profile_row public.extraction_profiles;
begin
  select * into r from public.agent_runs where options->>'workflow'='simple_extraction_v1'
    and (status='QUEUED' or (status='RUNNING' and coalesce((options->'simple_lease'->>'expires_at')::timestamptz,'-infinity')<now()))
    order by created_at,id for update skip locked limit 1;
  if not found then return null; end if;
  select * into p from public.extraction_projects where id=r.project_id for update;
  if not found or p.status='archived' or p.owner_id<>r.requested_by then
    update public.agent_runs set status='CANCELLED',updated_at=now() where id=r.id;
    return null;
  end if;
  lease:=jsonb_build_object('worker',worker,'token',gen_random_uuid(),'expires_at',now()+interval '120 seconds');
  update public.agent_runs set status='RUNNING',options=options||jsonb_build_object('simple_lease',lease),updated_at=now()
    where id=r.id returning * into r;
  select * into profile_row from public.extraction_profiles where id=p.profile_id;
  return jsonb_build_object('run',to_jsonb(r),'project',to_jsonb(p),'profile',to_jsonb(profile_row),'lease',lease);
end $$;

create function public.renew_simple_extraction(run uuid, worker text, token text) returns boolean
language plpgsql security definer set search_path=public,pg_temp as $$
begin
  update public.agent_runs set options=jsonb_set(options,'{simple_lease,expires_at}',to_jsonb(now()+interval '120 seconds')),
    updated_at=now() where id=run and status='RUNNING' and options->>'workflow'='simple_extraction_v1'
    and options->'simple_lease'->>'worker'=worker and options->'simple_lease'->>'token'=token
    and (options->'simple_lease'->>'expires_at')::timestamptz>now();
  return found;
end $$;

create function public.commit_simple_extraction(run uuid, worker text, token text, item_key text, value jsonb)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare r public.agent_runs; p public.extraction_projects; old public.extraction_connection_rows;
  row_value public.extraction_connection_rows; entry jsonb; pages jsonb; progress jsonb; prior jsonb;
  aid text; event_seq integer; total integer; kind text; page_number integer; review_count integer;
begin
  select * into r from public.agent_runs where id=run for update;
  if not found or r.options->>'workflow' is distinct from 'simple_extraction_v1'
    or worker is null or token is null
    or r.options->'simple_lease'->>'worker' is distinct from worker
    or r.options->'simple_lease'->>'token' is distinct from token then
    raise sqlstate 'PT409' using message='Extraction lease expired or replaced';
  end if;
  select * into p from public.extraction_projects where id=r.project_id for update;
  if not found or p.status='archived' or p.owner_id<>r.requested_by then
    raise sqlstate 'PT409' using message='Project is unavailable';
  end if;
  aid:='simple:'||run::text||':'||item_key;
  select payload into prior from public.agent_artifacts where artifact_id=aid;
  if prior is not null then
    if prior<>value then raise sqlstate 'PT409' using message='Step payload changed'; end if;
    return jsonb_build_object('idempotent',true,'payload',prior);
  end if;
  if r.status<>'RUNNING' or r.options->'simple_lease'->>'expires_at' is null
    or (r.options->'simple_lease'->>'expires_at')::timestamptz<=now() then
    raise sqlstate 'PT409' using message='Extraction lease expired or replaced';
  end if;
  kind:=value->>'kind';
  if kind is null or kind not in ('rendered','classified','scan','completion','page_completed','finished','failed','cache') then
    raise sqlstate 'PT422' using message='Invalid extraction step';
  end if;
  total:=(p.drawing_index->'source'->>'page_count')::int;
  page_number:=coalesce((value->'page'->>'pdf_page_number')::int,(value->>'pdf_page_number')::int);
  if page_number is not null and (page_number<1 or page_number>total) then
    raise sqlstate 'PT422' using message='Invalid physical page';
  end if;
  for entry in select * from jsonb_array_elements(coalesce(value->'rows','[]'::jsonb)) loop
    row_value:=jsonb_populate_record(null::public.extraction_connection_rows,entry);
    if row_value.project_id is distinct from p.id or row_value.batch_id is distinct from run::text
      or row_value.source_pdf_page_number is distinct from page_number
      or row_value.target_pdf_page_number>total or row_value.source_pdf_page_number<1 then
      raise sqlstate 'PT422' using message='Row scope does not match extraction step';
    end if;
    select * into old from public.extraction_connection_rows where project_id=p.id and batch_id=run::text
      and source_pdf_page_number=page_number and page_item_id=row_value.page_item_id for update;
    if found then
      if old.id<>row_value.id or old.record_version<>coalesce((old.evidence->>'agent_record_version')::int,old.record_version) then
        raise sqlstate 'PT409' using message='Extraction row has changed';
      end if;
      row_value.evidence:=row_value.evidence||jsonb_build_object('agent_record_version',old.record_version);
      if (to_jsonb(old)-array['record_version','created_at','updated_at'])=
         (to_jsonb(row_value)-array['record_version','created_at','updated_at']) then continue; end if;
      row_value.record_version:=old.record_version+1;
      row_value.evidence:=row_value.evidence||jsonb_build_object('agent_record_version',row_value.record_version);
      update public.extraction_connection_rows set
        row_order=row_value.row_order,workspace_code=row_value.workspace_code,source_drawing_page=row_value.source_drawing_page,
        target_drawing_page=row_value.target_drawing_page,target_pdf_page_number=row_value.target_pdf_page_number,
        wire_number=row_value.wire_number,principle_number=row_value.principle_number,terminal_strip=row_value.terminal_strip,
        start_code=row_value.start_code,start_description=row_value.start_description,start_terminal=row_value.start_terminal,
        end_code=row_value.end_code,end_description=row_value.end_description,end_terminal=row_value.end_terminal,
        current_value=row_value.current_value,color_mark=row_value.color_mark,remark=row_value.remark,
        is_cross_page=row_value.is_cross_page,needs_review=row_value.needs_review,evidence=row_value.evidence,
        start_terminal_coordinates=row_value.start_terminal_coordinates,end_terminal_coordinates=row_value.end_terminal_coordinates
        where id=old.id;
    else
      row_value.record_version:=1; row_value.created_at:=now(); row_value.updated_at:=now();
      row_value.evidence:=row_value.evidence||jsonb_build_object('agent_record_version',1);
      insert into public.extraction_connection_rows select row_value.*;
    end if;
  end loop;
  if kind='page_completed' then
    if exists(select 1 from public.extraction_connection_rows where project_id=p.id and batch_id=run::text
      and source_pdf_page_number=page_number and record_version<>coalesce((evidence->>'agent_record_version')::int,record_version)) then
      raise sqlstate 'PT409' using message='Extraction page has manual changes';
    end if;
    delete from public.extraction_connection_rows where project_id=p.id and batch_id=run::text
      and source_pdf_page_number=page_number and not exists(
        select 1 from jsonb_array_elements(value->'rows') v where v->>'page_item_id'=page_item_id);
  end if;
  insert into public.agent_artifacts(artifact_id,agent_run_id,kind,payload,checksum)
    values(aid,run,'simple_extraction_step',value,'md5:'||md5(value::text));
  if kind='cache' then return jsonb_build_object('idempotent',false); end if;
  pages:=coalesce(p.drawing_index->'pages','[]'::jsonb);
  if value ? 'page' then
    select coalesce(jsonb_agg(v order by (v->>'pdf_page_number')::int),'[]'::jsonb) into pages from (
      select v from jsonb_array_elements(pages) v where (v->>'pdf_page_number')::int<>page_number
      union all select value->'page'
    ) entries;
  end if;
  select count(*) filter(where needs_review) into review_count from public.extraction_connection_rows
    where project_id=p.id and batch_id=run::text;
  progress:=coalesce(p.drawing_index->'processing','{}'::jsonb)||jsonb_build_object(
    'run_id',run,'stage',value->>'stage','total_pages',total,
    'rendered_pages',(select count(*) from jsonb_array_elements(pages) v where v->>'image_path' is not null),
    'classified_pages',(select count(*) from jsonb_array_elements(pages) v where v->>'status'<>'rendered'),
    'completed_pages',(select count(*) from jsonb_array_elements(pages) v where v->>'status' in ('completed','needs_review','skipped')),
    'row_count',(select count(*) from public.extraction_connection_rows where project_id=p.id and batch_id=run::text),
    'needs_review_count',review_count,'current_page',page_number,'error',value->'error');
  update public.extraction_projects set drawing_index=drawing_index||jsonb_build_object('pages',pages,'processing',progress),
    status=case kind when 'finished' then 'ready' when 'failed' then 'failed' else 'processing' end where id=p.id;
  update public.agent_runs set current_stage=value->>'stage',updated_at=now(),
    status=case kind when 'finished' then case when review_count>0 or exists(
      select 1 from jsonb_array_elements(pages) v where v->>'status'='needs_review') then 'NEEDS_REVIEW' else 'SUCCEEDED' end
      when 'failed' then 'FAILED' else 'RUNNING' end,error=value->'error' where id=run;
  select coalesce(max(seq),-1)+1 into event_seq from public.agent_events where agent_run_id=run;
  insert into public.agent_events(id,agent_run_id,seq,event_type,stage,message,metrics)
    values(gen_random_uuid(),run,event_seq,'EXTRACTION_STEP',value->>'stage',kind,progress);
  return jsonb_build_object('idempotent',false,'seq',event_seq);
end $$;

revoke all on function public.start_simple_extraction(uuid,uuid,uuid,boolean) from public,anon,authenticated;
revoke all on function public.claim_simple_extraction(text) from public,anon,authenticated;
revoke all on function public.renew_simple_extraction(uuid,text,text) from public,anon,authenticated;
revoke all on function public.commit_simple_extraction(uuid,text,text,text,jsonb) from public,anon,authenticated;
grant execute on function public.start_simple_extraction(uuid,uuid,uuid,boolean) to service_role;
grant execute on function public.claim_simple_extraction(text) to service_role;
grant execute on function public.renew_simple_extraction(uuid,text,text) to service_role;
grant execute on function public.commit_simple_extraction(uuid,text,text,text,jsonb) to service_role;
create or replace function public.manage_extraction_connection(value jsonb) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
declare
  p public.extraction_projects;
  r public.extraction_connection_rows;
  changed public.extraction_connection_rows;
  actor uuid := (value->>'actor')::uuid;
  project uuid := (value->>'project_id')::uuid;
  action text := value->>'action';
  key text := value->>'key';
  body jsonb := value->'body';
  fields jsonb;
  saved jsonb;
  receipt jsonb;
  before_value jsonb := 'null'::jsonb;
  after_value jsonb := 'null'::jsonb;
  management jsonb;
  field_name text;
begin
  if auth.role() is distinct from 'service_role' then
    raise sqlstate 'PT403' using message='Internal row management only';
  end if;
  select * into p from public.extraction_projects where id=project for update;
  if not found then raise sqlstate 'PT404' using message='Project not found'; end if;
  if actor is null or p.owner_id <> actor then
    raise sqlstate 'PT403' using message='Project owner required';
  end if;
  if p.status='processing' then raise sqlstate 'PT409' using message='Extraction results are read only while processing'; end if;
  if p.status='archived' then raise sqlstate 'PT409' using message='Project archived'; end if;
  if key is null or length(key) not between 1 and 200 or action not in ('add','edit','remove') then
    raise sqlstate 'PT422' using message='Invalid management request';
  end if;
  management := coalesce(p.drawing_index->'management','{}'::jsonb);
  saved := management->'receipts'->key;
  if saved is not null then
    if saved->'request' is distinct from value then
      raise sqlstate 'PT409' using message='Idempotency key reused with different input';
    end if;
    return (saved->'receipt') || '{"idempotent":true}'::jsonb;
  end if;
  if action in ('edit','remove') then
    select * into r from public.extraction_connection_rows
      where id=(value->>'connection_id')::uuid and project_id=project for update;
    if not found then raise sqlstate 'PT404' using message='Connection not found'; end if;
    if r.record_version is distinct from (body->>'record_version')::integer then
      raise sqlstate 'PT409' using message='Record version changed';
    end if;
    before_value := to_jsonb(r);
  end if;
  if action='remove' then
    if body->>'confirmed' is distinct from 'true' then
      raise sqlstate 'PT422' using message='Deletion confirmation required';
    end if;
    delete from public.extraction_connection_rows where id=r.id;
    changed := r;
  else
    fields := coalesce(case when action='edit' then body->'changes' else body->'fields' end,'{}'::jsonb);
    if jsonb_typeof(fields)<>'object' then raise sqlstate 'PT422' using message='Invalid fields'; end if;
    for field_name in select jsonb_object_keys(fields) loop
      if field_name not in ('voltage_level','terminal_strip','principle_number','start_code',
        'start_description','start_terminal','end_code','end_description','end_terminal',
        'current_value','remark','color_mark','is_cross_page') then
        raise sqlstate 'PT422' using message='Unsupported connection field';
      end if;
    end loop;
    if action='add' then
      if nullif(btrim(fields->>'start_terminal'),'') is null
         or nullif(btrim(body->>'batch_id'),'') is null
         or not exists(select 1 from jsonb_array_elements(coalesce(p.drawing_index->'pages','[]')) page
           where (page->>'pdf_page_number')::integer=(body->'source'->>'pdf_page_number')::integer) then
        raise sqlstate 'PT422' using message='Source page and start terminal required';
      end if;
      r.id := gen_random_uuid(); r.project_id := project; r.batch_id := body->>'batch_id';
      r.page_item_id := 'manual:' || r.id::text;
      r.source_pdf_page_number := (body->'source'->>'pdf_page_number')::integer;
      r.workspace_code := body->'source'->>'workspace_code';
      r.source_drawing_page := body->'source'->>'workspace_page';
      r.target_pdf_page_number := (body->'target'->>'pdf_page_number')::integer;
      r.target_drawing_page := body->'target'->>'workspace_page';
      if r.target_pdf_page_number is not null and not exists(
        select 1 from jsonb_array_elements(coalesce(p.drawing_index->'pages','[]')) page
        where (page->>'pdf_page_number')::integer=r.target_pdf_page_number) then
        raise sqlstate 'PT422' using message='Target page is not in this project';
      end if;
      select coalesce(max(row_order),-1)+1 into r.row_order from public.extraction_connection_rows
        where project_id=project and batch_id=r.batch_id and source_pdf_page_number=r.source_pdf_page_number;
      r.wire_number := body->>'wire_number'; r.record_version := 1; r.evidence := '{}'::jsonb;
      r.is_cross_page := coalesce(r.target_pdf_page_number<>r.source_pdf_page_number,false);
      r.needs_review := false;
    end if;
    changed := jsonb_populate_record(r,fields-'is_cross_page'-'voltage_level');
    if fields ? 'is_cross_page' and fields->>'is_cross_page' is not null then
      if fields->>'is_cross_page' not in ('same_page','cross_page','unknown') then
        raise sqlstate 'PT422' using message='Invalid cross-page state';
      end if;
      changed.is_cross_page := fields->>'is_cross_page'='cross_page';
      if fields->>'is_cross_page'='unknown' then changed.needs_review := true; end if;
    end if;
    if not changed.is_cross_page then
      changed.target_pdf_page_number := null; changed.target_drawing_page := null;
    end if;
    if fields ? 'voltage_level' then
      changed.evidence := coalesce(changed.evidence,'{}'::jsonb) || jsonb_build_object('voltage_level',fields->'voltage_level');
    end if;
    changed.needs_review := coalesce(changed.needs_review,false)
      or nullif(btrim(changed.start_terminal),'') is null
      or nullif(btrim(changed.end_terminal),'') is null
      or (changed.is_cross_page and changed.target_pdf_page_number is null);
    if action='add' then
      changed.created_at := now(); changed.updated_at := now();
      insert into public.extraction_connection_rows select changed.* returning * into changed;
    else
      update public.extraction_connection_rows set
        principle_number=changed.principle_number,terminal_strip=changed.terminal_strip,
        start_code=changed.start_code,start_description=changed.start_description,start_terminal=changed.start_terminal,
        end_code=changed.end_code,end_description=changed.end_description,end_terminal=changed.end_terminal,
        current_value=changed.current_value,color_mark=changed.color_mark,remark=changed.remark,
        is_cross_page=changed.is_cross_page,target_pdf_page_number=changed.target_pdf_page_number,
        target_drawing_page=changed.target_drawing_page,needs_review=changed.needs_review,evidence=changed.evidence
        where id=r.id returning * into changed;
    end if;
    after_value := to_jsonb(changed);
  end if;
  receipt := jsonb_build_object('connection_id',changed.id,'batch_id',changed.batch_id,
    'action',action,'record_version',changed.record_version,'idempotent',false);
  management := management || jsonb_build_object(
    'receipts',coalesce(management->'receipts','{}'::jsonb) || jsonb_build_object(key,jsonb_build_object('request',value,'receipt',receipt)),
    'audit',coalesce(management->'audit','[]'::jsonb) || jsonb_build_array(jsonb_build_object(
      'action',action,'actor',actor,'time',now(),'before',before_value,'after',after_value)));
  update public.extraction_projects set drawing_index=jsonb_set(drawing_index,'{management}',management)
    where id=project;
  return receipt;
end;
$$;

notify pgrst,'reload schema';
commit;
