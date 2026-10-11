-- A lost lease is a logical fencing rejection, not a serialization failure.
-- PT409 gives PostgREST a permanent HTTP 409 without transaction retry loops.
create or replace function public.gate_a_lock(target uuid,token jsonb,allow_terminal boolean default false)
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
    raise exception 'lease lost' using errcode='PT409';
  end if;
  if not allow_terminal and r.status<>'RUNNING' then
    raise exception 'run is not running' using errcode='PT409';
  end if;
  perform set_config('gate_a.authorized',target::text,true);
  return r;
end $$;
notify pgrst,'reload schema';
