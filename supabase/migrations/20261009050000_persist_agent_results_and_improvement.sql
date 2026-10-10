-- Persist normalized Agent results, correction feedback, traces and Profile improvement state.

alter table public.result_proposals
  alter column id type text using id::text;

alter table public.result_proposals
  add column if not exists committed_result_version_id uuid
    references public.result_versions(id) on delete set null,
  add column if not exists committed_at timestamptz,
  add column if not exists confirmed_by uuid references auth.users(id) on delete set null;

alter table public.result_versions
  add column if not exists source_proposal_id text,
  add column if not exists profile jsonb,
  add column if not exists model jsonb,
  add column if not exists confirmed_by uuid references auth.users(id) on delete set null;

create unique index if not exists result_versions_source_proposal_uidx
  on public.result_versions (source_proposal_id)
  where source_proposal_id is not null;

alter table public.wiring_connections
  add column if not exists record_version integer not null default 1
    check (record_version > 0);

create table if not exists public.feedback_items (
  id text primary key,
  project_id uuid not null references public.projects(id) on delete cascade,
  target_type text not null check (target_type in ('CONNECTION', 'DRAWING', 'WORKSPACE', 'PROJECT')),
  target_id text not null,
  target_field text,
  issue_kind text not null,
  status text not null default 'prepared'
    check (status in ('prepared', 'proposal_ready', 'accepted', 'rejected')),
  requested_by uuid references auth.users(id) on delete set null,
  base_result_version integer not null check (base_result_version >= 0),
  base_result_version_id uuid references public.result_versions(id) on delete set null,
  proposal_id text references public.result_proposals(id) on delete set null,
  committed_result_version_id uuid references public.result_versions(id) on delete set null,
  correction_bundle jsonb not null,
  before_value jsonb,
  after_value jsonb,
  accepted_payload jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  accepted_at timestamptz,
  constraint feedback_items_id_not_blank check (btrim(id) <> ''),
  constraint feedback_items_target_not_blank check (btrim(target_id) <> ''),
  constraint feedback_items_bundle_object check (jsonb_typeof(correction_bundle) = 'object'),
  constraint feedback_items_accepted_object
    check (accepted_payload is null or jsonb_typeof(accepted_payload) = 'object')
);

create table if not exists public.agent_traces (
  id bigint generated always as identity primary key,
  agent_run_id uuid not null references public.agent_runs(id) on delete cascade,
  seq integer not null check (seq >= 0),
  payload jsonb not null,
  created_at timestamptz not null default timezone('utc', now()),
  constraint agent_traces_payload_object check (jsonb_typeof(payload) = 'object'),
  unique (agent_run_id, seq)
);

create table if not exists public.profile_candidates (
  id text primary key,
  profile_key text not null,
  profile_version text not null,
  status text not null,
  payload jsonb not null,
  gate_passed boolean not null default false,
  gate_decision jsonb,
  previous_active_candidate_id text references public.profile_candidates(id) on delete set null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint profile_candidates_payload_object check (jsonb_typeof(payload) = 'object'),
  constraint profile_candidates_gate_object
    check (gate_decision is null or jsonb_typeof(gate_decision) = 'object')
);

create unique index if not exists profile_candidates_one_active_uidx
  on public.profile_candidates (profile_key)
  where status = 'ACTIVE';

create table if not exists public.profile_candidate_reviews (
  id bigint generated always as identity primary key,
  candidate_id text not null references public.profile_candidates(id) on delete cascade,
  reviewer_id text not null,
  action text not null,
  created_at timestamptz not null default timezone('utc', now()),
  constraint profile_candidate_reviews_reviewer_not_blank check (btrim(reviewer_id) <> '')
);

create table if not exists public.profile_candidate_audit (
  id bigint generated always as identity primary key,
  candidate_id text not null references public.profile_candidates(id) on delete cascade,
  action text not null,
  from_status text,
  to_status text,
  reviewer_id text,
  payload jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default timezone('utc', now()),
  constraint profile_candidate_audit_payload_object check (jsonb_typeof(payload) = 'object')
);

create table if not exists public.evaluation_reports (
  id text primary key,
  candidate_id text not null references public.profile_candidates(id) on delete cascade,
  payload jsonb not null,
  created_at timestamptz not null default timezone('utc', now()),
  constraint evaluation_reports_payload_object check (jsonb_typeof(payload) = 'object')
);

drop trigger if exists feedback_items_updated_at on public.feedback_items;
create trigger feedback_items_updated_at
before update on public.feedback_items
for each row execute function public.set_updated_at_utc();

drop trigger if exists profile_candidates_updated_at on public.profile_candidates;
create trigger profile_candidates_updated_at
before update on public.profile_candidates
for each row execute function public.set_updated_at_utc();

