-- Stage 2 page extraction. Local branch artifact only; not deployed by this task.
-- No new tables/data writes. Frozen old inputs retain their historical stage order.
-- Rollback: retain historical artifacts; revert RPC definitions only after new runs finish.
create function public.gate_a_workflow_upstream(target uuid, stage_name text) returns text
language plpgsql security definer set search_path=public,pg_temp as $$
declare workflow text;
begin
  select payload->'configuration'->>'workflow' into workflow from public.agent_artifacts
    where artifact_id=target::text||':durable-input';
  if workflow='page_extraction_v2' then
    if stage_name not in ('RENDER','PAGE_CLASSIFICATION','PAGE_SCAN','VALIDATION') then
      raise exception 'stage not part of page extraction workflow';
    end if;
    return case stage_name when 'PAGE_CLASSIFICATION' then 'RENDER'
      when 'PAGE_SCAN' then 'PAGE_CLASSIFICATION' when 'VALIDATION' then 'PAGE_SCAN' else null end;
  end if;
  return case stage_name when 'RENDER' then null when 'PAGE_CLASSIFICATION' then 'RENDER'
    when 'PAGE_SCAN' then 'PAGE_CLASSIFICATION' when 'BUILD_CROSS_PAGE_TASKS' then 'PAGE_SCAN'
    when 'CROSS_PAGE_COMPLETION' then 'BUILD_CROSS_PAGE_TASKS'
    when 'VALIDATION' then 'CROSS_PAGE_COMPLETION' else 'INVALID' end;
end $$;
create or replace function public.gate_a_base_seal(target uuid, token jsonb, stage_name text, snapshot_value jsonb)
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
  upstream:=public.gate_a_workflow_upstream(target,stage_name);
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

create or replace function public.gate_a_commit_item(target uuid,token jsonb,item jsonb,model_cache boolean default false)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare r public.agent_runs; semantic jsonb; receipt jsonb; aid text; fingerprint text; upstream text;
  root_digest text; upstream_digest text;
begin
  r:=public.gate_a_lock(target,token);
  semantic:=item-'attempt'-'created_at'-'metrics';
  select checksum into root_digest from public.agent_artifacts where artifact_id=target::text||':durable-input';
  upstream:=public.gate_a_workflow_upstream(target,item->>'stage');
  if upstream is not null then
    select result_digest into upstream_digest from public.agent_artifacts
      where artifact_id=target::text||':gate_a_manifest:'||upstream||':manifest';
    if upstream_digest is null then raise exception 'upstream input not sealed'; end if;
  end if;
  if root_digest is null then raise exception 'no frozen input'; end if;
  fingerprint:=public.gate_a_digest(jsonb_build_object('root',root_digest,'stage',item->>'stage',
    'item_id',item->>'item_id','upstream_result_digest',upstream_digest));
  if item->>'input_fingerprint'<>fingerprint then raise exception 'item input fingerprint mismatch'; end if;
  receipt:=public.gate_a_base_commit_item(target,token,semantic,model_cache);
  aid:=receipt->>'artifact_id';
  if (receipt->>'conflict')::boolean then
    aid:=aid||':conflict:'||public.gate_a_digest(semantic);
    update public.agent_artifacts set payload=item,checksum=public.gate_a_digest(item) where artifact_id=aid;
  elsif not (receipt->>'idempotent')::boolean then
    update public.agent_artifacts set payload=item,checksum=public.gate_a_digest(item) where artifact_id=aid;
  end if;
  return receipt;
end $$;

create or replace function public.gate_a_seal(target uuid,token jsonb,stage_name text,snapshot_value jsonb)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare r public.agent_runs; prior jsonb; existing jsonb; page jsonb; saved jsonb;
  expected text[]; actual text[]; tasks jsonb;
begin
  r:=public.gate_a_lock(target,token);
  select payload into existing from public.agent_artifacts where artifact_id=
    target::text||':gate_a_manifest:'||stage_name||':manifest';
  if existing is not null then
    if existing->>'result_digest'<>public.gate_a_digest(snapshot_value) then raise exception 'snapshot changed'; end if;
    return existing;
  end if;
  if stage_name in ('RENDER','PAGE_CLASSIFICATION','PAGE_SCAN') then
    for page in select * from jsonb_array_elements(snapshot_value->'pages') loop
      select payload->'result'->'page' into saved from public.agent_artifacts
        where agent_run_id=target and kind='gate_a_item' and stage=stage_name
          and item_id='pdf-page:'||(page->>'page_number');
      if saved is null or saved<>page then raise exception 'snapshot page does not match canonical item'; end if;
    end loop;
    select array_agg((p->>'page_number')::int::text order by (p->>'page_number')::int) into actual
      from jsonb_array_elements(snapshot_value->'pages') p;
    select array_agg(i::text order by i) into expected from generate_series(1,
      (select (payload->>'page_count')::int from public.agent_artifacts
       where artifact_id=target::text||':durable-input')) i;
    if actual is distinct from expected then raise exception 'snapshot pages incomplete'; end if;
  elsif stage_name='BUILD_CROSS_PAGE_TASKS' then
    select payload->'snapshot' into prior from public.agent_artifacts where artifact_id=
      target::text||':gate_a_manifest:PAGE_SCAN:manifest';
    select array_agg(k order by k collate "C") into expected from jsonb_object_keys(prior->'planning_sources') k;
    select array_agg(k order by k collate "C") into actual from jsonb_object_keys(snapshot_value->'planning_sources') k;
    if expected is distinct from actual then raise exception 'planning connection coverage'; end if;
    select coalesce(jsonb_agg(t order by t->>'task_id'),'[]') into tasks
      from public.agent_artifacts a cross join lateral jsonb_array_elements(a.payload->'result'->'tasks') t
      where a.agent_run_id=target and a.stage=stage_name and a.kind='gate_a_item';
    select coalesce(jsonb_agg(t order by t->>'task_id'),'[]') into saved
      from jsonb_array_elements(snapshot_value->'cross_page_tasks') t;
    if tasks<>saved then raise exception 'task inventory mismatch'; end if;
  end if;
  if stage_name='PAGE_SCAN' and exists (
    select 1 from public.agent_artifacts where artifact_id=target::text||':durable-input'
      and payload->'configuration'->>'workflow'='page_extraction_v2'
  ) then
    -- Page completion is authoritative, not just the presence of a page identity.
    for page in select * from jsonb_array_elements(snapshot_value->'pages') loop
      select payload->'result'->'scan' into saved from public.agent_artifacts
        where agent_run_id=target and stage='PAGE_SCAN' and kind='gate_a_item'
          and item_id='pdf-page:'||(page->>'page_number');
      if saved is distinct from snapshot_value->'page_scan_results'->(page->>'page_number') then
        raise exception 'completed page scan mismatch';
      end if;
    end loop;
    select coalesce(jsonb_object_agg(k,v),'{}') into saved
      from public.agent_artifacts a cross join lateral jsonb_each(a.payload->'result'->'wire_units') e(k,v)
      where a.agent_run_id=target and a.stage='PAGE_SCAN' and a.kind='gate_a_item';
    if saved is distinct from snapshot_value->'wire_units' then
      raise exception 'completed page connection facts mismatch';
    end if;
  end if;
  return public.gate_a_base_seal(target,token,stage_name,snapshot_value);
end $$;

revoke all on function public.gate_a_workflow_upstream(uuid,text) from public,anon,authenticated;
grant execute on function public.gate_a_workflow_upstream(uuid,text) to service_role;
notify pgrst,'reload schema';
