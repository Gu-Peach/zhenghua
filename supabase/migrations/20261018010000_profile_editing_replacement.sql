-- Latest-version replacement and durable, retryable cleanup. No user rows are changed on deployment.
-- Rollback: stop editing publishers, drop replace_extraction_profile/profile_version_in_use,
-- restore protect_published_profile from 20261017010000, then drop profile_asset_gc.
-- Deleted retired ZIPs cannot be recovered by rollback; in-use versions are never collected.
create table public.profile_asset_gc (
  resource_ref text primary key check (resource_ref like 'storage://project-assets/profiles/%'),
  owner_id uuid not null references auth.users(id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);
create index profile_asset_gc_pending on public.profile_asset_gc(owner_id,created_at) where deleted_at is null;
create trigger profile_asset_gc_updated_at before update on public.profile_asset_gc
for each row execute function public.touch_simple_extraction_row();
alter table public.profile_asset_gc enable row level security;
create policy profile_asset_gc_owner_read on public.profile_asset_gc for select to authenticated using(owner_id=auth.uid());
revoke all on public.profile_asset_gc from public,anon,authenticated;
grant select on public.profile_asset_gc to authenticated;
grant all on public.profile_asset_gc to service_role;

create or replace function public.protect_published_profile() returns trigger
language plpgsql set search_path=public as $$
begin
  if new.resource_ref like 'storage://%' and current_user not in ('postgres','service_role') then
    raise sqlstate 'PT403' using message='Published profiles require trusted publication';
  end if;
  if tg_op='INSERT' and exists(select 1 from public.profile_asset_gc where resource_ref=new.resource_ref) then
    raise sqlstate 'PT409' using message='Retired profile package cannot be republished';
  end if;
  if tg_op='UPDATE' and old.resource_ref like 'storage://%' and
    (new.profile_key,new.profile_version,new.checksum,new.resource_ref,new.created_by,new.display_name) is distinct from
    (old.profile_key,old.profile_version,old.checksum,old.resource_ref,old.created_by,old.display_name) then
    raise sqlstate 'PT409' using message='Published profile version is immutable';
  end if;
  return new;
end $$;

create function public.profile_version_in_use(target uuid) returns boolean
language plpgsql security definer set search_path=public as $$
declare p public.extraction_profiles; active boolean := false;
begin
  if exists(select 1 from public.extraction_projects where profile_id=target) then return true; end if;
  select * into p from public.extraction_profiles where id=target;
  if found and to_regclass('public.agent_runs') is not null then
    execute 'select exists(select 1 from public.agent_runs where status::text in (''QUEUED'',''RUNNING'',''WAITING_INPUT'',''FAILED'') and profile->>''key''=$1 and profile->>''version''=$2 and profile->>''checksum''=$3)'
    into active using p.profile_key,p.profile_version,p.checksum;
  end if;
  return active;
end $$;
revoke all on function public.profile_version_in_use(uuid) from public,anon,authenticated;
grant execute on function public.profile_version_in_use(uuid) to service_role;

create function public.replace_extraction_profile(
  actor uuid, base_profile_id uuid, base_checksum text, profile_key_value text,
  version_value text, name_value text, checksum_value text, ref_value text
) returns jsonb language plpgsql security definer set search_path=public as $$
declare base public.extraction_profiles; latest public.extraction_profiles;
  result jsonb; old public.extraction_profiles; retained boolean := false;
begin
  if actor is null then raise sqlstate 'PT403' using message='Invalid owner'; end if;
  perform pg_advisory_xact_lock(hashtextextended('published-profile:'||profile_key_value,0));
  select * into base from public.extraction_profiles where id=base_profile_id for update;
  if found and base.created_by is distinct from actor then
    raise sqlstate 'PT403' using message='Profile belongs to another owner';
  end if;
  if base.id is not null and (base.checksum is distinct from base_checksum or base.profile_key is distinct from profile_key_value) then
    raise sqlstate 'PT409' using message='Profile source changed';
  end if;
  select * into latest from public.extraction_profiles
    where profile_key=profile_key_value and profile_version=version_value and checksum=checksum_value and resource_ref=ref_value and created_by=actor;
  if found then
    return jsonb_build_object('profile',to_jsonb(latest),'previous_version_retained',
      base.id is not null and public.profile_version_in_use(base.id));
  end if;
  if base.id is null then raise sqlstate 'PT409' using message='Profile source no longer current'; end if;
  select * into latest from public.extraction_profiles where profile_key=profile_key_value
    order by string_to_array(profile_version,'.')::integer[] desc,created_at desc limit 1;
  if latest.id<>base.id or version_value !~ '^\d+\.\d+\.\d+$' or
    string_to_array(version_value,'.')::integer[] <= string_to_array(base.profile_version,'.')::integer[] then
    raise sqlstate 'PT409' using message='Newer profile version already exists';
  end if;
  result := public.publish_extraction_profile(actor,profile_key_value,version_value,name_value,checksum_value,ref_value);
  for old in select * from public.extraction_profiles where profile_key=profile_key_value and created_by=actor
    and id<>(result->>'id')::uuid for update loop
    if public.profile_version_in_use(old.id) then
      retained := true;
    else
      if old.resource_ref like 'storage://project-assets/profiles/'||actor::text||'/%' then
        insert into public.profile_asset_gc(resource_ref,owner_id) values(old.resource_ref,actor) on conflict do nothing;
      end if;
      delete from public.extraction_profiles where id=old.id;
    end if;
  end loop;
  return jsonb_build_object('profile',result,'previous_version_retained',retained);
end $$;
revoke all on function public.replace_extraction_profile(uuid,uuid,text,text,text,text,text,text) from public,anon,authenticated;
grant execute on function public.replace_extraction_profile(uuid,uuid,text,text,text,text,text,text) to service_role;
notify pgrst, 'reload schema';
