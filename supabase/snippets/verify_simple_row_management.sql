-- Run after the function definition in an outer transaction. Probe data is rolled back.
savepoint simple_row_management_probe;
set local request.jwt.claim.role = 'service_role';
do $$
declare
  actor uuid; other_actor uuid; profile uuid := gen_random_uuid(); project uuid := gen_random_uuid();
  request jsonb; result jsonb; again jsonb; identifier uuid; audit jsonb; receipts jsonb;
begin
  select id into actor from auth.users order by id limit 1;
  select id into other_actor from auth.users order by id offset 1 limit 1;
  if actor is null or other_actor is null then raise exception 'Two existing Auth identities required'; end if;
  insert into public.extraction_profiles(id,profile_key,profile_version,checksum,resource_ref,display_name,created_by)
    values(profile,'crud_probe','0.0.0','sha256:'||repeat('0',64),'temporary/probe','Probe',actor);
  insert into public.extraction_projects(id,owner_id,name,profile_id,drawing_index)
    values(project,actor,'Probe',profile,'{"pages":[{"pdf_page_number":1,"workspace_code":"003.C","drawing_page":"003C01"},{"pdf_page_number":2,"workspace_code":"004.C","drawing_page":"004C01"}]}'::jsonb);
  request := jsonb_build_object('project_id',project,'actor',actor,'action','add','key','add-one',
    'body',jsonb_build_object('batch_id','probe','source',jsonb_build_object('pdf_page_number',1,'workspace_code','003.C','workspace_page','003C01'),
      'target',jsonb_build_object('pdf_page_number',2,'workspace_page','004C01'),
      'fields',jsonb_build_object('start_terminal','XA:8','end_terminal','XD10:1','terminal_strip','X1')));
  result := public.manage_extraction_connection(request);
  identifier := (result->>'connection_id')::uuid;
  again := public.manage_extraction_connection(request);
  if again->>'idempotent'<>'true' or again->>'connection_id'<>result->>'connection_id'
     or (select count(*) from public.extraction_connection_rows where project_id=project)<>1 then
    raise exception 'Add replay failed';
  end if;
  begin
    perform public.manage_extraction_connection(jsonb_set(request,'{body,fields,end_terminal}','"different"'));
    raise exception 'Different payload with same key was accepted';
  exception when sqlstate 'PT409' then null;
  end;
  request := jsonb_build_object('project_id',project,'actor',actor,'action','edit','connection_id',identifier,'key','edit-one',
    'body',jsonb_build_object('record_version',1,'changes',jsonb_build_object('end_terminal','XD10:2','voltage_level','380VAC')));
  result := public.manage_extraction_connection(request);
  if (result->>'record_version')::integer<>2
     or (select end_terminal from public.extraction_connection_rows where id=identifier)<>'XD10:2'
     or (select evidence->>'voltage_level' from public.extraction_connection_rows where id=identifier)<>'380VAC' then
    raise exception 'Row edit/version failed';
  end if;
  begin
    perform public.manage_extraction_connection(jsonb_set(request,'{key}','"stale-edit"'));
    raise exception 'Stale version was accepted';
  exception when sqlstate 'PT409' then null;
  end;
  begin
    perform public.manage_extraction_connection(jsonb_set(jsonb_set(request,'{key}','"other-owner"'),'{actor}',to_jsonb(other_actor)));
    raise exception 'Other owner was accepted';
  exception when sqlstate 'PT403' then null;
  end;
  request := jsonb_build_object('project_id',project,'actor',actor,'action','remove','connection_id',identifier,'key','remove-one',
    'body',jsonb_build_object('record_version',2,'confirmed',true));
  perform public.manage_extraction_connection(request);
  again := public.manage_extraction_connection(request);
  if again->>'idempotent'<>'true' or exists(select 1 from public.extraction_connection_rows where id=identifier) then
    raise exception 'Delete replay failed';
  end if;
  select drawing_index->'management'->'audit',drawing_index->'management'->'receipts'
    into audit,receipts from public.extraction_projects where id=project;
  if jsonb_array_length(audit)<>3 or audit->1->'before'->>'end_terminal'<>'XD10:1'
     or audit->1->'after'->>'end_terminal'<>'XD10:2'
     or (select count(*) from jsonb_object_keys(receipts))<>3 then
    raise exception 'Audit or receipts invalid';
  end if;
end;
$$;
-- Inspect ACLs rather than execute a denied function inside a nested DO handler:
-- the local Postgres build crashed on that denial probe during initial validation.
do $$ begin
  if has_function_privilege('authenticated','public.manage_extraction_connection(jsonb)','EXECUTE')
     or has_function_privilege('anon','public.manage_extraction_connection(jsonb)','EXECUTE')
     or not has_function_privilege('service_role','public.manage_extraction_connection(jsonb)','EXECUTE') then
    raise exception 'Mutation RPC execution permissions invalid';
  end if;
end $$;
rollback to savepoint simple_row_management_probe;
release savepoint simple_row_management_probe;
select 'add/edit/delete, audit, replay, conflict and owner permissions passed' as validation;
