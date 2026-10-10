-- Production project assets and durable Agent control-plane storage.
-- The legacy public images bucket and wiring_tables table remain unchanged.

create table if not exists public.document_files (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  kind text not null default 'source_pdf'
    check (kind in ('source_pdf', 'attachment')),
  original_filename text not null,
  storage_bucket text not null default 'project-assets',
  storage_path text not null,
  checksum text not null,
  mime_type text not null,
  size_bytes bigint not null check (size_bytes > 0),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint document_files_filename_not_blank check (btrim(original_filename) <> ''),
  constraint document_files_bucket_not_blank check (btrim(storage_bucket) <> ''),
  constraint document_files_path_not_blank check (btrim(storage_path) <> ''),
  constraint document_files_checksum_not_blank check (btrim(checksum) <> ''),
  constraint document_files_mime_not_blank check (btrim(mime_type) <> ''),
  unique (storage_bucket, storage_path),
  unique (id, project_id)
);

create unique index if not exists document_files_one_source_pdf_per_project_uidx
  on public.document_files (project_id)
  where kind = 'source_pdf';

alter table public.drawings
  add column if not exists image_bucket text not null default 'project-assets';

comment on column public.document_files.storage_path is
  'Stable object key. Source PDF: projects/{project_id}/original.pdf.';
comment on column public.drawings.image_path is
  'Stable object key: projects/{project_id}/workspaces/{workspace_id}/drawings/{drawing_id}.png.';

create table if not exists public.agent_runs (
  id uuid primary key,
  idempotency_key text not null,
  request_fingerprint text not null,
  run_type text not null,
  status text not null,
  project_id uuid not null references public.projects(id) on delete cascade,
  source_document_id uuid not null,
  requested_by uuid not null references auth.users(id) on delete restrict,
  scope jsonb not null,
  feedback_id text,
  profile_hint text,
  expected_result_version integer check (expected_result_version is null or expected_result_version >= 0),
  options jsonb not null default '{}'::jsonb,
  profile jsonb,
  parent_run_id uuid references public.agent_runs(id) on delete set null,
  current_stage text,
  error jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint agent_runs_source_document_project_fk
    foreign key (source_document_id, project_id)
    references public.document_files(id, project_id)
    on delete restrict,
  constraint agent_runs_scope_object check (jsonb_typeof(scope) = 'object'),
  constraint agent_runs_options_object check (jsonb_typeof(options) = 'object'),
  constraint agent_runs_profile_object check (profile is null or jsonb_typeof(profile) = 'object'),
  constraint agent_runs_error_object check (error is null or jsonb_typeof(error) = 'object'),
  constraint agent_runs_idempotency_not_blank check (btrim(idempotency_key) <> ''),
  constraint agent_runs_fingerprint_not_blank check (btrim(request_fingerprint) <> ''),
  unique (project_id, idempotency_key)
);

create table if not exists public.agent_events (
  id uuid primary key,
  agent_run_id uuid not null references public.agent_runs(id) on delete cascade,
  seq integer not null check (seq >= 0),
  event_type text not null,
  stage text,
  level text not null default 'INFO',
  scope jsonb,
  message text not null default '',
  metrics jsonb not null default '{}'::jsonb,
  artifact_refs jsonb not null default '[]'::jsonb,
  error jsonb,
  occurred_at timestamptz not null default timezone('utc', now()),
  constraint agent_events_scope_object check (scope is null or jsonb_typeof(scope) = 'object'),
  constraint agent_events_metrics_object check (jsonb_typeof(metrics) = 'object'),
  constraint agent_events_artifact_refs_array check (jsonb_typeof(artifact_refs) = 'array'),
  constraint agent_events_error_object check (error is null or jsonb_typeof(error) = 'object'),
  unique (agent_run_id, seq)
);

create table if not exists public.agent_artifacts (
  artifact_id text primary key,
  agent_run_id uuid not null references public.agent_runs(id) on delete cascade,
  kind text not null,
  payload jsonb not null,
  storage_bucket text,
  storage_path text,
  checksum text,
  created_at timestamptz not null default timezone('utc', now()),
  constraint agent_artifacts_payload_object check (jsonb_typeof(payload) = 'object'),
  constraint agent_artifacts_id_not_blank check (btrim(artifact_id) <> ''),
  constraint agent_artifacts_kind_not_blank check (btrim(kind) <> ''),
  constraint agent_artifacts_storage_pair check (
    (storage_bucket is null and storage_path is null)
    or (storage_bucket is not null and storage_path is not null)
  )
);

