-- Shared rule resources are readable by every authenticated user and immediately usable.
-- Legacy draft/candidate rows become ready; retired remains the only disabled state.
-- No project/Storage/write grants change; private objects still need Server signed URLs.
drop index if exists public.profile_package_active_per_key;
update public.profile_resource_packages
set status = case when candidate_id is null then 'active' else 'candidate' end,
    updated_at = now()
where status = 'draft';
alter table public.profile_resource_packages
  drop constraint if exists profile_resource_packages_status_check;
alter table public.profile_resource_packages
  add constraint profile_resource_packages_status_check check (status in ('active','candidate','retired'));
alter policy profile_package_read on public.profile_resource_packages
  to authenticated using (true);

create or replace function public.publish_profile_package(package_id uuid, reviewer uuid) returns void
language plpgsql security definer set search_path = public as $$
begin
  if auth.role() <> 'service_role' then raise exception 'Internal publisher only'; end if;
  perform pg_advisory_xact_lock(hashtext('profile-package:' || package_id::text));
  update public.profile_resource_packages
  set status = 'active', approved_by = reviewer, published_at = coalesce(published_at, now())
  where id = package_id;
  if not found then raise exception 'Profile package not found'; end if;
end;
$$;

-- Rollback requires restoring the previous four-state check/publish function and
-- owner/reviewer SELECT predicate. Data promoted to active is intentionally retained.
