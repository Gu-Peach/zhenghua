-- Immutable published packages; legacy local:// references remain readable.
-- Rollback: drop trigger protect_published_profile on public.extraction_profiles;
-- drop function public.protect_published_profile();
-- drop function public.publish_extraction_profile(uuid,text,text,text,text,text).
create or replace function public.protect_published_profile() returns trigger
language plpgsql set search_path=public as $$
begin
  if new.resource_ref like 'storage://%' and current_user not in ('postgres','service_role') then
    raise sqlstate 'PT403' using message='Published profiles require trusted publication';
  end if;
  if tg_op='UPDATE' and old.resource_ref like 'storage://%' and
    (new.profile_key,new.profile_version,new.checksum,new.resource_ref,new.created_by,new.display_name)
    is distinct from
    (old.profile_key,old.profile_version,old.checksum,old.resource_ref,old.created_by,old.display_name) then
    raise sqlstate 'PT409' using message='Published profile version is immutable';
  end if;
  return new;
end $$;
create trigger protect_published_profile before insert or update on public.extraction_profiles
for each row execute function public.protect_published_profile();
revoke all on function public.protect_published_profile() from public,anon,authenticated;
create or replace function public.publish_extraction_profile(
  actor uuid, profile_key_value text, version_value text, name_value text,
  checksum_value text, ref_value text
) returns jsonb language plpgsql security definer set search_path=public as $$
declare previous public.extraction_profiles; result public.extraction_profiles;
begin
  if actor is null or not exists(select 1 from auth.users where id=actor) then
    raise sqlstate 'PT403' using message='Invalid owner';
  end if;
  if profile_key_value !~ '^[a-z][a-z0-9_-]{0,63}$' or version_value !~ '^\d+\.\d+\.\d+$'
    or checksum_value !~ '^sha256:[0-9a-f]{64}$' or length(trim(name_value)) not between 1 and 120
    or ref_value <> 'storage://project-assets/profiles/'||actor::text||'/'||profile_key_value||'/'||version_value||'/'||substr(checksum_value,8)||'.zip' then
    raise sqlstate 'PT422' using message='Invalid package metadata';
  end if;
  perform pg_advisory_xact_lock(hashtextextended('published-profile:'||profile_key_value,0));
  select * into previous from public.extraction_profiles where profile_key=profile_key_value order by created_at limit 1;
  if found and previous.created_by <> actor then
    raise sqlstate 'PT403' using message='Profile key belongs to another owner';
  end if;
  select * into result from public.extraction_profiles where profile_key=profile_key_value and profile_version=version_value limit 1;
  if found then
    if result.checksum <> checksum_value or result.resource_ref <> ref_value then
      raise sqlstate 'PT409' using message='Profile version already exists';
    end if;
    return to_jsonb(result);
  end if;
  insert into public.extraction_profiles(profile_key,profile_version,display_name,checksum,resource_ref,created_by)
    values(profile_key_value,version_value,name_value,checksum_value,ref_value,actor) returning * into result;
  return to_jsonb(result);
end $$;
revoke all on function public.publish_extraction_profile(uuid,text,text,text,text,text) from public,anon,authenticated;
grant execute on function public.publish_extraction_profile(uuid,text,text,text,text,text) to service_role;
notify pgrst, 'reload schema';
