-- User-confirmed replacement of the complete frozen page/workspace scope.
-- No business rows are rewritten at deployment. Requires 20261018050000.
-- Rollback: restore the public function name from decide_connection_rescan_patch,
-- revoke/grant it as in 20261018050000. Confirmed replaced rows need their audit snapshot to recover.
begin;

alter function public.decide_connection_rescan(jsonb) rename to decide_connection_rescan_patch;
revoke all on function public.decide_connection_rescan_patch(jsonb) from public,anon,authenticated,service_role;

create function public.decide_connection_rescan(value jsonb) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare p extraction_projects; job connection_rescan_runs; saved_baseline jsonb;
  current_rows jsonb; actual_versions jsonb; expected_versions jsonb;
  item jsonb; old_row jsonb; preview jsonb; result jsonb; audit jsonb;
  mode text; broad boolean; actor uuid:=(value->>'actor')::uuid;
  allowed text[]:=array['principle_number','terminal_strip','start_code','start_description','start_terminal',
    'end_code','end_description','end_terminal','current_value','remark','start_terminal_coordinates',
    'end_terminal_coordinates','target_pdf_page_number','target_drawing_page','is_cross_page','needs_review'];
begin
  if auth.role() is distinct from 'service_role' then raise sqlstate 'PT403' using message='Server only'; end if;
  select * into p from extraction_projects where id=(value->>'project_id')::uuid for update;
  if not found or p.owner_id is distinct from actor then raise sqlstate 'PT403' using message='Project owner required'; end if;
  select * into job from connection_rescan_runs where id=(value->>'id')::uuid and project_id=p.id and created_by=actor for update;
  if not found then raise sqlstate 'PT404' using message='Rescan not found'; end if;
  -- Existing decisions, rejection and cancellation retain their established semantics.
  if job.status in ('applied','rejected') or coalesce((value->>'accepted')::boolean,false)=false then
    return decide_connection_rescan_patch(value);
  end if;
  mode:=coalesce(job.request->>'result_mode','patch');
  broad:=job.request->>'fields'='all'
    and jsonb_array_length(coalesce(job.request->'scope'->'connection_ids','[]'))=0
    and jsonb_array_length(coalesce(job.request->'scope'->'principle_numbers','[]'))=0;
  if mode='patch' then
    if broad then raise sqlstate 'PT409' using message='Legacy full rescan must be regenerated for range replacement'; end if;
    if job.candidate->'replacement' is not null and job.candidate->'replacement'<>'null'::jsonb then
      raise sqlstate 'PT422' using message='Replacement candidate does not match patch mode'; end if;
    return decide_connection_rescan_patch(value);
  end if;
  if mode<>'replace_scope' or not broad or job.candidate->'replacement'->>'version' is distinct from '1' then
    raise sqlstate 'PT422' using message='Invalid replacement mode'; end if;
  if jsonb_typeof(job.candidate->'changes') is distinct from 'array'
    or jsonb_typeof(job.candidate->'replacement'->'removed') is distinct from 'array'
    or jsonb_typeof(job.candidate->'replacement'->'scanned_pages') is distinct from 'array' then
    raise sqlstate 'PT422' using message='Explicit replacement lists required'; end if;
  if job.status<>'ready' or value->>'checksum' is distinct from job.checksum then
    raise sqlstate 'PT409' using message='Replacement candidate changed or not ready'; end if;
  if p.status in ('processing','archived') or job.expires_at<now() then
    raise sqlstate 'PT409' using message='Project busy or candidate expired'; end if;
  if coalesce(p.drawing_index->>'active_batch_id',(select batch_id from extraction_connection_rows where project_id=p.id order by created_at desc,id desc limit 1)) is distinct from job.batch_id
    or p.drawing_index->'pages' is distinct from job.project_snapshot->'pages' then
    raise sqlstate 'PT409' using message='Batch or drawing index changed'; end if;
  if (select jsonb_agg(page->'pdf_page_number' order by (page->>'pdf_page_number')::int) from jsonb_array_elements(job.project_snapshot->'scan_pages') page)
      is distinct from (select jsonb_agg(page order by page::int) from jsonb_array_elements(job.candidate->'replacement'->'scanned_pages') page) then
    raise sqlstate 'PT422' using message='Replacement requires every frozen scan page'; end if;
  perform 1 from extraction_connection_rows x where x.project_id=p.id and x.batch_id=job.batch_id and rescan_matches(x,job.request->'scope') order by id for update;
  select coalesce(jsonb_agg(to_jsonb(x) order by id),'[]') into current_rows from extraction_connection_rows x
    where x.project_id=p.id and x.batch_id=job.batch_id and rescan_matches(x,job.request->'scope');
  select coalesce(jsonb_agg(jsonb_build_object('id',x->'id','version',x->'record_version') order by x->>'id'),'[]') into actual_versions from jsonb_array_elements(current_rows) x;
  select coalesce(jsonb_agg(jsonb_build_object('id',x->'id','version',x->'record_version') order by x->>'id'),'[]') into expected_versions from jsonb_array_elements(job.baseline) x;
  if actual_versions is distinct from expected_versions then raise sqlstate 'PT409' using message='Replacement scope or row versions changed'; end if;
  if expected_versions is distinct from (
    select coalesce(jsonb_agg(jsonb_build_object('id',x->'connection_id','version',x->'record_version') order by x->>'connection_id'),'[]')
      from jsonb_array_elements(job.candidate->'replacement'->'removed') x) then
    raise sqlstate 'PT422' using message='Deletion preview must equal the complete frozen baseline'; end if;
  for item in select * from jsonb_array_elements(job.candidate->'replacement'->'removed') loop
    select x into old_row from jsonb_array_elements(job.baseline) x where x->>'id'=item->>'connection_id';
    select jsonb_object_agg(key,coalesce(old_row->key,'null'::jsonb)) into preview from unnest(allowed) key;
    if item->'before' is distinct from preview
      or item->'source_pdf_page_number' is distinct from old_row->'source_pdf_page_number'
      or item->'source_drawing_page' is distinct from old_row->'source_drawing_page'
      or item->'workspace_code' is distinct from old_row->'workspace_code'
      or item->'principle_number' is distinct from old_row->'principle_number' then
      raise sqlstate 'PT422' using message='Deletion preview does not match saved facts'; end if;
  end loop;
  for item in select * from jsonb_array_elements(job.candidate->'changes') loop
    if item->>'action' is distinct from 'insert' or item->>'record_version' is distinct from '0'
      or exists(select 1 from extraction_connection_rows where id=(item->>'connection_id')::uuid) then
      raise sqlstate 'PT422' using message='Replacement requires fresh inserted row identities'; end if;
  end loop;
  saved_baseline:=job.baseline;
  -- Only this locked task is shielded from the existing delete-copy trigger.
  -- The trigger sees neither old IDs in baseline nor in the fresh insert list.
  -- Restore the confirmed snapshot after success; any error rolls this whole transaction back.
  update connection_rescan_runs set baseline='[]'::jsonb where id=job.id;
  delete from extraction_connection_rows x where x.project_id=p.id and x.batch_id=job.batch_id and rescan_matches(x,job.request->'scope');
  delete from connection_edit_proposals proposal where proposal.project_id=p.id and exists(
    select 1 from jsonb_array_elements(proposal.changes) change join jsonb_array_elements(saved_baseline) old on change->>'connection_id'=old->>'id');
  update extraction_projects set drawing_index=jsonb_set(coalesce(drawing_index,'{}'),'{active_batch_id}',to_jsonb(job.batch_id))
    where id=p.id and drawing_index->>'active_batch_id' is null;
  -- Reuse typed field, coordinate-page, origin, insert and receipt validation.
  -- The now-empty scope is checked again against the temporarily empty baseline.
  result:=decide_connection_rescan_patch(value);
  update connection_rescan_runs set baseline=saved_baseline,
    receipt=receipt||jsonb_build_object('replacement',true,'removed_count',jsonb_array_length(saved_baseline),
      'inserted_count',jsonb_array_length(job.candidate->'changes')) where id=job.id returning * into job;
  audit:=jsonb_build_object('action','rescan_replace_scope','actor',actor,'time',now(),'run_id',job.id,
    'scope',job.request->'scope','removed_ids',(select coalesce(jsonb_agg(x->'id'),'[]') from jsonb_array_elements(saved_baseline) x),
    'inserted_ids',(select coalesce(jsonb_agg(x->'connection_id'),'[]') from jsonb_array_elements(job.candidate->'changes') x));
  update extraction_projects set drawing_index=jsonb_set(drawing_index,'{management}',coalesce(drawing_index->'management','{}')||
    jsonb_build_object('audit',coalesce(drawing_index->'management'->'audit','[]')||jsonb_build_array(audit))) where id=p.id;
  return rescan_public(job);
end $$;

revoke all on function public.decide_connection_rescan(jsonb) from public,anon,authenticated;
grant execute on function public.decide_connection_rescan(jsonb) to service_role;
-- Prevent new clients from accidentally sending replacement candidates to an old merge-only RPC.
create function public.rescan_replacement_contract() returns integer
language sql stable set search_path=public,pg_temp as $$
  select case when position('Explicit replacement lists required' in pg_get_functiondef('public.decide_connection_rescan(jsonb)'::regprocedure))>0 then 1 else 0 end
$$;
revoke all on function public.rescan_replacement_contract() from public,anon,authenticated;
grant execute on function public.rescan_replacement_contract() to service_role;
notify pgrst,'reload schema';
commit;
