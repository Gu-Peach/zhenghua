-- Retry state must not ambiguously refer to the queue.attempts column.
create or replace function public.gate_a_base_lease_action(target uuid,token jsonb,action text,value jsonb default '{}')
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare r public.agent_runs; receipt jsonb; retry_attempt integer; failure_id text;
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
    select q.attempts into retry_attempt from public.agent_run_queue q where q.agent_run_id=target;
    failure_id:=target::text||':lease-failure:'||r.lease_generation;
    insert into public.agent_artifacts(artifact_id,agent_run_id,kind,payload)
      values(failure_id,target,'gate_a_attempt',jsonb_build_object('attempt',retry_attempt,
        'error',value->'error','retryable',value->'retryable')) on conflict(artifact_id) do nothing;
    if coalesce((value->>'retryable')::boolean,false) and retry_attempt<4 then
      update public.agent_runs set status='QUEUED',error=value->'error' where id=target;
      update public.agent_run_queue set available_at=now()+make_interval(secs=>least(60,2^retry_attempt)::int),
        leased_by=null,leased_at=null,lease_expires_at=null where agent_run_id=target;
    else
      update public.agent_runs set status='FAILED',error=value->'error' where id=target;
      perform public.gate_a_event(target,'failed:'||r.lease_generation,'RUN_FAILED',r.current_stage,
        '[]',jsonb_build_object('attempt',retry_attempt));
      delete from public.agent_run_queue where agent_run_id=target;
    end if;
  else raise exception 'unknown lease action'; end if;
  return '{}';
end $$;
notify pgrst,'reload schema';