create index if not exists feedback_items_project_created_idx
  on public.feedback_items (project_id, created_at desc);
create index if not exists feedback_items_target_idx
  on public.feedback_items (target_type, target_id, created_at desc);
create index if not exists agent_traces_run_seq_idx
  on public.agent_traces (agent_run_id, seq);
create index if not exists profile_candidates_profile_created_idx
  on public.profile_candidates (profile_key, created_at desc);
create index if not exists profile_candidate_audit_candidate_idx
  on public.profile_candidate_audit (candidate_id, occurred_at);
create index if not exists evaluation_reports_candidate_idx
  on public.evaluation_reports (candidate_id, created_at desc);

alter table public.feedback_items enable row level security;
alter table public.agent_traces enable row level security;
alter table public.profile_candidates enable row level security;
alter table public.profile_candidate_reviews enable row level security;
alter table public.profile_candidate_audit enable row level security;
alter table public.evaluation_reports enable row level security;

create policy feedback_items_member_read
on public.feedback_items for select to authenticated
using (public.is_project_member(project_id));

create policy agent_traces_member_read
on public.agent_traces for select to authenticated
using (
  exists (
    select 1 from public.agent_runs as run
    where run.id = agent_run_id and public.is_project_member(run.project_id)
  )
);

revoke all on public.feedback_items from anon;
revoke all on public.agent_traces from anon;
revoke all on public.profile_candidates from anon, authenticated;
revoke all on public.profile_candidate_reviews from anon, authenticated;
revoke all on public.profile_candidate_audit from anon, authenticated;
revoke all on public.evaluation_reports from anon, authenticated;

grant select on public.feedback_items to authenticated;
grant select on public.agent_traces to authenticated;
grant all on public.feedback_items to service_role;
grant all on public.agent_traces to service_role;
grant all on public.profile_candidates to service_role;
grant all on public.profile_candidate_reviews to service_role;
grant all on public.profile_candidate_audit to service_role;
grant all on public.evaluation_reports to service_role;

create or replace function public.append_agent_trace(
  target_run_id uuid,
  payload_value jsonb
)
returns integer
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  next_seq integer;
begin
  perform pg_advisory_xact_lock(hashtextextended(target_run_id::text, 0));
  select coalesce(max(seq), -1) + 1 into next_seq
  from public.agent_traces where agent_run_id = target_run_id;
  insert into public.agent_traces (agent_run_id, seq, payload)
  values (target_run_id, next_seq, payload_value);
  return next_seq;
end;
$$;

