-- Model calls may use UUID Agent run ids or logical improvement/candidate keys.

drop policy if exists agent_traces_member_read on public.agent_traces;
drop function if exists public.append_agent_trace(uuid, jsonb);

alter table public.agent_traces
  drop constraint if exists agent_traces_agent_run_id_fkey;

alter table public.agent_traces
  rename column agent_run_id to run_key;

alter table public.agent_traces
  alter column run_key type text using run_key::text;

alter table public.agent_traces
  add column if not exists project_id uuid references public.projects(id) on delete cascade;

update public.agent_traces as trace
set project_id = run.project_id
from public.agent_runs as run
where trace.run_key = run.id::text and trace.project_id is null;

drop index if exists public.agent_traces_run_seq_idx;
create index if not exists agent_traces_run_key_seq_idx
  on public.agent_traces (run_key, seq);
create index if not exists agent_traces_project_created_idx
  on public.agent_traces (project_id, created_at desc)
  where project_id is not null;

create policy agent_traces_member_read
on public.agent_traces for select to authenticated
using (project_id is not null and public.is_project_member(project_id));

create or replace function public.append_agent_trace(
  target_run_id text,
  payload_value jsonb
)
returns integer
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  next_seq integer;
  target_project uuid;
begin
  perform pg_advisory_xact_lock(hashtextextended(target_run_id, 0));
  select project_id into target_project
  from public.agent_runs where id::text = target_run_id;
  select coalesce(max(seq), -1) + 1 into next_seq
  from public.agent_traces where run_key = target_run_id;
  insert into public.agent_traces (run_key, project_id, seq, payload)
  values (target_run_id, target_project, next_seq, payload_value);
  return next_seq;
end;
$$;

revoke all on function public.append_agent_trace(text, jsonb) from public;
grant execute on function public.append_agent_trace(text, jsonb) to service_role;