create table if not exists public.result_proposals (
  id uuid primary key,
  agent_run_id uuid not null references public.agent_runs(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  status text not null,
  payload jsonb not null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint result_proposals_payload_object check (jsonb_typeof(payload) = 'object')
);

create table if not exists public.agent_checkpoints (
  checkpoint_key text primary key,
  agent_run_id uuid not null references public.agent_runs(id) on delete cascade,
  revision integer not null check (revision > 0),
  payload jsonb not null,
  updated_at timestamptz not null default timezone('utc', now()),
  constraint agent_checkpoints_key_not_blank check (btrim(checkpoint_key) <> ''),
  constraint agent_checkpoints_payload_object check (jsonb_typeof(payload) = 'object')
);

drop trigger if exists document_files_updated_at on public.document_files;
create trigger document_files_updated_at
before update on public.document_files
for each row execute function public.set_updated_at_utc();

drop trigger if exists agent_runs_updated_at on public.agent_runs;
create trigger agent_runs_updated_at
before update on public.agent_runs
for each row execute function public.set_updated_at_utc();

drop trigger if exists result_proposals_updated_at on public.result_proposals;
create trigger result_proposals_updated_at
before update on public.result_proposals
for each row execute function public.set_updated_at_utc();

create index if not exists document_files_project_idx
  on public.document_files (project_id, kind);
create index if not exists agent_runs_project_created_idx
  on public.agent_runs (project_id, created_at desc);
create index if not exists agent_runs_status_created_idx
  on public.agent_runs (status, created_at);
create index if not exists agent_events_run_seq_idx
  on public.agent_events (agent_run_id, seq);
create index if not exists agent_artifacts_run_created_idx
  on public.agent_artifacts (agent_run_id, created_at);
create index if not exists result_proposals_project_created_idx
  on public.result_proposals (project_id, created_at desc);
create index if not exists agent_checkpoints_run_idx
  on public.agent_checkpoints (agent_run_id, updated_at desc);

alter table public.document_files enable row level security;
alter table public.agent_runs enable row level security;
alter table public.agent_events enable row level security;
alter table public.agent_artifacts enable row level security;
alter table public.result_proposals enable row level security;
alter table public.agent_checkpoints enable row level security;

drop policy if exists document_files_member_read on public.document_files;
create policy document_files_member_read
on public.document_files for select to authenticated
using (public.is_project_member(project_id));

drop policy if exists agent_runs_member_read on public.agent_runs;
create policy agent_runs_member_read
on public.agent_runs for select to authenticated
using (public.is_project_member(project_id));

drop policy if exists agent_events_member_read on public.agent_events;
create policy agent_events_member_read
on public.agent_events for select to authenticated
using (
  exists (
    select 1 from public.agent_runs as run
    where run.id = agent_run_id
      and public.is_project_member(run.project_id)
  )
);

drop policy if exists agent_artifacts_member_read on public.agent_artifacts;
create policy agent_artifacts_member_read
on public.agent_artifacts for select to authenticated
using (
  exists (
    select 1 from public.agent_runs as run
    where run.id = agent_run_id
      and public.is_project_member(run.project_id)
  )
);

drop policy if exists result_proposals_member_read on public.result_proposals;
create policy result_proposals_member_read
on public.result_proposals for select to authenticated
using (public.is_project_member(project_id));

drop policy if exists agent_checkpoints_member_read on public.agent_checkpoints;
create policy agent_checkpoints_member_read
on public.agent_checkpoints for select to authenticated
using (
  exists (
    select 1 from public.agent_runs as run
    where run.id = agent_run_id
      and public.is_project_member(run.project_id)
  )
);

revoke all on public.document_files from anon;
revoke all on public.agent_runs from anon;
revoke all on public.agent_events from anon;
revoke all on public.agent_artifacts from anon;
revoke all on public.result_proposals from anon;
revoke all on public.agent_checkpoints from anon, authenticated;

grant select on public.document_files to authenticated;
grant select on public.agent_runs to authenticated;
grant select on public.agent_events to authenticated;
grant select on public.agent_artifacts to authenticated;
grant select on public.result_proposals to authenticated;

grant all on public.document_files to service_role;
grant all on public.agent_runs to service_role;
grant all on public.agent_events to service_role;
grant all on public.agent_artifacts to service_role;
grant all on public.result_proposals to service_role;
grant all on public.agent_checkpoints to service_role;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'project-assets',
  'project-assets',
  false,
  524288000,
  array[
    'application/pdf',
    'image/png',
    'image/jpeg',
    'application/json',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  ]
)
on conflict (id) do update
set public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists project_assets_member_read on storage.objects;
create policy project_assets_member_read
on storage.objects for select to authenticated
using (
  bucket_id = 'project-assets'
  and (storage.foldername(name))[1] = 'projects'
  and exists (
    select 1 from public.projects as project
    where project.id::text = (storage.foldername(name))[2]
      and public.is_project_member(project.id)
  )
);

-- Browser writes are intentionally absent. The business API/Agent service use
-- a service-role credential, which bypasses RLS, after validating project scope.

-- Rollback is intentionally manual because runtime rows and private objects may
-- already be referenced. Remove the policy/bucket only after deleting objects,
-- then drop agent_checkpoints, result_proposals, agent_artifacts, agent_events,
-- agent_runs and document_files; finally remove drawings.image_bucket.
