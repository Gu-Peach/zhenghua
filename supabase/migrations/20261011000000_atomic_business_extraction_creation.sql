-- Gate B: atomic protocol-2 creation, initial event, and queue registration.
-- Existing run/stage/result tables and Gate A guards are reused.
-- Rollback: disable the Gate B HTTP entry before revoking this function;
-- retain created runs, confirmation payloads, and their stage/result history.
create or replace function public.gate_b_create_extraction(value jsonb)
returns jsonb language plpgsql security definer set search_path = public, pg_temp as $$
declare
  existing public.agent_runs;
  project public.projects;
  source public.document_files;
  confirmation jsonb := value->'options'->'profile_confirmation';
begin
  if value->>'run_type' <> 'FULL_EXTRACTION' or (value->>'protocol_version')::int <> 2
     or value->>'status' <> 'QUEUED' or nullif(value->>'idempotency_key','') is null then
    raise exception 'Invalid durable extraction creation' using errcode='PT409';
  end if;
  select * into project from public.projects where id=(value->>'project_id')::uuid for update;
  if not found or project.owner_id <> (value->>'requested_by')::uuid then
    raise exception 'Project owner mismatch' using errcode='PT403';
  end if;
  select * into source from public.document_files where id=(value->>'source_document_id')::uuid
    and project_id=project.id and kind='source_pdf';
  if not found then
    raise exception 'Source document mismatch' using errcode='PT409';
  end if;
  select * into existing from public.agent_runs where project_id=project.id
    and idempotency_key=value->>'idempotency_key';
  if found then
    if existing.request_fingerprint is distinct from value->>'request_fingerprint' then
      raise exception 'Idempotency input conflict' using errcode='PT409';
    end if;
    return to_jsonb(existing);
  end if;
  if confirmation is not null and confirmation <> 'null'::jsonb and (
    confirmation->>'confirmed_by' is distinct from value->>'requested_by'
    or confirmation->>'source_checksum' is distinct from source.checksum
    or confirmation->'profile' is distinct from value->'profile'
    or value->>'profile_hint' is distinct from value->'profile'->>'key'
  ) then
    raise exception 'Frozen confirmation mismatch' using errcode='PT409';
  end if;
  insert into public.agent_runs(
    id,project_id,source_document_id,requested_by,run_type,status,scope,idempotency_key,
    request_fingerprint,profile_hint,profile,expected_result_version,options,protocol_version
  ) values (
    (value->>'id')::uuid,project.id,source.id,(value->>'requested_by')::uuid,
    'FULL_EXTRACTION','QUEUED',value->'scope',value->>'idempotency_key',
    value->>'request_fingerprint',value->>'profile_hint',nullif(value->'profile','null'::jsonb),
    (value->>'expected_result_version')::int,value->'options',2
  ) returning * into existing;
  insert into public.agent_events(id,agent_run_id,seq,event_type,message)
    values(gen_random_uuid(),existing.id,0,'RUN_CREATED','run created');
  insert into public.agent_run_queue(agent_run_id) values(existing.id);
  return to_jsonb(existing);
end $$;
revoke all on function public.gate_b_create_extraction(jsonb) from public,anon,authenticated;
grant execute on function public.gate_b_create_extraction(jsonb) to service_role;