create or replace function public.commit_wiring_result(
  proposal_key text,
  target_project_id uuid,
  target_agent_run_id uuid,
  created_by_user uuid,
  expected_base_version integer,
  target_status text,
  profile_value jsonb,
  model_value jsonb,
  units_value jsonb,
  feedback_updates jsonb default '[]'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  current_version integer;
  new_version integer;
  result_id uuid;
  existing_result record;
  unit_value jsonb;
  connection_value jsonb;
  evidence_value jsonb;
  feedback_value jsonb;
  unit_id uuid;
  connection_id uuid;
  accepted_value jsonb;
begin
  if target_status not in ('draft', 'needs_review', 'accepted') then
    raise exception 'invalid result status';
  end if;
  if jsonb_typeof(units_value) <> 'array' or jsonb_typeof(feedback_updates) <> 'array' then
    raise exception 'units and feedback updates must be arrays';
  end if;

  perform 1 from public.projects where id = target_project_id for update;
  if not found then raise exception 'project not found'; end if;

  select id, version into existing_result
  from public.result_versions where source_proposal_id = proposal_key;
  if found then
    return jsonb_build_object(
      'result_version_id', existing_result.id,
      'result_version', existing_result.version,
      'idempotent', true
    );
  end if;

  if not exists (
    select 1 from public.result_proposals
    where id = proposal_key and project_id = target_project_id and agent_run_id = target_agent_run_id
  ) then
    raise exception 'proposal does not belong to project/run';
  end if;

  select coalesce(max(version), 0) into current_version
  from public.result_versions where project_id = target_project_id;
  if current_version <> expected_base_version then
    raise exception 'base result version conflict';
  end if;
  new_version := current_version + 1;

  if target_status = 'accepted' then
    update public.result_versions set status = 'superseded'
    where project_id = target_project_id and status = 'accepted';
  end if;

  insert into public.result_versions (
    project_id, version, agent_run_id, status, created_by,
    source_proposal_id, profile, model, confirmed_by
  ) values (
    target_project_id, new_version, target_agent_run_id::text, target_status, created_by_user,
    proposal_key, profile_value, model_value,
    case when target_status = 'accepted' then created_by_user else null end
  ) returning id into result_id;

  for unit_value in select value from jsonb_array_elements(units_value)
  loop
    insert into public.wiring_units (
      project_id, result_version_id, workspace_id, drawing_id,
      voltage_level, terminal_strip, status, needs_review, raw_payload
    ) values (
      target_project_id,
      result_id,
      (unit_value->>'workspace_id')::uuid,
      nullif(unit_value->>'drawing_id', '')::uuid,
      nullif(unit_value->>'voltage_level', ''),
      nullif(unit_value->>'terminal_strip', ''),
      coalesce(nullif(unit_value->>'status', ''), 'extracted'),
      coalesce((unit_value->>'needs_review')::boolean, false),
      coalesce(unit_value->'raw_payload', '{}'::jsonb)
    ) returning id into unit_id;

    for connection_value in
      select value from jsonb_array_elements(coalesce(unit_value->'connections', '[]'::jsonb))
    loop
      insert into public.wiring_connections (
        wiring_unit_id, source_drawing_id, core_order, principle_number,
        start_code, start_description, start_terminal,
        end_code, end_description, end_terminal,
        current_value, remark, color_mark, is_cross_page,
        confidence, status, needs_review, raw_payload, record_version
      ) values (
        unit_id,
        nullif(connection_value->>'source_drawing_id', '')::uuid,
        (connection_value->>'core_order')::integer,
        nullif(connection_value->>'principle_number', ''),
        nullif(connection_value->>'start_code', ''),
        nullif(connection_value->>'start_description', ''),
        nullif(connection_value->>'start_terminal', ''),
        nullif(connection_value->>'end_code', ''),
        nullif(connection_value->>'end_description', ''),
        nullif(connection_value->>'end_terminal', ''),
        nullif(connection_value->>'current_value', ''),
        nullif(connection_value->>'remark', ''),
        nullif(connection_value->>'color_mark', ''),
        coalesce(nullif(connection_value->>'is_cross_page', ''), 'unknown'),
        nullif(connection_value->>'confidence', '')::numeric,
        coalesce(nullif(connection_value->>'status', ''), 'extracted'),
        coalesce((connection_value->>'needs_review')::boolean, false),
        coalesce(connection_value->'raw_payload', '{}'::jsonb),
        coalesce((connection_value->>'record_version')::integer, 1)
      ) returning id into connection_id;

      for evidence_value in
        select value from jsonb_array_elements(coalesce(connection_value->'evidence', '[]'::jsonb))
      loop
        insert into public.connection_evidence (
          connection_id, drawing_id, kind, bbox, raw_text
        ) values (
          connection_id,
          (evidence_value->>'drawing_id')::uuid,
          evidence_value->>'kind',
          evidence_value->'bbox',
          evidence_value->>'raw_text'
        );
      end loop;
    end loop;
  end loop;

  for feedback_value in select value from jsonb_array_elements(feedback_updates)
  loop
    accepted_value := jsonb_set(
      coalesce(feedback_value->'accepted_payload', '{}'::jsonb),
      '{result_version_id}', to_jsonb(result_id::text), true
    );
    update public.feedback_items
    set status = 'accepted',
        proposal_id = proposal_key,
        committed_result_version_id = result_id,
        before_value = feedback_value->'before',
        after_value = feedback_value->'after',
        accepted_payload = accepted_value,
        accepted_at = timezone('utc', now())
    where id = feedback_value->>'feedback_id' and project_id = target_project_id;
    if not found then raise exception 'feedback item not found'; end if;
  end loop;

  update public.result_proposals
  set committed_result_version_id = result_id,
      committed_at = timezone('utc', now()),
      confirmed_by = case when target_status = 'accepted' then created_by_user else null end
  where id = proposal_key;

  return jsonb_build_object(
    'result_version_id', result_id,
    'result_version', new_version,
    'idempotent', false
  );
end;
$$;

create or replace function public.transition_profile_candidate(
  candidate_key text,
  target_status text,
  reviewer text default null,
  action_value text default 'transition'
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  candidate_row public.profile_candidates%rowtype;
  active_row public.profile_candidates%rowtype;
  previous_row public.profile_candidates%rowtype;
  old_status text;
begin
  select * into candidate_row from public.profile_candidates
  where id = candidate_key for update;
  if not found then raise exception 'candidate not found'; end if;
  old_status := candidate_row.status;

  if action_value = 'rollback' then
    if candidate_row.status not in ('CANARY', 'ACTIVE') then raise exception 'invalid rollback'; end if;
    if reviewer is null or btrim(reviewer) = '' then raise exception 'reviewer required'; end if;
    target_status := 'ROLLED_BACK';
  elsif not (
    (candidate_row.status = 'DRAFT' and target_status in ('EVALUATING', 'REJECTED')) or
    (candidate_row.status = 'EVALUATING' and target_status in ('REJECTED', 'APPROVED')) or
    (candidate_row.status = 'APPROVED' and target_status = 'CANARY') or
    (candidate_row.status = 'CANARY' and target_status in ('ACTIVE', 'ROLLED_BACK')) or
    (candidate_row.status = 'ACTIVE' and target_status in ('RETIRED', 'ROLLED_BACK'))
  ) then
    raise exception 'invalid candidate transition';
  end if;

  if target_status in ('APPROVED', 'CANARY') and (reviewer is null or btrim(reviewer) = '') then
    raise exception 'reviewer required';
  end if;
  if target_status = 'APPROVED' and not candidate_row.gate_passed then
    raise exception 'candidate has not passed release gate';
  end if;
  if reviewer is not null and btrim(reviewer) <> '' then
    insert into public.profile_candidate_reviews (candidate_id, reviewer_id, action)
    values (candidate_key, reviewer, action_value);
  end if;

  if target_status = 'ACTIVE' then
    if not exists (select 1 from public.profile_candidate_reviews where candidate_id = candidate_key) then
      raise exception 'human review required';
    end if;
    select * into active_row from public.profile_candidates
    where profile_key = candidate_row.profile_key and status = 'ACTIVE' and id <> candidate_key
    for update;
    if found then
      update public.profile_candidates
      set status = 'RETIRED', payload = jsonb_set(payload, '{status}', '"RETIRED"'::jsonb)
      where id = active_row.id;
      update public.profile_candidates set previous_active_candidate_id = active_row.id
      where id = candidate_key;
    end if;
  elsif target_status = 'ROLLED_BACK' and candidate_row.status = 'ACTIVE'
        and candidate_row.previous_active_candidate_id is not null then
    select * into previous_row from public.profile_candidates
    where id = candidate_row.previous_active_candidate_id for update;
    if found then
      update public.profile_candidates
      set status = 'ACTIVE', payload = jsonb_set(payload, '{status}', '"ACTIVE"'::jsonb)
      where id = previous_row.id;
    end if;
  end if;

  update public.profile_candidates
  set status = target_status,
      payload = jsonb_set(payload, '{status}', to_jsonb(target_status), true)
  where id = candidate_key
  returning * into candidate_row;

  insert into public.profile_candidate_audit (
    candidate_id, action, from_status, to_status, reviewer_id
  ) values (
    candidate_key, action_value, old_status, target_status, reviewer
  );
  return candidate_row.payload;
end;
$$;

revoke all on function public.append_agent_trace(uuid, jsonb) from public;
revoke all on function public.commit_wiring_result(text, uuid, uuid, uuid, integer, text, jsonb, jsonb, jsonb, jsonb) from public;
revoke all on function public.transition_profile_candidate(text, text, text, text) from public;
grant execute on function public.append_agent_trace(uuid, jsonb) to service_role;
grant execute on function public.commit_wiring_result(text, uuid, uuid, uuid, integer, text, jsonb, jsonb, jsonb, jsonb) to service_role;
grant execute on function public.transition_profile_candidate(text, text, text, text) to service_role;

drop view if exists public.wiring_connection_rows;

create view public.wiring_connection_rows
with (security_invoker = true)
as
select
  connection.id as connection_id,
  project.id as project_id,
  project.name as project_name,
  workspace.id as workspace_id,
  workspace.name as workspace_name,
  drawing.id as drawing_id,
  drawing.workspace_page,
  drawing.pdf_page_number,
  result_version.id as result_version_id,
  result_version.version as result_version,
  result_version.status as result_status,
  unit.id as wiring_unit_id,
  unit.wire_number,
  connection.principle_number,
  unit.voltage_level,
  unit.terminal_strip,
  connection.start_code,
  connection.start_description,
  connection.start_terminal,
  connection.end_code,
  connection.end_description,
  connection.end_terminal,
  connection.current_value,
  connection.remark,
  connection.color_mark,
  connection.core_order,
  connection.confidence,
  connection.status,
  connection.needs_review,
  connection.record_version,
  connection.created_at,
  connection.updated_at,
  connection.is_cross_page,
  source_document.id as source_document_id
from public.wiring_connections as connection
join public.wiring_units as unit on unit.id = connection.wiring_unit_id
join public.result_versions as result_version on result_version.id = unit.result_version_id
join public.projects as project on project.id = unit.project_id
join public.workspaces as workspace on workspace.id = unit.workspace_id
left join public.drawings as drawing
  on drawing.id = coalesce(connection.source_drawing_id, unit.drawing_id)
left join lateral (
  select document.id from public.document_files as document
  where document.project_id = project.id and document.kind = 'source_pdf'
  order by document.created_at desc limit 1
) as source_document on true;

grant select on public.wiring_connection_rows to authenticated, service_role;
