-- Run as the Supabase database administrator after the normal migrations.
-- Re-runnable: create missing buckets, preserve existing configuration/objects.
-- Operational helper, not an additional schema migration.
-- Does not create legacy public "images" or grant browser write access.
begin;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'project-assets', 'project-assets', false, 524288000,
  array[
    'application/pdf', 'image/png', 'image/jpeg', 'application/json',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/zip'
  ]
)
on conflict (id) do nothing;

insert into storage.buckets (id, name, public)
values ('agent-profile-assets', 'agent-profile-assets', false)
on conflict (id) do nothing;

do $$
begin
  if exists (
    select 1 from storage.buckets
    where id in ('project-assets', 'agent-profile-assets') and public
  ) then
    raise exception 'Expected private buckets. Review existing bucket visibility before retrying.';
  end if;
  if exists (
    select 1 from storage.buckets where id = 'project-assets'
    and allowed_mime_types is not null
    and not (allowed_mime_types @> array[
      'application/pdf', 'image/png', 'image/jpeg', 'application/json',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'application/zip'
    ]::text[])
  ) then
    raise exception 'Existing project-assets MIME list is incomplete. Review migrations/configuration; no existing setting was overwritten.';
  end if;
end;
$$;

commit;
