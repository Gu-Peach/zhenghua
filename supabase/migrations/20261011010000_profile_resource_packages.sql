-- Additive migration. Rollback: disable AGENT_PROFILE_PACKAGES_ENABLED;
-- retain immutable packages/metadata for historical runs, do not drop populated data.
create table public.profile_resource_packages (
  id uuid primary key,
  profile_key text not null check (profile_key ~ '^[a-z][a-z0-9_-]*$'),
  profile_version text not null,
  source_profile_checksum text not null check (source_profile_checksum ~ '^sha256:[0-9a-f]{64}$'),
  package_checksum text not null check (package_checksum ~ '^sha256:[0-9a-f]{64}$'),
  manifest_checksum text not null check (manifest_checksum ~ '^sha256:[0-9a-f]{64}$'),
  storage_bucket text not null default 'agent-profile-assets' check (storage_bucket = 'agent-profile-assets'),
  storage_prefix text not null unique,
  manifest_path text not null unique,
  status text not null default 'candidate' check (status in ('draft','candidate','active','retired')),
  base_package_id uuid references public.profile_resource_packages(id) on delete restrict,
  candidate_id text references public.profile_candidates(id) on delete restrict,
  created_by uuid not null references auth.users(id) on delete restrict,
  approved_by uuid references auth.users(id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  published_at timestamptz,
  unique(profile_key, profile_version, package_checksum)
);
create unique index profile_package_active_per_key on public.profile_resource_packages(profile_key)
  where status = 'active';
create index profile_package_version on public.profile_resource_packages(profile_key, profile_version);
alter table public.profile_resource_packages enable row level security;
grant select on public.profile_resource_packages to authenticated;
grant all on public.profile_resource_packages to service_role;
create policy profile_package_read on public.profile_resource_packages for select to authenticated
  using (status in ('active','retired') or created_by = auth.uid() or approved_by = auth.uid());

create function public.protect_profile_package_content() returns trigger language plpgsql as $$
begin
  if (to_jsonb(new) - array['status','approved_by','published_at','updated_at'])
     is distinct from (to_jsonb(old) - array['status','approved_by','published_at','updated_at']) then
    raise exception 'Profile package content is immutable';
  end if;
  new.updated_at = now();
  return new;
end;
$$;
create trigger protect_profile_package_content before update on public.profile_resource_packages
  for each row execute function public.protect_profile_package_content();

insert into storage.buckets(id, name, public) values ('agent-profile-assets', 'agent-profile-assets', false)
  on conflict (id) do nothing;
-- No browser Storage write/read policies: business API issues short-lived signed URLs.

create function public.publish_profile_package(package_id uuid, reviewer uuid) returns void
language plpgsql security definer set search_path = public as $$
declare target public.profile_resource_packages;
begin
  if auth.role() <> 'service_role' then raise exception 'Internal publisher only'; end if;
  select * into strict target from public.profile_resource_packages where id = package_id for update;
  perform pg_advisory_xact_lock(hashtext('profile-package:' || target.profile_key));
  if target.candidate_id is not null and not exists (
    select 1 from public.profile_candidates where id = target.candidate_id and status = 'ACTIVE'
  ) then raise exception 'Candidate must pass review and canary before publication'; end if;
  if target.candidate_id is null and target.approved_by is null then
    raise exception 'Bootstrap package requires explicit approval';
  end if;
  update public.profile_resource_packages set status = 'retired'
    where profile_key = target.profile_key and status = 'active' and id <> package_id;
  update public.profile_resource_packages set status = 'active', approved_by = reviewer,
    published_at = coalesce(published_at, now()) where id = package_id;
end;
$$;
revoke all on function public.publish_profile_package(uuid, uuid) from public, anon, authenticated;
grant execute on function public.publish_profile_package(uuid, uuid) to service_role;

create function public.rollback_profile_package(package_id uuid, reviewer uuid) returns void
language plpgsql security definer set search_path = public as $$
declare target public.profile_resource_packages;
begin
  if auth.role() <> 'service_role' then raise exception 'Internal publisher only'; end if;
  select * into strict target from public.profile_resource_packages where id = package_id for update;
  perform pg_advisory_xact_lock(hashtext('profile-package:' || target.profile_key));
  if target.base_package_id is null then raise exception 'No package rollback target'; end if;
  if not exists (select 1 from public.profile_candidates
                 where id = target.candidate_id and status = 'ROLLED_BACK') then
    raise exception 'Candidate rollback approval is required';
  end if;
  update public.profile_resource_packages set status = 'retired'
    where profile_key = target.profile_key and status = 'active';
  update public.profile_resource_packages set status = 'active', approved_by = reviewer
    where id = target.base_package_id and status in ('active','retired');
end;
$$;
revoke all on function public.rollback_profile_package(uuid, uuid) from public, anon, authenticated;
grant execute on function public.rollback_profile_package(uuid, uuid) to service_role;
