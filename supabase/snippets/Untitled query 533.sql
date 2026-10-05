-- One row represents one extracted wiring-table segment.
-- Files are kept in Storage under images/<job_id>/... and referenced by path.

create table if not exists public.wiring_tables (
  id uuid primary key default gen_random_uuid(),
  job_id text not null,
  group_id text not null,
  source_filename text not null,
  title text not null,
  status text not null default 'processing'
    check (status in ('processing', 'success', 'failed', 'partial', 'empty')),
  pages integer[] not null default '{}',
  reason text,
  record_count integer not null default 0 check (record_count >= 0),
  records jsonb not null default '[]'::jsonb,
  source_pdf_path text,
  page_paths jsonb not null default '[]'::jsonb,
  all_page_paths jsonb not null default '[]'::jsonb,
  records_path text,
  xlsx_path text,
  diagnostics_path text,
  error text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (job_id, group_id),
  constraint wiring_tables_records_array check (jsonb_typeof(records) = 'array'),
  constraint wiring_tables_page_paths_array check (jsonb_typeof(page_paths) = 'array'),
  constraint wiring_tables_all_page_paths_array check (jsonb_typeof(all_page_paths) = 'array')
);

create index if not exists wiring_tables_job_id_idx
  on public.wiring_tables (job_id);

create index if not exists wiring_tables_created_at_idx
  on public.wiring_tables (created_at desc);

alter table public.wiring_tables
  add column if not exists all_page_paths jsonb not null default '[]'::jsonb;

create or replace function public.set_wiring_tables_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

drop trigger if exists wiring_tables_updated_at on public.wiring_tables;
create trigger wiring_tables_updated_at
before update on public.wiring_tables
for each row execute function public.set_wiring_tables_updated_at();

alter table public.wiring_tables enable row level security;

drop policy if exists "wiring tables are readable" on public.wiring_tables;
create policy "wiring tables are readable"
on public.wiring_tables
for select
to anon, authenticated
using (true);

-- The backend uses the service-role key for writes. No anonymous write policy
-- is created, so browser clients can read but cannot mutate extracted data.

insert into storage.buckets (id, name, public, file_size_limit)
values ('images', 'images', true, 524288000)
on conflict (id) do update
set public = excluded.public,
    file_size_limit = excluded.file_size_limit;

drop policy if exists "images are publicly readable" on storage.objects;
create policy "images are publicly readable"
on storage.objects
for select
to anon, authenticated
using (bucket_id = 'images');
