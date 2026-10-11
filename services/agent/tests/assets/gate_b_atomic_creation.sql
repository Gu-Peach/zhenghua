-- Executed only in the disposable migration verification databases.
begin;
insert into auth.users(id) values('00000000-0000-4000-8000-000000000001');
insert into public.projects(id,owner_id,name) values(
  '00000000-0000-4000-8000-000000000002','00000000-0000-4000-8000-000000000001','synthetic Gate B');
insert into public.document_files(id,project_id,kind,original_filename,storage_bucket,storage_path,
                                 checksum,mime_type,size_bytes)
values('00000000-0000-4000-8000-000000000003','00000000-0000-4000-8000-000000000002',
       'source_pdf','synthetic.pdf','project-assets','synthetic-gate-b-only.pdf','synthetic-checksum',
       'application/pdf',1);
do $$
declare value jsonb; receipt jsonb; count_value int;
begin
  value := jsonb_build_object(
    'id','00000000-0000-4000-8000-000000000004','project_id','00000000-0000-4000-8000-000000000002',
    'source_document_id','00000000-0000-4000-8000-000000000003',
    'requested_by','00000000-0000-4000-8000-000000000001','run_type','FULL_EXTRACTION',
    'status','QUEUED','scope','{"type":"PROJECT","id":"synthetic"}'::jsonb,'idempotency_key','gate-b',
    'request_fingerprint','fingerprint','profile_hint','zh','profile','{"key":"zh","version":"1"}'::jsonb,
    'expected_result_version',0,'protocol_version',2,'options',jsonb_build_object('profile_confirmation',
      jsonb_build_object('confirmed_by','00000000-0000-4000-8000-000000000001',
                        'source_checksum','synthetic-checksum','profile','{"key":"zh","version":"1"}'::jsonb)));
  receipt := public.gate_b_create_extraction(value);
  if public.gate_b_create_extraction(value) <> receipt then raise exception 'Replay changed run'; end if;
  select count(*) into count_value from public.agent_events where agent_run_id=(receipt->>'id')::uuid;
  if count_value <> 1 then raise exception 'Duplicate initial event'; end if;
  select count(*) into count_value from public.agent_run_queue where agent_run_id=(receipt->>'id')::uuid;
  if count_value <> 1 then raise exception 'Missing queue'; end if;
  begin
    perform public.gate_b_create_extraction(value || '{"request_fingerprint":"changed"}'::jsonb);
    raise exception 'Different input accepted';
  exception when sqlstate 'PT409' then null; end;
  begin
    perform public.gate_b_create_extraction(value || '{"requested_by":"00000000-0000-4000-8000-000000000009"}'::jsonb);
    raise exception 'Wrong owner accepted';
  exception when sqlstate 'PT403' then null; end;
end $$;
create function public.gate_b_injected_queue_failure() returns trigger language plpgsql as $$
begin raise exception 'synthetic queue fault'; end $$;
create trigger gate_b_injected_queue_failure before insert on public.agent_run_queue
for each row execute function public.gate_b_injected_queue_failure();
do $$
declare value jsonb;
begin
  select to_jsonb(a) || '{"id":"00000000-0000-4000-8000-000000000005","idempotency_key":"fault"}'::jsonb
    into value from public.agent_runs a where id='00000000-0000-4000-8000-000000000004';
  begin
    perform public.gate_b_create_extraction(value);
  exception when raise_exception then
    if sqlerrm <> 'synthetic queue fault' then raise; end if;
  end;
  if exists(select 1 from public.agent_runs where id='00000000-0000-4000-8000-000000000005') then
    raise exception 'Queue failure left an orphan run';
  end if;
end $$;
rollback;
