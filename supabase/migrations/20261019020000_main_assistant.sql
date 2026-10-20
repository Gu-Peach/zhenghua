-- Main assistant metadata only. Existing extraction/Profile facts are not migrated.
begin;

create table public.assistant_conversations (
  id uuid primary key,
  owner_id uuid not null references auth.users(id) on delete cascade,
  title text not null check (length(btrim(title)) between 1 and 120),
  context jsonb not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index assistant_conversations_owner_time on public.assistant_conversations(owner_id,updated_at desc);

create table public.assistant_turns (
  id uuid primary key,
  conversation_id uuid not null references public.assistant_conversations(id) on delete cascade,
  owner_id uuid not null references auth.users(id) on delete cascade,
  request_hash text not null,
  request jsonb not null,
  tool_token_hash text not null,
  status text not null check (status in ('running','completed','failed','cancelled')),
  lease_until timestamptz not null default now(),
  events jsonb not null default '[]',
  answer text not null default '',
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index assistant_turns_conversation_time on public.assistant_turns(conversation_id,created_at,id);
create index assistant_turns_owner on public.assistant_turns(owner_id,conversation_id);

create table public.assistant_actions (
  id uuid primary key,
  conversation_id uuid not null references public.assistant_conversations(id) on delete cascade,
  turn_id uuid not null references public.assistant_turns(id) on delete cascade,
  owner_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid references public.extraction_projects(id) on delete cascade,
  tool_name text not null,
  arguments jsonb not null default '{}',
  result jsonb not null default '{}',
  status text not null default 'running' check (status in ('running','completed','awaiting_confirmation','applied','rejected','failed')),
  checksum text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index assistant_actions_owner_turn on public.assistant_actions(owner_id,turn_id);

create table public.assistant_attachments (
  id uuid primary key,
  conversation_id uuid not null references public.assistant_conversations(id) on delete cascade,
  owner_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid references public.extraction_projects(id) on delete cascade,
  filename text not null,
  mime_type text not null,
  role text not null check (role in ('source','target','detail','pdf')),
  pdf_page_number integer check (pdf_page_number > 0),
  checksum text not null,
  storage_path text not null unique,
  uploaded boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index assistant_attachments_owner_conversation on public.assistant_attachments(owner_id,conversation_id);

create function public.assistant_touch_updated_at() returns trigger language plpgsql set search_path=public,pg_temp as $$
begin new.updated_at=now(); return new; end $$;
do $$ declare t text; begin
  foreach t in array array['assistant_conversations','assistant_turns','assistant_actions','assistant_attachments'] loop
    execute format('alter table public.%I enable row level security',t);
    execute format('create policy owner_read on public.%I for select to authenticated using(owner_id=auth.uid())',t);
    execute format('revoke all on public.%I from anon,authenticated',t);
    execute format('grant select on public.%I to authenticated',t);
    execute format('grant all on public.%I to service_role',t);
    execute format('create trigger touch_updated_at before update on public.%I for each row execute function public.assistant_touch_updated_at()',t);
  end loop;
end $$;

create function public.assistant_begin_turn(
  actor uuid, conversation uuid, turn uuid, body jsonb, body_hash text, token_hash text
) returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare c public.assistant_conversations; t public.assistant_turns;
begin
  select * into c from public.assistant_conversations where id=conversation for update;
  if not found or c.owner_id<>actor then raise sqlstate 'PT403' using message='ASSISTANT_ACCESS_DENIED'; end if;
  select * into t from public.assistant_turns where id=turn for update;
  if found then
    if t.owner_id<>actor or t.conversation_id<>conversation or t.request_hash<>body_hash then
      raise sqlstate 'PT409' using message='ASSISTANT_TURN_CONFLICT';
    end if;
    if t.status='completed' then return to_jsonb(t); end if;
    if t.status='running' and t.lease_until>now() then raise sqlstate 'PT409' using message='ASSISTANT_TURN_BUSY'; end if;
  end if;
  if exists(select 1 from public.assistant_turns where conversation_id=conversation and id<>turn and status='running' and lease_until>now()) then
    raise sqlstate 'PT409' using message='ASSISTANT_CONVERSATION_BUSY';
  end if;
  insert into public.assistant_turns(id,conversation_id,owner_id,request_hash,request,tool_token_hash,status,lease_until)
  values(turn,conversation,actor,body_hash,body,token_hash,'running',now()+interval '20 minutes')
  on conflict(id) do update set status='running',tool_token_hash=excluded.tool_token_hash,
    lease_until=excluded.lease_until,error=null
  returning * into t;
  update public.assistant_conversations set updated_at=now() where id=conversation;
  return to_jsonb(t);
end $$;

create function public.assistant_finish_turn(
  actor uuid, turn uuid, token_hash text, outcome text, event_list jsonb, public_answer text,
  failure text, scope_context jsonb
) returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare t public.assistant_turns;
begin
  select * into t from public.assistant_turns where id=turn for update;
  if not found or t.owner_id<>actor then raise sqlstate 'PT403' using message='ASSISTANT_ACCESS_DENIED'; end if;
  if t.tool_token_hash<>token_hash then raise sqlstate 'PT409' using message='ASSISTANT_TURN_RECLAIMED'; end if;
  if outcome not in ('completed','failed','cancelled') then raise sqlstate 'PT422' using message='ASSISTANT_STATUS_INVALID'; end if;
  if t.status='completed' then return to_jsonb(t); end if;
  update public.assistant_turns set status=outcome,events=event_list,answer=public_answer,error=failure,lease_until=now()
  where id=turn returning * into t;
  update public.assistant_conversations set context=scope_context,updated_at=now() where id=t.conversation_id and owner_id=actor;
  return to_jsonb(t);
end $$;

revoke all on function public.assistant_begin_turn(uuid,uuid,uuid,jsonb,text,text) from public,anon,authenticated;
revoke all on function public.assistant_finish_turn(uuid,uuid,text,text,jsonb,text,text,jsonb) from public,anon,authenticated;
grant execute on function public.assistant_begin_turn(uuid,uuid,uuid,jsonb,text,text) to service_role;
grant execute on function public.assistant_finish_turn(uuid,uuid,text,text,jsonb,text,text,jsonb) to service_role;
comment on table public.assistant_actions is 'Assistant tool receipts and references; formal extraction/Profile writes use their existing confirmation services.';
-- Rollback: drop the two RPCs and the four assistant_* tables, then assistant_touch_updated_at();
-- this loses only assistant history/links; private assistant Storage assets require owner-scoped cleanup.
commit;
