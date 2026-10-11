-- Gate A: additive durable stages. Existing runs keep protocol 1.
-- Rollback: disable protocol-2 creation; retain artifacts/receipts. Do not DROP data.
alter table public.agent_runs
  add column protocol_version integer not null default 1 check (protocol_version in (1,2)),
  add column lease_generation bigint not null default 0,
  add column classification_epoch bigint;
alter table public.projects
  add column classification_publish_epoch bigint not null default 0,
  add column published_classification_snapshot_id text;
alter table public.agent_run_queue add column lease_expires_at timestamptz;
alter table public.agent_artifacts
  add column stage text, add column item_id text, add column input_fingerprint text,
  add column result_digest text;
create index agent_artifacts_stage_item_idx on public.agent_artifacts(agent_run_id,stage,item_id);
create unique index agent_stage_canonical_idx
  on public.agent_artifacts(agent_run_id,stage,item_id)
  where kind in ('gate_a_item','gate_a_model','gate_a_manifest');
alter table public.drawings add column classification_snapshot_id text;
alter table public.workspaces add column classification_snapshot_id text;

create function public.gate_a_json(value jsonb) returns text
language plpgsql immutable strict set search_path=public,pg_temp as $$
declare answer text; number text;
begin
  case jsonb_typeof(value)
    when 'object' then
      select '{'||coalesce(string_agg(to_jsonb(key)::text||':'||public.gate_a_json(val),','
        order by key collate "C"),'')||'}' into answer from jsonb_each(value) e(key,val);
    when 'array' then
      select '['||coalesce(string_agg(public.gate_a_json(val),',' order by idx),'')||']'
        into answer from jsonb_array_elements(value) with ordinality e(val,idx);
    when 'number' then
      number := ((value#>>'{}')::numeric)::text;
      if position('.' in number)>0 then number:=rtrim(rtrim(number,'0'),'.'); end if;
      answer:=case when number='-0' then '0' else number end;
    else answer:=value::text;
  end case;
  return answer;
end $$;
create function public.gate_a_digest(value jsonb) returns text
language sql immutable strict set search_path=public,extensions,pg_temp as $$
  select 'sha256:'||encode(digest(convert_to(public.gate_a_json(value),'UTF8'),'sha256'),'hex')
$$;

-- All mutation helpers use the same project -> run -> queue locking order.
create function public.gate_a_lock(target uuid, token jsonb, allow_terminal boolean default false)
returns public.agent_runs language plpgsql security definer set search_path=public,pg_temp as $$
declare r public.agent_runs; q public.agent_run_queue; p uuid;
begin
  select project_id into p from public.agent_runs where id=target;
  perform 1 from public.projects where id=p for update;
  select * into r from public.agent_runs where id=target for update;
  select * into q from public.agent_run_queue where agent_run_id=target for update;
  if r.id is null or r.protocol_version<>2 or token->>'run_id'<>target::text
     or token->>'owner' is distinct from q.leased_by
     or (token->>'generation')::bigint is distinct from r.lease_generation
     or q.lease_expires_at is null or q.lease_expires_at<=clock_timestamp() then
    raise exception 'lease lost' using errcode='40001';
  end if;
  if not allow_terminal and r.status<>'RUNNING' then
    raise exception 'run is not running' using errcode='40001';
  end if;
  perform set_config('gate_a.authorized',target::text,true);
  return r;
end $$;

create function public.gate_a_guard() returns trigger
language plpgsql security definer set search_path=public,pg_temp as $$
declare rid uuid; version integer;
begin
  if tg_table_name='agent_runs' then rid:=new.id;
  elsif tg_table_name='result_versions' then
    begin rid:=new.agent_run_id::uuid; exception when invalid_text_representation then return new; end;
  else rid:=new.agent_run_id; end if;
  select protocol_version into version from public.agent_runs where id=rid;
  if version=2 and current_setting('gate_a.authorized',true) is distinct from rid::text then
    raise exception 'protocol 2 requires fenced mutation' using errcode='42501';
  end if;
  return new;
end $$;
create trigger gate_a_guard_run before update on public.agent_runs
for each row execute function public.gate_a_guard();
create trigger gate_a_guard_event before insert on public.agent_events
for each row execute function public.gate_a_guard();
create trigger gate_a_guard_artifact before insert or update on public.agent_artifacts
for each row execute function public.gate_a_guard();
create trigger gate_a_guard_checkpoint before insert or update on public.agent_checkpoints
for each row execute function public.gate_a_guard();
create trigger gate_a_guard_proposal before insert or update on public.result_proposals
for each row execute function public.gate_a_guard();
create trigger gate_a_guard_result before insert on public.result_versions
for each row execute function public.gate_a_guard();

create function public.gate_a_run_created() returns trigger language plpgsql security definer
set search_path=public,pg_temp as $$
begin
  if new.protocol_version=2 then
    if new.run_type<>'FULL_EXTRACTION' then raise exception 'protocol 2 is extraction only'; end if;
    update public.projects set classification_publish_epoch=classification_publish_epoch+1
      where id=new.project_id returning classification_publish_epoch into new.classification_epoch;
  end if;
  return new;
end $$;
create trigger gate_a_run_created before insert on public.agent_runs
for each row execute function public.gate_a_run_created();

create function public.gate_a_event(target uuid, event_key text, event_type text,
  stage_name text, refs jsonb default '[]', metrics jsonb default '{}') returns integer
language plpgsql security definer set search_path=public,pg_temp as $$
declare eid uuid; seq integer;
begin
  eid:=md5(target::text||':'||event_key)::uuid;
  seq:=public.append_agent_event(eid,target,event_type,stage_name,'INFO',null,
    event_type,metrics,refs,null,now());
  return seq;
end $$;

create function public.claim_durable_agent_run(worker_id text, lease_seconds integer default 300)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare candidate record; r public.agent_runs; q public.agent_run_queue; mode text; exp timestamptz;
begin
  if worker_id='' or lease_seconds<1 then raise exception 'invalid lease configuration'; end if;
  for candidate in
    select a.id,a.project_id from public.agent_runs a join public.agent_run_queue b on a.id=b.agent_run_id
    where a.protocol_version=2 and b.available_at<=now()
      and (b.leased_by is null or b.lease_expires_at<=clock_timestamp())
    order by b.available_at,b.created_at limit 32
  loop
    perform 1 from public.projects where id=candidate.project_id for update skip locked;
    if not found then continue; end if;
    select * into r from public.agent_runs where id=candidate.id for update;
    select * into q from public.agent_run_queue where agent_run_id=r.id for update;
    if q.agent_run_id is null or q.available_at>now() or
      (q.leased_by is not null and q.lease_expires_at>clock_timestamp()) then continue; end if;
    mode:=case when r.status='RUNNING' then 'recover'
      when r.status='QUEUED' then 'execute' else 'cleanup' end;
    exp:=clock_timestamp()+make_interval(secs=>lease_seconds);
    perform set_config('gate_a.authorized',r.id::text,true);
    update public.agent_runs set lease_generation=lease_generation+1,
      status=case when mode='cleanup' then status else 'RUNNING' end where id=r.id
      returning * into r;
    update public.agent_run_queue set leased_by=worker_id,leased_at=clock_timestamp(),
      lease_expires_at=exp,attempts=attempts+1 where agent_run_id=r.id;
    if mode<>'cleanup' then perform public.gate_a_event(r.id,
      case when mode='execute' then 'started' else 'recovered:'||r.lease_generation end,
      case when mode='execute' then 'RUN_STARTED' else 'ITEM_COMPLETED' end,null);
    end if;
    return jsonb_build_object('run_id',r.id,'owner',worker_id,'generation',r.lease_generation,
      'expires_at',exp,'mode',mode);
  end loop;
  return null;
end $$;

create function public.gate_a_lease_action(target uuid, token jsonb, action text, value jsonb default '{}')
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare r public.agent_runs; receipt jsonb; attempts integer;
begin
  r:=public.gate_a_lock(target,token,true);
  if action='renew' then
    update public.agent_run_queue set lease_expires_at=clock_timestamp()+
      make_interval(secs=>greatest(1,(value->>'seconds')::integer)) where agent_run_id=target;
  elsif action='ack' then
    if r.status in ('QUEUED','RUNNING') then raise exception 'cannot acknowledge unfinished run'; end if;
    delete from public.agent_run_queue where agent_run_id=target;
  elsif action='fail' then
    select payload into receipt from public.agent_artifacts where artifact_id=target::text||':final-receipt';
    if receipt is not null then return jsonb_build_object('recover_finalization',true); end if;
    select q.attempts into attempts from public.agent_run_queue q where q.agent_run_id=target;
    if coalesce((value->>'retryable')::boolean,false) and attempts<4 then
      update public.agent_runs set status='QUEUED',error=value->'error' where id=target;
      update public.agent_run_queue set available_at=now()+make_interval(secs=>least(60,2^attempts)::int),
        leased_by=null,leased_at=null,lease_expires_at=null where agent_run_id=target;
    else
      update public.agent_runs set status='FAILED',error=value->'error' where id=target;
      perform public.gate_a_event(target,'failed:'||r.lease_generation,'RUN_FAILED',r.current_stage,
        '[]',jsonb_build_object('attempt',attempts));
      delete from public.agent_run_queue where agent_run_id=target;
    end if;
  else raise exception 'unknown lease action'; end if;
  return '{}';
end $$;

create function public.gate_a_initialize(target uuid, token jsonb, input_value jsonb)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare r public.agent_runs; existing jsonb; aid text; n integer;
begin
  r:=public.gate_a_lock(target,token);
  if input_value->>'run_id'<>target::text or input_value->>'project_id'<>r.project_id::text
    or input_value->>'source_document_id'<>r.source_document_id::text then raise exception 'input scope'; end if;
  if not exists(select 1 from public.document_files where id=r.source_document_id
    and checksum=input_value->>'source_checksum') then raise exception 'source checksum'; end if;
  n:=(input_value->>'page_count')::int;
  if n<1 then raise exception 'empty PDF'; end if;
  aid:=target::text||':durable-input';
  select payload into existing from public.agent_artifacts where artifact_id=aid;
  if existing is not null then
    if existing<>input_value then raise exception 'frozen input changed'; end if;
    return existing;
  end if;
  insert into public.agent_artifacts(artifact_id,agent_run_id,kind,payload,checksum)
    values(aid,target,'gate_a_input',input_value,public.gate_a_digest(input_value));
  update public.agent_runs set profile=input_value->'profile' where id=target;
  return input_value;
end $$;

create function public.gate_a_commit_item(target uuid, token jsonb, item jsonb,
  model_cache boolean default false) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare r public.agent_runs; aid text; existing public.agent_artifacts; result_hash text; kind_value text;
begin
  r:=public.gate_a_lock(target,token);
  if item->>'run_id'<>target::text or item->>'item_id'='' or item->>'stage' not in
    ('RENDER','PAGE_CLASSIFICATION','PAGE_SCAN','BUILD_CROSS_PAGE_TASKS','CROSS_PAGE_COMPLETION','VALIDATION')
    or item->>'status' not in ('completed','skipped') then raise exception 'invalid stage item'; end if;
  kind_value:=case when model_cache then 'gate_a_model' else 'gate_a_item' end;
  aid:=target::text||':'||kind_value||':'||(item->>'stage')||':'||(item->>'item_id');
  result_hash:=public.gate_a_digest(item);
  select * into existing from public.agent_artifacts where artifact_id=aid;
  if existing.artifact_id is not null then
    if existing.input_fingerprint<>item->>'input_fingerprint' then raise exception 'input changed'; end if;
    if existing.result_digest<>result_hash then
      insert into public.agent_artifacts(artifact_id,agent_run_id,kind,payload,checksum)
        values(aid||':conflict:'||result_hash,target,'gate_a_conflict',item,result_hash)
        on conflict(artifact_id) do nothing;
    end if;
    return jsonb_build_object('artifact_id',aid,'result_digest',existing.result_digest,
      'idempotent',true,'conflict',existing.result_digest<>result_hash);
  end if;
  insert into public.agent_artifacts(artifact_id,agent_run_id,kind,payload,checksum,stage,item_id,
    input_fingerprint,result_digest)
    values(aid,target,kind_value,item,result_hash,item->>'stage',item->>'item_id',
      item->>'input_fingerprint',result_hash);
  perform public.save_agent_checkpoint(aid,target,jsonb_build_object('artifact_id',aid),0);
  if not model_cache then perform public.gate_a_event(target,'item:'||aid,'ITEM_COMPLETED',item->>'stage',
    jsonb_build_array(aid)); end if;
  return jsonb_build_object('artifact_id',aid,'result_digest',result_hash,'idempotent',false,'conflict',false);
end $$;

create function public.gate_a_seal(target uuid, token jsonb, stage_name text, snapshot_value jsonb)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare r public.agent_runs; aid text; upstream text; input_value jsonb; expected text[]; actual text[];
  ids text[]; prior jsonb; manifest jsonb; n integer; done_count int; skipped_count int;
  review_count int; publish boolean:=false; page jsonb; wid uuid; did uuid; code text; image jsonb;
begin
  r:=public.gate_a_lock(target,token);
  aid:=target::text||':gate_a_manifest:'||stage_name||':manifest';
  select payload into manifest from public.agent_artifacts where artifact_id=aid;
  if manifest is not null then return manifest; end if;
  select payload into input_value from public.agent_artifacts where artifact_id=target::text||':durable-input';
  if input_value is null then raise exception 'no frozen input'; end if;
  upstream:=case stage_name when 'RENDER' then null when 'PAGE_CLASSIFICATION' then 'RENDER'
    when 'PAGE_SCAN' then 'PAGE_CLASSIFICATION' when 'BUILD_CROSS_PAGE_TASKS' then 'PAGE_SCAN'
    when 'CROSS_PAGE_COMPLETION' then 'BUILD_CROSS_PAGE_TASKS' when 'VALIDATION' then 'CROSS_PAGE_COMPLETION'
    else 'INVALID' end;
  if upstream='INVALID' then raise exception 'invalid stage'; end if;
  if upstream is not null then
    select payload into prior from public.agent_artifacts
      where artifact_id=target::text||':gate_a_manifest:'||upstream||':manifest';
    if prior is null then raise exception 'upstream not sealed'; end if;
  end if;
  if stage_name in ('RENDER','PAGE_CLASSIFICATION','PAGE_SCAN') then
    select array_agg('pdf-page:'||i order by ('pdf-page:'||i) collate "C") into expected
      from generate_series(1,(input_value->>'page_count')::int) i;
  elsif stage_name='BUILD_CROSS_PAGE_TASKS' then
    select coalesce(array_agg(k order by k collate "C"),'{}') into expected
      from jsonb_object_keys(prior->'snapshot'->'planning_sources') k;
  elsif stage_name='CROSS_PAGE_COMPLETION' then
    select coalesce(array_agg(t->>'task_id' order by (t->>'task_id') collate "C"),'{}') into expected
      from jsonb_array_elements(prior->'snapshot'->'cross_page_tasks') t;
  else expected:=array['validation']; end if;
  select coalesce(array_agg(item_id order by item_id collate "C"),'{}'),
    coalesce(array_agg(artifact_id order by item_id collate "C"),'{}'),
    count(*) filter(where payload->>'status'='completed'),
    count(*) filter(where payload->>'status'='skipped'),
    count(*) filter(where (payload->>'needs_review')::boolean)
    into actual,ids,done_count,skipped_count,review_count
    from public.agent_artifacts where agent_run_id=target and stage=stage_name and kind='gate_a_item';
  if actual is distinct from expected then raise exception 'stage coverage mismatch'; end if;
  publish:=stage_name='PAGE_CLASSIFICATION' and r.classification_epoch=
    (select classification_publish_epoch from public.projects where id=r.project_id);
  if publish then
    for page in select * from jsonb_array_elements(snapshot_value->'pages') loop
      code:=coalesce(nullif(page->>'function',''),'UNKNOWN');
      wid:=(page->>'workspace_id')::uuid; did:=(page->>'drawing_id')::uuid; image:=page->'image_ref';
      insert into public.workspaces(id,project_id,code,name,sort_order,classification_snapshot_id)
        values(wid,r.project_id,code,code,(page->>'page_number')::int-1,aid)
        on conflict(id) do update set classification_snapshot_id=aid;
      insert into public.drawings(id,project_id,workspace_id,pdf_page_number,workspace_page,
        image_bucket,image_path,status,classification_snapshot_id)
        values(did,r.project_id,wid,(page->>'page_number')::int,page->>'workspace_page',
          image->>'storage_bucket',image->>'storage_path','classified',aid)
        on conflict(id) do update set workspace_id=excluded.workspace_id,workspace_page=excluded.workspace_page,
          image_path=excluded.image_path,image_bucket=excluded.image_bucket,classification_snapshot_id=aid;
    end loop;
    update public.projects set published_classification_snapshot_id=aid where id=r.project_id;
  end if;
  manifest:=jsonb_build_object('schema_version','1.0.0','run_id',target,'stage',stage_name,
    'upstream_stage',upstream,'expected_item_ids',expected,'item_artifact_ids',ids,
    'counts',jsonb_build_object('expected',cardinality(expected),'completed',done_count,'skipped',skipped_count,
      'failed',0,'needs_review',review_count),'ready_for_next_stage',true,'snapshot',snapshot_value,
    'result_digest',public.gate_a_digest(snapshot_value),'tree_published',publish);
  insert into public.agent_artifacts(artifact_id,agent_run_id,kind,payload,checksum,stage,item_id,result_digest)
    values(aid,target,'gate_a_manifest',manifest,public.gate_a_digest(manifest),stage_name,'manifest',
      public.gate_a_digest(snapshot_value));
  perform public.save_agent_checkpoint(target::text||':stage:'||stage_name,target,
    jsonb_build_object('artifact_id',aid),0);
  update public.agent_runs set current_stage=stage_name where id=target;
  perform public.gate_a_event(target,'sealed:'||stage_name,'STAGE_COMPLETED',stage_name,
    jsonb_build_array(aid),jsonb_build_object('tree_published',publish));
  return manifest;
end $$;

-- Controlled legacy-shaped writes; no dynamic SQL, table names or field lists.
create function public.gate_a_runtime_write(target uuid, token jsonb, kind text, value jsonb)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare r public.agent_runs; seq int; existing jsonb;
begin
  r:=public.gate_a_lock(target,token);
  if kind='event' then
    seq:=public.append_agent_event((value->>'event_id')::uuid,target,value->>'event_type',value->>'stage',
      value->>'level',value->'scope',value->>'message',value->'metrics',value->'artifact_refs',value->'error',
      (value->>'occurred_at')::timestamptz);
    return to_jsonb(seq);
  elsif kind='run' then
    update public.agent_runs set current_stage=value->>'current_stage',profile=value->'profile',
      profile_hint=value->>'profile_hint' where id=target;
  elsif kind='artifact' then
    if value->>'agent_run_id'<>target::text then raise exception 'artifact scope'; end if;
    select payload into existing from public.agent_artifacts where artifact_id=value->>'artifact_id';
    if existing is not null and existing<>value then raise exception 'artifact conflict'; end if;
    insert into public.agent_artifacts(artifact_id,agent_run_id,kind,payload,storage_bucket,storage_path,checksum)
      values(value->>'artifact_id',target,value->>'kind',value,value->>'storage_bucket',value->>'storage_path',
        value->>'checksum') on conflict(artifact_id) do nothing;
  elsif kind='proposal' then
    if value->>'agent_run_id'<>target::text or value->>'project_id'<>r.project_id::text then
      raise exception 'proposal scope'; end if;
    select payload into existing from public.result_proposals where id=value->>'proposal_id';
    if existing is not null and existing<>value then raise exception 'proposal conflict'; end if;
    insert into public.result_proposals(id,agent_run_id,project_id,status,payload)
      values(value->>'proposal_id',target,r.project_id,value->>'status',value) on conflict(id) do nothing;
  else raise exception 'invalid runtime write'; end if;
  return '{}';
end $$;

create function public.gate_a_commit_result(target uuid, token jsonb, value jsonb, run_status text)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare r public.agent_runs; committed jsonb; receipt jsonb;
begin
  r:=public.gate_a_lock(target,token);
  if value->>'target_agent_run_id'<>target::text or value->>'target_project_id'<>r.project_id::text then
    raise exception 'result scope'; end if;
  select payload into receipt from public.agent_artifacts where artifact_id=target::text||':final-receipt';
  if receipt is not null then return receipt; end if;
  if not exists(select 1 from public.agent_artifacts where agent_run_id=target and
    kind='gate_a_manifest' and stage='VALIDATION') then raise exception 'validation not sealed'; end if;
  if run_status not in ('SUCCEEDED','NEEDS_REVIEW') then raise exception 'invalid final status'; end if;
  committed:=public.commit_wiring_result(value->>'proposal_key',r.project_id,target,
    (value->>'created_by_user')::uuid,(value->>'expected_base_version')::int,value->>'target_status',
    value->'profile_value',value->'model_value',value->'units_value',value->'feedback_updates');
  receipt:=jsonb_build_object('run_id',target,'proposal_id',value->>'proposal_key',
    'result_version_id',committed->>'result_version_id','result_version',committed->'result_version',
    'status',run_status,'finalized',false);
  insert into public.agent_artifacts(artifact_id,agent_run_id,kind,payload,checksum)
    values(target::text||':final-receipt',target,'gate_a_receipt',receipt,public.gate_a_digest(receipt));
  return receipt;
end $$;

create function public.gate_a_finalize(target uuid, token jsonb) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare r public.agent_runs; receipt jsonb; aid text; final_receipt jsonb;
begin
  r:=public.gate_a_lock(target,token,true);
  aid:=target::text||':final-receipt';
  select payload into receipt from public.agent_artifacts where artifact_id=aid;
  if receipt is null then raise exception 'result not committed'; end if;
  select payload into final_receipt from public.agent_artifacts where artifact_id=target::text||':finalized';
  if final_receipt is not null then return final_receipt; end if;
  insert into public.agent_artifacts(artifact_id,agent_run_id,kind,payload)
    values(target::text||':result-version',target,'result_version',jsonb_build_object(
      'artifact_id',target::text||':result-version','agent_run_id',target,'kind','result_version',
      'proposal_id',receipt->>'proposal_id','result_version_id',receipt->>'result_version_id',
      'result_version',receipt->'result_version')) on conflict(artifact_id) do nothing;
  final_receipt:=receipt||jsonb_build_object('finalized',true);
  insert into public.agent_artifacts(artifact_id,agent_run_id,kind,payload)
    values(target::text||':finalized',target,'gate_a_finalized',final_receipt);
  update public.agent_runs set status=receipt->>'status',error=null where id=target;
  perform public.gate_a_event(target,'finalized',case when receipt->>'status'='NEEDS_REVIEW'
    then 'HUMAN_INPUT_REQUIRED' else 'RUN_COMPLETED' end,null,jsonb_build_array(target::text||':result-version'));
  return final_receipt;
end $$;

create function public.gate_a_control(target uuid, action text) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare r public.agent_runs; p uuid; receipt jsonb;
begin
  select project_id into p from public.agent_runs where id=target;
  perform 1 from public.projects where id=p for update;
  select * into r from public.agent_runs where id=target for update;
  perform 1 from public.agent_run_queue where agent_run_id=target for update;
  if r.protocol_version<>2 then raise exception 'invalid protocol'; end if;
  select payload into receipt from public.agent_artifacts where artifact_id=target::text||':final-receipt';
  if receipt is not null then return jsonb_build_object('result_committed',true); end if;
  perform set_config('gate_a.authorized',target::text,true);
  if action='cancel' then
    update public.agent_runs set status='CANCELLED',lease_generation=lease_generation+1 where id=target;
    delete from public.agent_run_queue where agent_run_id=target;
    perform public.gate_a_event(target,'cancelled','RUN_CANCELLED',null);
  elsif action='resume' and r.status in ('FAILED','WAITING_INPUT') then
    update public.agent_runs set status='QUEUED',error=null,lease_generation=lease_generation+1 where id=target;
    insert into public.agent_run_queue(agent_run_id) values(target) on conflict(agent_run_id)
      do update set available_at=now(),leased_by=null,leased_at=null,lease_expires_at=null;
  else raise exception 'invalid control transition'; end if;
  return '{}';
end $$;

-- Block old queue claim/ack from accidentally consuming a protocol-2 run.
create function public.gate_a_queue_guard() returns trigger
language plpgsql security definer set search_path=public,pg_temp as $$
declare rid uuid;
begin
  rid:=case when tg_op='DELETE' then old.agent_run_id else new.agent_run_id end;
  if exists(select 1 from public.agent_runs where id=rid and protocol_version=2)
    and current_setting('gate_a.authorized',true) is distinct from rid::text then
    raise exception 'durable queue requires fencing' using errcode='42501';
  end if;
  if tg_op='DELETE' then return old; end if; return new;
end $$;
create trigger gate_a_queue_guard before update or delete on public.agent_run_queue
for each row execute function public.gate_a_queue_guard();

create or replace function public.claim_agent_run(worker_id text, lease_seconds integer default 300)
returns uuid language plpgsql security definer set search_path=public,pg_temp as $$
declare claimed uuid;
begin
  with candidate as (
    select q.agent_run_id from public.agent_run_queue q join public.agent_runs r on r.id=q.agent_run_id
    where r.protocol_version=1 and q.available_at<=now()
      and (q.leased_at is null or q.leased_at<now()-make_interval(secs=>lease_seconds))
    order by q.available_at,q.created_at for update of q skip locked limit 1
  ) update public.agent_run_queue q set leased_at=now(),leased_by=worker_id,attempts=q.attempts+1
    from candidate c where q.agent_run_id=c.agent_run_id returning q.agent_run_id into claimed;
  return claimed;
end $$;

-- None of the security-definer helpers are browser-callable.
do $$ declare f record; begin
  for f in select oid::regprocedure signature from pg_proc
    where pronamespace='public'::regnamespace and (proname like 'gate_a_%' or proname='claim_durable_agent_run')
  loop execute format('revoke all on function %s from public, anon, authenticated',f.signature);
       execute format('grant execute on function %s to service_role',f.signature);
  end loop;
end $$;
notify pgrst,'reload schema';
