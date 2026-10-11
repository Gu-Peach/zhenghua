alter function public.gate_a_commit_item(uuid,jsonb,jsonb,boolean) rename to gate_a_base_commit_item;
create function public.gate_a_commit_item(target uuid,token jsonb,item jsonb,model_cache boolean default false)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare r public.agent_runs; semantic jsonb; receipt jsonb; aid text; fingerprint text; upstream text;
  root_digest text; upstream_digest text;
begin
  r:=public.gate_a_lock(target,token);
  semantic:=item-'attempt'-'created_at'-'metrics';
  select checksum into root_digest from public.agent_artifacts where artifact_id=target::text||':durable-input';
  upstream:=case item->>'stage' when 'RENDER' then null when 'PAGE_CLASSIFICATION' then 'RENDER'
    when 'PAGE_SCAN' then 'PAGE_CLASSIFICATION' when 'BUILD_CROSS_PAGE_TASKS' then 'PAGE_SCAN'
    when 'CROSS_PAGE_COMPLETION' then 'BUILD_CROSS_PAGE_TASKS' when 'VALIDATION' then 'CROSS_PAGE_COMPLETION' end;
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
revoke all on function public.gate_a_commit_item(uuid,jsonb,jsonb,boolean) from public,anon,authenticated;
grant execute on function public.gate_a_commit_item(uuid,jsonb,jsonb,boolean) to service_role;
notify pgrst,'reload schema';
