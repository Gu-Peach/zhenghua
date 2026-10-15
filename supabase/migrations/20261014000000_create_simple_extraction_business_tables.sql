-- Three core extraction tables; additive, no old tables/views/data are deleted.
-- Copy this entire file into the intended Supabase SQL Editor and execute once.
-- Existing application readers/writers still require adaptation to these tables.
-- Rollback requires a separate reviewed migration after checking data and callers.
begin;

-- 1. Drawing-rule references. Prompt and example assets remain outside this table.
create table public.extraction_profiles (
  id uuid primary key default gen_random_uuid(),
  profile_key text not null check (btrim(profile_key) <> ''),
  profile_version text not null check (btrim(profile_version) <> ''),
  checksum text not null check (checksum ~ '^sha256:[0-9a-f]{64}$'),
  resource_ref text not null check (btrim(resource_ref) <> ''),
  display_name text not null check (btrim(display_name) <> ''),
  created_by uuid not null default auth.uid() references auth.users(id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (profile_key, profile_version, checksum)
);

-- 2. Projects. Direct foreign keys replace a separate project/result link table.
create table public.extraction_projects (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null default auth.uid() references auth.users(id) on delete restrict,
  name text not null check (btrim(name) <> ''),
  profile_id uuid not null references public.extraction_profiles(id) on delete restrict,
  source_pdf_bucket text,
  source_pdf_path text,
  drawing_index jsonb not null default '{}'::jsonb
    check (jsonb_typeof(drawing_index) = 'object'),
  status text not null default 'draft'
    check (status in ('draft', 'processing', 'ready', 'failed', 'archived')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 3. Real row storage, unlike the existing wiring_connection_rows VIEW.
create table public.extraction_connection_rows (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.extraction_projects(id) on delete cascade,
  batch_id text not null check (btrim(batch_id) <> ''),
  page_item_id text not null check (btrim(page_item_id) <> ''),
  row_order integer not null check (row_order >= 0),
  workspace_code text,
  source_drawing_page text,
  source_pdf_page_number integer not null check (source_pdf_page_number > 0),
  target_drawing_page text,
  target_pdf_page_number integer check (target_pdf_page_number > 0),
  wire_number text,
  principle_number text,
  terminal_strip text,
  start_code text,
  start_description text,
  start_terminal text,
  end_code text,
  end_description text,
  end_terminal text,
  current_value text,
  color_mark text,
  remark text,
  is_cross_page boolean not null default false,
  needs_review boolean not null default false,
  evidence jsonb not null default '{}'::jsonb
    check (jsonb_typeof(evidence) = 'object'),
  record_version integer not null default 1 check (record_version > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (project_id, batch_id, source_pdf_page_number, page_item_id)
);

comment on column public.extraction_profiles.resource_ref is
  '稳定规则目录或Storage manifest引用；不存过期签名URL或密钥。';
comment on column public.extraction_projects.drawing_index is
  '图纸目录及页面图片对象路径；保留业务页标和PDF物理页号。';
comment on column public.extraction_connection_rows.source_drawing_page is '来源图纸业务页标，如003C01。';
comment on column public.extraction_connection_rows.source_pdf_page_number is '来源PDF物理页号，从1开始。';
comment on column public.extraction_connection_rows.page_item_id is
  '同页连接的稳定项标识，由调用方提供；原理号不能替代，原理号可在分支中重复。';
comment on column public.extraction_connection_rows.batch_id is
  '提取批次/run标识，读取方应指定批次；不自动选择最新批次。';
comment on column public.extraction_connection_rows.current_value is
  '带单位的电流展示值；无法确认时为NULL，不用0代替缺失值。';

create index extraction_projects_owner_idx on public.extraction_projects(owner_id, created_at desc);
create index extraction_projects_profile_idx on public.extraction_projects(profile_id);
create index extraction_profiles_creator_idx on public.extraction_profiles(created_by);
create index extraction_rows_page_order_idx
  on public.extraction_connection_rows(project_id, batch_id, source_pdf_page_number, row_order, id);
create index extraction_rows_principle_idx
  on public.extraction_connection_rows(project_id, principle_number);
create index extraction_rows_review_idx
  on public.extraction_connection_rows(project_id, batch_id) where needs_review;

create function public.touch_simple_extraction_row() returns trigger
language plpgsql set search_path = public, pg_temp as $$
begin
  new.updated_at = now();
  if tg_table_name = 'extraction_connection_rows' then
    new.record_version = old.record_version + 1;
  end if;
  return new;
end;
$$;

create trigger extraction_profiles_updated_at before update on public.extraction_profiles
  for each row execute function public.touch_simple_extraction_row();
create trigger extraction_projects_updated_at before update on public.extraction_projects
  for each row execute function public.touch_simple_extraction_row();
create trigger extraction_rows_updated_at before update on public.extraction_connection_rows
  for each row execute function public.touch_simple_extraction_row();

alter table public.extraction_profiles enable row level security;
alter table public.extraction_projects enable row level security;
alter table public.extraction_connection_rows enable row level security;

-- Shared rule references; only their creator can maintain them.
create policy extraction_profiles_read on public.extraction_profiles
  for select to authenticated using (true);
create policy extraction_profiles_insert on public.extraction_profiles
  for insert to authenticated with check (created_by = (select auth.uid()));
create policy extraction_profiles_update on public.extraction_profiles
  for update to authenticated using (created_by = (select auth.uid()))
  with check (created_by = (select auth.uid()));
create policy extraction_profiles_delete on public.extraction_profiles
  for delete to authenticated using (created_by = (select auth.uid()));

create policy extraction_projects_owner on public.extraction_projects
  for all to authenticated using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

create policy extraction_rows_owner on public.extraction_connection_rows
  for all to authenticated
  using (exists (
    select 1 from public.extraction_projects project
    where project.id = extraction_connection_rows.project_id and project.owner_id = (select auth.uid())
  ))
  with check (exists (
    select 1 from public.extraction_projects project
    where project.id = extraction_connection_rows.project_id and project.owner_id = (select auth.uid())
  ));

revoke all on public.extraction_profiles, public.extraction_projects,
  public.extraction_connection_rows from public, anon;
grant select, insert, update, delete on public.extraction_profiles,
  public.extraction_projects, public.extraction_connection_rows to authenticated, service_role;
revoke all on function public.touch_simple_extraction_row() from public, anon;
grant execute on function public.touch_simple_extraction_row() to authenticated, service_role;

commit;
