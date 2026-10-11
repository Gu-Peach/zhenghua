-- Follow-up to the applied Gate A migration: admission events and pause.
create or replace function public.gate_a_guard() returns trigger
language plpgsql security definer set search_path=public,pg_temp as $$
declare rid uuid; version integer; generation bigint; state text;
begin
  if tg_table_name='agent_runs' then rid:=new.id;
  elsif tg_table_name='result_versions' then
    begin rid:=new.agent_run_id::uuid; exception when invalid_text_representation then return new; end;
  else rid:=new.agent_run_id; end if;
  select protocol_version,lease_generation,status into version,generation,state from public.agent_runs where id=rid;
  if version=2 and current_setting('gate_a.authorized',true) is distinct from rid::text then
    if tg_table_name='agent_events' then
      if new.event_type='RUN_CREATED' and generation=0 and state='QUEUED' then return new; end if;
    end if;
    raise exception 'protocol 2 requires fenced mutation' using errcode='42501';
  end if;
  return new;
end $$;
alter function public.gate_a_lease_action(uuid,jsonb,text,jsonb) rename to gate_a_base_lease_action;
create function public.gate_a_lease_action(target uuid,token jsonb,action text,value jsonb default '{}')
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare r public.agent_runs;
begin
  if action<>'pause' then return public.gate_a_base_lease_action(target,token,action,value); end if;
  r:=public.gate_a_lock(target,token);
  if value->>'status'<>'WAITING_INPUT' then raise exception 'invalid pause status'; end if;
  update public.agent_runs set status='WAITING_INPUT' where id=target;
  perform public.gate_a_event(target,'waiting:'||r.lease_generation,'HUMAN_INPUT_REQUIRED',r.current_stage);
  return '{}';
end $$;
revoke all on function public.gate_a_lease_action(uuid,jsonb,text,jsonb) from public,anon,authenticated;
grant execute on function public.gate_a_lease_action(uuid,jsonb,text,jsonb) to service_role;
alter table public.projects add constraint project_classification_snapshot_fk
  foreign key(published_classification_snapshot_id) references public.agent_artifacts(artifact_id) on delete set null;
create index drawings_classification_snapshot_idx on public.drawings(project_id,classification_snapshot_id);
notify pgrst,'reload schema';
