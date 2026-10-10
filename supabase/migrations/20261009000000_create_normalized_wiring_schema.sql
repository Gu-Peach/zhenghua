-- Normalized project and wiring-result schema.
-- The legacy public.wiring_tables table is intentionally left unchanged.

create table if not exists public.projects (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete restrict,
  name text not null,
  standard_profile text,
  status text not null default 'draft'
    check (status in ('draft', 'processing', 'ready', 'failed', 'archived')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint projects_name_not_blank check (btrim(name) <> '')
);

create table if not exists public.project_members (
  project_id uuid not null references public.projects(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in ('owner', 'editor', 'viewer')),
  created_at timestamptz not null default timezone('utc', now()),
  primary key (project_id, user_id)
);

create table if not exists public.workspaces (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  code text,
  name text not null,
  sort_order integer not null default 0 check (sort_order >= 0),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint workspaces_name_not_blank check (btrim(name) <> ''),
  constraint workspaces_code_not_blank check (code is null or btrim(code) <> ''),
  unique (id, project_id)
);

create unique index if not exists workspaces_project_code_uidx
  on public.workspaces (project_id, code)
  where code is not null;

create table if not exists public.drawings (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null,
  workspace_id uuid not null,
  pdf_page_number integer not null check (pdf_page_number > 0),
  workspace_page text,
  image_path text,
  status text not null default 'pending'
    check (status in ('pending', 'classified', 'scanned', 'needs_review', 'failed')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint drawings_workspace_page_not_blank
    check (workspace_page is null or btrim(workspace_page) <> ''),
  constraint drawings_workspace_project_fk
    foreign key (workspace_id, project_id)
    references public.workspaces(id, project_id)
    on delete cascade,
  unique (workspace_id, pdf_page_number),
  unique (id, workspace_id, project_id)
);

create unique index if not exists drawings_workspace_business_page_uidx
  on public.drawings (workspace_id, workspace_page)
  where workspace_page is not null;

create table if not exists public.result_versions (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  version integer not null check (version > 0),
  agent_run_id text,
  status text not null default 'draft'
    check (status in ('draft', 'needs_review', 'accepted', 'superseded', 'rejected')),
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default timezone('utc', now()),
  constraint result_versions_agent_run_not_blank
    check (agent_run_id is null or btrim(agent_run_id) <> ''),
  unique (project_id, version),
  unique (id, project_id)
);

create unique index if not exists result_versions_one_accepted_per_project_uidx
  on public.result_versions (project_id)
  where status = 'accepted';

create table if not exists public.result_wire_number_counters (
  result_version_id uuid primary key
    references public.result_versions(id) on delete cascade,
  next_wire_number integer not null default 1000
    check (next_wire_number >= 1000),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.wiring_units (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null,
  result_version_id uuid not null,
  workspace_id uuid not null,
  drawing_id uuid,
  wire_number integer not null,
  voltage_level text,
  terminal_strip text,
  status text not null default 'extracted'
    check (status in ('extracted', 'needs_review', 'confirmed', 'rejected')),
  needs_review boolean not null default false,
  raw_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint wiring_units_wire_number_min check (wire_number >= 1000),
  constraint wiring_units_voltage_level_not_blank
    check (voltage_level is null or btrim(voltage_level) <> ''),
  constraint wiring_units_terminal_strip_not_blank
    check (terminal_strip is null or btrim(terminal_strip) <> ''),
  constraint wiring_units_raw_payload_object
    check (jsonb_typeof(raw_payload) = 'object'),
  constraint wiring_units_result_project_fk
    foreign key (result_version_id, project_id)
    references public.result_versions(id, project_id)
    on delete cascade,
  constraint wiring_units_workspace_project_fk
    foreign key (workspace_id, project_id)
    references public.workspaces(id, project_id)
    on delete restrict,
  constraint wiring_units_drawing_scope_fk
    foreign key (drawing_id, workspace_id, project_id)
    references public.drawings(id, workspace_id, project_id)
    on delete restrict,
  unique (result_version_id, wire_number)
);

create unique index if not exists wiring_units_terminal_strip_uidx
  on public.wiring_units (result_version_id, workspace_id, terminal_strip)
  where terminal_strip is not null;

create table if not exists public.wiring_connections (
  id uuid primary key default gen_random_uuid(),
  wiring_unit_id uuid not null references public.wiring_units(id) on delete cascade,
  source_drawing_id uuid references public.drawings(id) on delete restrict,
  core_order integer not null check (core_order > 0),
  principle_number text,
  start_code text,
  start_description text,
  start_terminal text,
  end_code text,
  end_description text,
  end_terminal text,
  current_value text,
  remark text,
  color_mark text,
  confidence numeric(5, 4) check (confidence between 0 and 1),
  status text not null default 'extracted'
    check (status in ('extracted', 'needs_review', 'confirmed', 'rejected')),
  needs_review boolean not null default false,
  raw_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint wiring_connections_raw_payload_object
    check (jsonb_typeof(raw_payload) = 'object'),
  unique (wiring_unit_id, core_order)
);

create table if not exists public.connection_evidence (
  id uuid primary key default gen_random_uuid(),
  connection_id uuid not null
    references public.wiring_connections(id) on delete cascade,
  drawing_id uuid not null references public.drawings(id) on delete restrict,
  kind text not null
    check (kind in ('source', 'cross_page_reference', 'target', 'manual')),
  bbox jsonb,
  raw_text text,
  created_at timestamptz not null default timezone('utc', now()),
  constraint connection_evidence_bbox_object
    check (bbox is null or jsonb_typeof(bbox) = 'object')
);

comment on column public.wiring_units.wire_number is
  '数据库分配的线号；每个结果版本从 1000 开始递增，同一端子排单元的连接共享该值。';
comment on column public.wiring_units.voltage_level is 'Agent 提取的电压等级。';
comment on column public.wiring_units.terminal_strip is 'Agent 提取的端子排标识。';
comment on column public.wiring_connections.principle_number is 'Agent 提取的原理号。';
comment on column public.wiring_connections.start_code is 'Agent 提取的起点代号。';
comment on column public.wiring_connections.start_description is 'Agent 提取的起点描述。';
comment on column public.wiring_connections.start_terminal is 'Agent 提取的起点端子。';
comment on column public.wiring_connections.end_code is 'Agent 提取的终点代号。';
comment on column public.wiring_connections.end_description is 'Agent 提取的终点描述。';
comment on column public.wiring_connections.end_terminal is 'Agent 提取的终点端子。';
comment on column public.wiring_connections.current_value is 'Agent 提取的电流原始展示值。';
comment on column public.wiring_connections.remark is 'Agent 提取的备注。';
comment on column public.wiring_connections.color_mark is 'Agent 提取的色标。';

create or replace function public.allocate_wiring_unit_wire_number()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  allocated integer;
begin
  if new.wire_number is null then
    insert into public.result_wire_number_counters (
      result_version_id,
      next_wire_number,
      updated_at
    )
    values (
      new.result_version_id,
      1001,
      timezone('utc', now())
    )
    on conflict (result_version_id) do update
      set next_wire_number = public.result_wire_number_counters.next_wire_number + 1,
          updated_at = timezone('utc', now())
    returning next_wire_number - 1 into allocated;

    new.wire_number := allocated;
  else
    if new.wire_number < 1000 then
      raise exception 'wire_number must be at least 1000';
    end if;

    insert into public.result_wire_number_counters (
      result_version_id,
      next_wire_number,
      updated_at
    )
    values (
      new.result_version_id,
      new.wire_number + 1,
      timezone('utc', now())
    )
    on conflict (result_version_id) do update
      set next_wire_number = greatest(
            public.result_wire_number_counters.next_wire_number,
            excluded.next_wire_number
          ),
          updated_at = timezone('utc', now());
  end if;

  return new;
end;
$$;

drop trigger if exists wiring_units_allocate_wire_number on public.wiring_units;
create trigger wiring_units_allocate_wire_number
before insert on public.wiring_units
for each row execute function public.allocate_wiring_unit_wire_number();

create or replace function public.prevent_wiring_unit_identity_change()
returns trigger
language plpgsql
as $$
begin
  if new.result_version_id is distinct from old.result_version_id
     or new.wire_number is distinct from old.wire_number then
    raise exception 'result_version_id and wire_number are immutable';
  end if;
  return new;
end;
$$;

drop trigger if exists wiring_units_protect_identity on public.wiring_units;
create trigger wiring_units_protect_identity
before update of result_version_id, wire_number on public.wiring_units
for each row execute function public.prevent_wiring_unit_identity_change();

create or replace function public.set_updated_at_utc()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

drop trigger if exists projects_updated_at on public.projects;
create trigger projects_updated_at
before update on public.projects
for each row execute function public.set_updated_at_utc();

drop trigger if exists workspaces_updated_at on public.workspaces;
create trigger workspaces_updated_at
before update on public.workspaces
for each row execute function public.set_updated_at_utc();

drop trigger if exists drawings_updated_at on public.drawings;
create trigger drawings_updated_at
before update on public.drawings
for each row execute function public.set_updated_at_utc();

drop trigger if exists wiring_units_updated_at on public.wiring_units;
create trigger wiring_units_updated_at
before update on public.wiring_units
for each row execute function public.set_updated_at_utc();

drop trigger if exists wiring_connections_updated_at on public.wiring_connections;
create trigger wiring_connections_updated_at
before update on public.wiring_connections
for each row execute function public.set_updated_at_utc();

create index if not exists projects_owner_id_idx
  on public.projects (owner_id);
create index if not exists project_members_user_id_idx
  on public.project_members (user_id, project_id);
create index if not exists workspaces_project_sort_idx
  on public.workspaces (project_id, sort_order, name);
create index if not exists drawings_project_page_idx
  on public.drawings (project_id, workspace_id, pdf_page_number);
create index if not exists result_versions_project_created_idx
  on public.result_versions (project_id, created_at desc);
create index if not exists wiring_units_project_workspace_idx
  on public.wiring_units (project_id, workspace_id, result_version_id);
create index if not exists wiring_units_terminal_strip_idx
  on public.wiring_units (terminal_strip);
create index if not exists wiring_connections_unit_order_idx
  on public.wiring_connections (wiring_unit_id, core_order);
create index if not exists wiring_connections_principle_number_idx
  on public.wiring_connections (principle_number);
create index if not exists wiring_connections_start_terminal_idx
  on public.wiring_connections (start_terminal);
create index if not exists wiring_connections_end_terminal_idx
  on public.wiring_connections (end_terminal);
create index if not exists connection_evidence_connection_idx
  on public.connection_evidence (connection_id, kind);
create index if not exists connection_evidence_drawing_idx
  on public.connection_evidence (drawing_id);

create or replace view public.wiring_connection_rows
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
  connection.created_at,
  connection.updated_at
from public.wiring_connections as connection
join public.wiring_units as unit
  on unit.id = connection.wiring_unit_id
join public.result_versions as result_version
  on result_version.id = unit.result_version_id
join public.projects as project
  on project.id = unit.project_id
join public.workspaces as workspace
  on workspace.id = unit.workspace_id
left join public.drawings as drawing
  on drawing.id = coalesce(connection.source_drawing_id, unit.drawing_id);

create or replace function public.is_project_member(target_project_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select exists (
    select 1
    from public.projects as project
    where project.id = target_project_id
      and project.owner_id = auth.uid()
  ) or exists (
    select 1
    from public.project_members as member
    where member.project_id = target_project_id
      and member.user_id = auth.uid()
  );
$$;

revoke all on function public.is_project_member(uuid) from public;
grant execute on function public.is_project_member(uuid) to authenticated;
grant execute on function public.is_project_member(uuid) to service_role;

alter table public.projects enable row level security;
alter table public.project_members enable row level security;
alter table public.workspaces enable row level security;
alter table public.drawings enable row level security;
alter table public.result_versions enable row level security;
alter table public.result_wire_number_counters enable row level security;
alter table public.wiring_units enable row level security;
alter table public.wiring_connections enable row level security;
alter table public.connection_evidence enable row level security;

drop policy if exists projects_member_read on public.projects;
create policy projects_member_read
on public.projects for select to authenticated
using (public.is_project_member(id));

drop policy if exists project_members_member_read on public.project_members;
create policy project_members_member_read
on public.project_members for select to authenticated
using (public.is_project_member(project_id));

drop policy if exists workspaces_member_read on public.workspaces;
create policy workspaces_member_read
on public.workspaces for select to authenticated
using (public.is_project_member(project_id));

drop policy if exists drawings_member_read on public.drawings;
create policy drawings_member_read
on public.drawings for select to authenticated
using (public.is_project_member(project_id));

drop policy if exists result_versions_member_read on public.result_versions;
create policy result_versions_member_read
on public.result_versions for select to authenticated
using (public.is_project_member(project_id));

drop policy if exists wiring_units_member_read on public.wiring_units;
create policy wiring_units_member_read
on public.wiring_units for select to authenticated
using (public.is_project_member(project_id));

drop policy if exists wiring_connections_member_read on public.wiring_connections;
create policy wiring_connections_member_read
on public.wiring_connections for select to authenticated
using (
  exists (
    select 1
    from public.wiring_units as unit
    where unit.id = wiring_unit_id
      and public.is_project_member(unit.project_id)
  )
);

drop policy if exists connection_evidence_member_read on public.connection_evidence;
create policy connection_evidence_member_read
on public.connection_evidence for select to authenticated
using (
  exists (
    select 1
    from public.wiring_connections as connection
    join public.wiring_units as unit
      on unit.id = connection.wiring_unit_id
    where connection.id = connection_id
      and public.is_project_member(unit.project_id)
  )
);

revoke all on public.projects from anon;
revoke all on public.project_members from anon;
revoke all on public.workspaces from anon;
revoke all on public.drawings from anon;
revoke all on public.result_versions from anon;
revoke all on public.result_wire_number_counters from anon, authenticated;
revoke all on public.wiring_units from anon;
revoke all on public.wiring_connections from anon;
revoke all on public.connection_evidence from anon;
revoke all on public.wiring_connection_rows from anon;

grant select on public.projects to authenticated;
grant select on public.project_members to authenticated;
grant select on public.workspaces to authenticated;
grant select on public.drawings to authenticated;
grant select on public.result_versions to authenticated;
grant select on public.wiring_units to authenticated;
grant select on public.wiring_connections to authenticated;
grant select on public.connection_evidence to authenticated;
grant select on public.wiring_connection_rows to authenticated;

grant all on public.projects to service_role;
grant all on public.project_members to service_role;
grant all on public.workspaces to service_role;
grant all on public.drawings to service_role;
grant all on public.result_versions to service_role;
grant all on public.result_wire_number_counters to service_role;
grant all on public.wiring_units to service_role;
grant all on public.wiring_connections to service_role;
grant all on public.connection_evidence to service_role;
grant select on public.wiring_connection_rows to service_role;

-- Rollback order, if this unapplied migration must be reverted manually:
-- view wiring_connection_rows; tables connection_evidence, wiring_connections,
-- wiring_units, result_wire_number_counters, result_versions, drawings,
-- workspaces, project_members, projects; then the three helper functions.
