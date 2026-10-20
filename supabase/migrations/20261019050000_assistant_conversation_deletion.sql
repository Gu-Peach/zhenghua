-- Permanent assistant history deletion. Existing project/Profile/task facts stay intact.
begin;

create table public.assistant_asset_gc (
  id uuid primary key,
  owner_id uuid not null references auth.users(id) on delete cascade,
  conversation_id uuid not null, -- deliberately no FK: jobs survive history deletion
  storage_path text not null unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint assistant_gc_owned_path check (
    starts_with(storage_path, 'assistant/' || owner_id::text || '/' || conversation_id::text || '/' || id::text || '/')
    and storage_path !~ '(^|/)\.\.?(/|$)'
    and position(chr(92) in storage_path) = 0
  )
);
create index assistant_asset_gc_owner_time on public.assistant_asset_gc(owner_id,created_at,id);
alter table public.assistant_asset_gc enable row level security;
revoke all on public.assistant_asset_gc from public,anon,authenticated;
grant all on public.assistant_asset_gc to service_role;
create trigger touch_updated_at before update on public.assistant_asset_gc
  for each row execute function public.assistant_touch_updated_at();

create function public.assistant_delete_conversation(actor uuid, conversation uuid)
returns boolean language plpgsql security definer set search_path=public,pg_temp as $$
declare saved public.assistant_conversations;
begin
  if actor is null or conversation is null then
    raise sqlstate 'PT404' using message='ASSISTANT_NOT_FOUND';
  end if;
  -- Same parent-row lock as begin_turn; concurrent new turns cannot bypass this guard.
  select * into saved from public.assistant_conversations where id=conversation for update;
  if not found then return true; end if;
  if saved.owner_id<>actor then raise sqlstate 'PT404' using message='ASSISTANT_NOT_FOUND'; end if;
  if exists(select 1 from public.assistant_turns
    where conversation_id=conversation and status='running' and lease_until>now())
    or exists(select 1 from public.assistant_attachments
    where conversation_id=conversation and not uploaded and updated_at>now()-interval '20 minutes') then
    raise sqlstate 'PT409' using message='ASSISTANT_CONVERSATION_BUSY';
  end if;
  insert into public.assistant_asset_gc(id,owner_id,conversation_id,storage_path)
    select id,owner_id,conversation_id,storage_path from public.assistant_attachments
    where conversation_id=conversation
    on conflict(id) do nothing;
  delete from public.assistant_conversations where id=conversation and owner_id=actor;
  return true;
end $$;
revoke all on function public.assistant_delete_conversation(uuid,uuid) from public,anon,authenticated;
grant execute on function public.assistant_delete_conversation(uuid,uuid) to service_role;
comment on table public.assistant_asset_gc is 'Owner-scoped retryable private assistant object cleanup after history deletion.';

-- Rollback: first drain queued Storage jobs, then drop assistant_delete_conversation(uuid,uuid)
-- and assistant_asset_gc. Permanently deleted history cannot be reconstructed by rollback.
notify pgrst, 'reload schema';
commit;
