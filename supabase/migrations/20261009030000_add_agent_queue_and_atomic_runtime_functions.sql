-- Durable queue leases and atomic Agent event/checkpoint writes.

create table if not exists public.agent_run_queue (
  agent_run_id uuid primary key references public.agent_runs(id) on delete cascade,
  available_at timestamptz not null default timezone('utc', now()),
  leased_at timestamptz,
  leased_by text,
  attempts integer not null default 0 check (attempts >= 0),
  created_at timestamptz not null default timezone('utc', now()),
  constraint agent_run_queue_lease_pair check (
    (leased_at is null and leased_by is null)
    or (leased_at is not null and leased_by is not null)
  )
);

create index if not exists agent_run_queue_available_idx
  on public.agent_run_queue (available_at, created_at);

alter table public.agent_run_queue enable row level security;
revoke all on public.agent_run_queue from anon, authenticated;
grant all on public.agent_run_queue to service_role;

create or replace function public.claim_agent_run(
  worker_id text,
  lease_seconds integer default 300
)
returns uuid
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  claimed_run_id uuid;
begin
  if btrim(worker_id) = '' then
    raise exception 'worker_id is required';
  end if;
  if lease_seconds < 1 then
    raise exception 'lease_seconds must be positive';
  end if;

  with candidate as (
    select queue.agent_run_id
    from public.agent_run_queue as queue
    where queue.available_at <= timezone('utc', now())
      and (
        queue.leased_at is null
        or queue.leased_at < timezone('utc', now()) - make_interval(secs => lease_seconds)
      )
    order by queue.available_at, queue.created_at
    for update skip locked
    limit 1
  )
  update public.agent_run_queue as queue
     set leased_at = timezone('utc', now()),
         leased_by = worker_id,
         attempts = queue.attempts + 1
    from candidate
   where queue.agent_run_id = candidate.agent_run_id
  returning queue.agent_run_id into claimed_run_id;

  return claimed_run_id;
end;
$$;

create or replace function public.append_agent_event(
  event_id uuid,
  target_run_id uuid,
  event_type_value text,
  stage_value text,
  level_value text,
  scope_value jsonb,
  message_value text,
  metrics_value jsonb,
  artifact_refs_value jsonb,
  error_value jsonb,
  occurred_at_value timestamptz
)
returns integer
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  next_seq integer;
  existing_seq integer;
begin
  select event.seq into existing_seq
  from public.agent_events as event
  where event.id = event_id;
  if found then
    return existing_seq;
  end if;

  perform pg_advisory_xact_lock(hashtextextended(target_run_id::text, 0));
  select coalesce(max(event.seq), -1) + 1 into next_seq
  from public.agent_events as event
  where event.agent_run_id = target_run_id;

  insert into public.agent_events (
    id,
    agent_run_id,
    seq,
    event_type,
    stage,
    level,
    scope,
    message,
    metrics,
    artifact_refs,
    error,
    occurred_at
  )
  values (
    event_id,
    target_run_id,
    next_seq,
    event_type_value,
    stage_value,
    coalesce(level_value, 'INFO'),
    scope_value,
    coalesce(message_value, ''),
    coalesce(metrics_value, '{}'::jsonb),
    coalesce(artifact_refs_value, '[]'::jsonb),
    error_value,
    coalesce(occurred_at_value, timezone('utc', now()))
  );

  return next_seq;
end;
$$;

create or replace function public.save_agent_checkpoint(
  target_key text,
  target_run_id uuid,
  payload_value jsonb,
  expected_revision integer default null
)
returns integer
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  current_revision integer;
  next_revision integer;
begin
  perform pg_advisory_xact_lock(hashtextextended(target_key, 0));
  select checkpoint.revision into current_revision
  from public.agent_checkpoints as checkpoint
  where checkpoint.checkpoint_key = target_key;
  current_revision := coalesce(current_revision, 0);

  if expected_revision is not null and expected_revision <> current_revision then
    raise exception 'checkpoint revision mismatch: expected %, got %',
      expected_revision, current_revision
      using errcode = '40001';
  end if;

  next_revision := current_revision + 1;
  insert into public.agent_checkpoints (
    checkpoint_key,
    agent_run_id,
    revision,
    payload,
    updated_at
  )
  values (
    target_key,
    target_run_id,
    next_revision,
    payload_value,
    timezone('utc', now())
  )
  on conflict (checkpoint_key) do update
    set revision = excluded.revision,
        payload = excluded.payload,
        updated_at = excluded.updated_at;

  return next_revision;
end;
$$;

revoke all on function public.claim_agent_run(text, integer) from public;
revoke all on function public.append_agent_event(
  uuid, uuid, text, text, text, jsonb, text, jsonb, jsonb, jsonb, timestamptz
) from public;
revoke all on function public.save_agent_checkpoint(text, uuid, jsonb, integer) from public;

grant execute on function public.claim_agent_run(text, integer) to service_role;
grant execute on function public.append_agent_event(
  uuid, uuid, text, text, text, jsonb, text, jsonb, jsonb, jsonb, timestamptz
) to service_role;
grant execute on function public.save_agent_checkpoint(text, uuid, jsonb, integer) to service_role;
