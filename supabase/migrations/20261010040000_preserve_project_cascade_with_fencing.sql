-- Parent project deletion is a domain operation; its FK cascade must not
-- be confused with an unfenced worker write to an existing project.
create or replace function public.gate_a_guard() returns trigger
language plpgsql security definer set search_path=public,pg_temp as $$
declare rid uuid; version integer; generation bigint; state text; project uuid;
begin
  if tg_table_name='agent_runs' then rid:=new.id;
  elsif tg_table_name='result_versions' then
    begin rid:=new.agent_run_id::uuid; exception when invalid_text_representation then return new; end;
  else rid:=new.agent_run_id; end if;
  select protocol_version,lease_generation,status,project_id into version,generation,state,project
    from public.agent_runs where id=rid;
  if project is not null and not exists(select 1 from public.projects where id=project) then return new; end if;
  if version=2 and current_setting('gate_a.authorized',true) is distinct from rid::text then
    if tg_table_name='agent_events' then
      if new.event_type='RUN_CREATED' and generation=0 and state='QUEUED' then return new; end if;
    end if;
    raise exception 'protocol 2 requires fenced mutation' using errcode='42501';
  end if;
  return new;
end $$;
create or replace function public.gate_a_queue_guard() returns trigger
language plpgsql security definer set search_path=public,pg_temp as $$
declare rid uuid;
begin
  rid:=case when tg_op='DELETE' then old.agent_run_id else new.agent_run_id end;
  if exists(select 1 from public.agent_runs r join public.projects p on p.id=r.project_id
      where r.id=rid and r.protocol_version=2)
    and current_setting('gate_a.authorized',true) is distinct from rid::text then
    raise exception 'durable queue requires fencing' using errcode='42501';
  end if;
  if tg_op='DELETE' then return old; end if; return new;
end $$;
notify pgrst,'reload schema';
