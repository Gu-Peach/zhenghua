-- Multi-version ready packages must not retire unrelated versions during candidate rollback.
-- Rollback: restore the previous rollback_profile_package implementation from
-- 20261011010000_profile_resource_packages.sql (not recommended after multi-version activation).
create or replace function public.rollback_profile_package(package_id uuid, reviewer uuid) returns void
language plpgsql security definer set search_path = public as $$
declare target public.profile_resource_packages;
begin
  if auth.role() <> 'service_role' then raise exception 'Internal publisher only'; end if;
  select * into strict target from public.profile_resource_packages where id = package_id for update;
  perform pg_advisory_xact_lock(hashtext('profile-package:' || target.profile_key));
  if target.base_package_id is null then raise exception 'No package rollback target'; end if;
  if not exists (
    select 1 from public.profile_candidates
    where id = target.candidate_id and status = 'ROLLED_BACK'
  ) then raise exception 'Candidate rollback approval is required'; end if;
  update public.profile_resource_packages set status = 'retired' where id = package_id;
  update public.profile_resource_packages set status = 'active', approved_by = reviewer
  where id = target.base_package_id and status in ('active','retired');
end;
$$;
revoke all on function public.rollback_profile_package(uuid, uuid) from public, anon, authenticated;
grant execute on function public.rollback_profile_package(uuid, uuid) to service_role;
