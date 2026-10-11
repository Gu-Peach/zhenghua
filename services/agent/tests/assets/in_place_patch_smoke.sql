-- Run inside a transaction, always ROLLBACK. Only generated synthetic IDs are written.
do $$
<<smoke>>
declare
  actor uuid := gen_random_uuid(); stranger uuid := gen_random_uuid();
  project uuid := gen_random_uuid(); workspace uuid := gen_random_uuid(); doc uuid := gen_random_uuid();
  run_id uuid := gen_random_uuid(); result_id uuid := gen_random_uuid(); unit_id uuid := gen_random_uuid();
  connection_id uuid := gen_random_uuid(); drawing_id uuid := gen_random_uuid(); evidence_id uuid := gen_random_uuid();
  proposal_key text := 'in-place-smoke:' || gen_random_uuid()::text;
  feedback_key text := 'in-place-smoke:' || gen_random_uuid()::text;
  profile jsonb := '{"key":"zh","version":"1.0.0"}'::jsonb;
  before_value jsonb; after_value jsonb; operation jsonb; request jsonb; receipt jsonb; record jsonb;
  second_operation jsonb; batch jsonb;
begin
  perform set_config('request.jwt.claims',jsonb_build_object('role','service_role')::text,true);
  insert into auth.users(id) values(actor),(stranger);
  insert into public.projects(id,owner_id,name) values(project,actor,'Synthetic in-place patch');
  insert into public.workspaces(id,project_id,name) values(workspace,project,'Synthetic');
  insert into public.document_files(id,project_id,original_filename,storage_path,checksum,mime_type,size_bytes)
    values(doc,project,'synthetic.pdf','synthetic/' || doc::text,'synthetic','application/pdf',1);
  insert into public.drawings(id,project_id,workspace_id,pdf_page_number) values(drawing_id,project,workspace,1);
  insert into public.agent_runs(id,idempotency_key,request_fingerprint,run_type,status,project_id,
                               source_document_id,requested_by,scope)
    values(run_id,proposal_key,'synthetic','SCOPED_CORRECTION','NEEDS_REVIEW',project,doc,actor,
           jsonb_build_object('type','CONNECTION','id',connection_id));
  insert into public.result_versions(id,project_id,version,status,profile)
    values(result_id,project,1,'accepted',profile);
  insert into public.wiring_units(id,project_id,result_version_id,workspace_id,drawing_id,wire_number)
    values(unit_id,project,result_id,workspace,drawing_id,1000);
  insert into public.wiring_connections(id,wiring_unit_id,source_drawing_id,core_order,start_terminal,end_terminal)
    values(connection_id,unit_id,drawing_id,1,'X1:1','999');
  insert into public.connection_evidence(id,connection_id,drawing_id,kind)
    values(evidence_id,connection_id,drawing_id,'source');
  before_value := jsonb_build_object('connection_id',connection_id,'end_terminal','999');
  after_value := jsonb_build_object('connection_id',connection_id,'end_terminal','2');
  operation := jsonb_build_object('op','replace','target_type','CONNECTION','target_id',connection_id,
                     'expected_version',1,'before',before_value,'after',after_value);
  insert into public.result_proposals(id,agent_run_id,project_id,status,payload) values(
    proposal_key,run_id,project,'READY_FOR_REVIEW',jsonb_build_object('feedback_id',feedback_key,
      'base_result_version',1,'base_result_revision',1,'profile',profile,
      'validation','{"schema_valid":true,"business_rules_valid":true}'::jsonb,
      'operations',jsonb_build_array(operation)));
  insert into public.feedback_items(id,project_id,target_type,target_id,issue_kind,base_result_version,
                                   correction_bundle)
    values(feedback_key,project,'CONNECTION',connection_id,'DIRECT_VALUE_CHANGE',1,'{}');
  select to_jsonb(c) || '{"end_terminal":"2"}'::jsonb into record
    from public.wiring_connections c where id=connection_id;
  request := jsonb_build_object('proposal_id',proposal_key,'project_id',project,'confirmed_by',actor,
    'changes',jsonb_build_array(operation || jsonb_build_object('record',record)),
    'feedback_updates',jsonb_build_array(jsonb_build_object('feedback_id',feedback_key,
      'before',before_value,'after',after_value,'accepted_payload','{}'::jsonb)));
  receipt := public.apply_confirmed_result_patch(request);
  if receipt->>'result_version_id' <> result_id::text or receipt->>'result_revision' <> '2'
     or receipt->>'update_mode' <> 'in_place' then raise exception 'Invalid receipt'; end if;
  if (select count(*) from public.result_versions where project_id=project) <> 1
     or (select count(*) from public.wiring_units where project_id=project) <> 1
     or (select end_terminal from public.wiring_connections where id=connection_id) <> '2'
     or (select record_version from public.wiring_connections where id=connection_id) <> 2
     or not exists(select 1 from public.connection_evidence e
                   where e.id=evidence_id and e.connection_id=smoke.connection_id)
     then raise exception 'IDs/counts/evidence not preserved'; end if;
  if public.apply_confirmed_result_patch(request) <> receipt then raise exception 'Replay changed receipt'; end if;
  if (select revision from public.result_versions where id=result_id) <> 2 then
    raise exception 'Replay changed revision'; end if;
  begin
    perform public.apply_confirmed_result_patch(request || jsonb_build_object('confirmed_by',stranger));
    raise exception 'Unauthorized actor accepted';
  exception when sqlstate 'PT403' then null; end;
  -- Uncommitted stale proposal must not mutate the connection.
  insert into public.result_proposals(id,agent_run_id,project_id,status,payload)
    select proposal_key || ':stale',agent_run_id,project_id,status,payload
    from public.result_proposals where id=proposal_key;
  begin
    perform public.apply_confirmed_result_patch(request || jsonb_build_object('proposal_id',proposal_key || ':stale'));
    raise exception 'Stale revision accepted';
  exception when sqlstate 'PT409' then null; end;
  -- First row updated, second out-of-scope row fails: the whole batch must roll back.
  before_value := jsonb_build_object('connection_id',connection_id,'end_terminal','2');
  after_value := jsonb_build_object('connection_id',connection_id,'end_terminal','3');
  operation := operation || jsonb_build_object('expected_version',2,'before',before_value,'after',after_value);
  second_operation := operation || jsonb_build_object('target_id',gen_random_uuid(),'expected_version',1);
  insert into public.result_proposals(id,agent_run_id,project_id,status,payload) values(
    proposal_key || ':batch',run_id,project,'READY_FOR_REVIEW',jsonb_build_object('feedback_id',feedback_key,
      'base_result_version',1,'base_result_revision',2,'profile',profile,
      'validation','{"schema_valid":true,"business_rules_valid":true}'::jsonb,
      'operations',jsonb_build_array(operation,second_operation)));
  select to_jsonb(c) || '{"end_terminal":"3"}'::jsonb into record
    from public.wiring_connections c where id=connection_id;
  batch := request || jsonb_build_object('proposal_id',proposal_key || ':batch','changes',
    jsonb_build_array(operation || jsonb_build_object('record',record),
                      second_operation || jsonb_build_object('record',record)));
  begin
    perform public.apply_confirmed_result_patch(batch);
    raise exception 'Invalid batch accepted';
  exception when sqlstate 'PT409' then null; end;
  if (select end_terminal from public.wiring_connections where id=connection_id) <> '2' then
    raise exception 'Failed commit changed data'; end if;
  raise notice 'PASS: stable IDs, no snapshot growth, revision, replay, permissions, stale rejection, atomic batch';
end;
$$;
