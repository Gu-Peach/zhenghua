-- Keep old wiring evidence attached to old classification metadata.
drop index public.workspaces_project_code_uidx;
create unique index workspaces_project_code_uidx on public.workspaces(project_id,code)
  where code is not null and classification_snapshot_id is null;
create unique index workspaces_snapshot_code_uidx on public.workspaces(project_id,classification_snapshot_id,code)
  where classification_snapshot_id is not null;

create function public.gate_a_start_stage(target uuid,token jsonb,stage_name text) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare r public.agent_runs;
begin
  r:=public.gate_a_lock(target,token);
  if stage_name not in ('RENDER','PAGE_CLASSIFICATION','PAGE_SCAN','BUILD_CROSS_PAGE_TASKS',
    'CROSS_PAGE_COMPLETION','VALIDATION') then raise exception 'invalid stage'; end if;
  update public.agent_runs set current_stage=stage_name where id=target;
  perform public.gate_a_event(target,'start:'||stage_name,'STAGE_STARTED',stage_name);
  return '{}';
end $$;

alter function public.gate_a_seal(uuid,jsonb,text,jsonb) rename to gate_a_base_seal;
create function public.gate_a_seal(target uuid,token jsonb,stage_name text,snapshot_value jsonb)
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
  return public.gate_a_base_seal(target,token,stage_name,snapshot_value);
end $$;

create function public.gate_a_materialize_classification(target uuid) returns void
language plpgsql security definer set search_path=public,pg_temp as $$
declare r public.agent_runs; manifest jsonb; page jsonb; aid text;
begin
  if current_setting('gate_a.authorized',true) is distinct from target::text then
    raise exception 'fenced parent operation required'; end if;
  select * into r from public.agent_runs where id=target;
  aid:=target::text||':gate_a_manifest:PAGE_CLASSIFICATION:manifest';
  select payload into manifest from public.agent_artifacts where artifact_id=aid;
  if manifest is null then raise exception 'classification not sealed'; end if;
  for page in select * from jsonb_array_elements(manifest->'snapshot'->'pages') loop
    insert into public.workspaces(id,project_id,code,name,sort_order,classification_snapshot_id)
      values((page->>'workspace_id')::uuid,r.project_id,coalesce(page->>'function','UNKNOWN'),
        coalesce(page->>'function','UNKNOWN'),(page->>'page_number')::int-1,aid) on conflict(id) do nothing;
    insert into public.drawings(id,project_id,workspace_id,pdf_page_number,workspace_page,
      image_bucket,image_path,status,classification_snapshot_id)
      values((page->>'drawing_id')::uuid,r.project_id,(page->>'workspace_id')::uuid,
        (page->>'page_number')::int,page->>'workspace_page',page->'image_ref'->>'storage_bucket',
        page->'image_ref'->>'storage_path','classified',aid) on conflict(id) do nothing;
  end loop;
end $$;

alter function public.gate_a_commit_result(uuid,jsonb,jsonb,text) rename to gate_a_base_commit_result;
create function public.gate_a_commit_result(target uuid,token jsonb,value jsonb,run_status text)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
begin
  perform public.gate_a_lock(target,token);
  perform public.gate_a_materialize_classification(target);
  return public.gate_a_base_commit_result(target,token,value,run_status);
end $$;
do $$ declare f record; begin
  for f in select oid::regprocedure signature from pg_proc
    where pronamespace='public'::regnamespace and proname like 'gate_a_%'
  loop execute format('revoke all on function %s from public,anon,authenticated',f.signature);
       execute format('grant execute on function %s to service_role',f.signature);
  end loop;
end $$;
notify pgrst,'reload schema';
