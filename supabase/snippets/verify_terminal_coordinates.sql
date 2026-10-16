-- Run inside an outer transaction after the coordinate migration. No probe rows remain.
savepoint terminal_coordinate_probe;
set local request.jwt.claim.role='service_role';
do $$
declare
  actor uuid; profile uuid:=gen_random_uuid(); project uuid:=gen_random_uuid(); identifier uuid:=gen_random_uuid();
  start_point jsonb:='{"x":0.17773,"y":0.53735,"pdf_page_number":60}';
  end_point jsonb:='{"x":0.17773,"y":0.17302,"pdf_page_number":403}';
  bad jsonb;
begin
  select id into actor from auth.users order by id limit 1;
  if actor is null then raise exception 'Existing Auth identity required'; end if;
  insert into public.extraction_profiles(id,profile_key,profile_version,checksum,resource_ref,display_name,created_by)
    values(profile,'coordinate_probe','0.0.0','sha256:'||repeat('0',64),'temporary/probe','Probe',actor);
  insert into public.extraction_projects(id,owner_id,name,profile_id) values(project,actor,'Probe',profile);
  insert into public.extraction_connection_rows(id,project_id,batch_id,page_item_id,row_order,source_pdf_page_number,
    target_pdf_page_number,start_terminal,end_terminal,is_cross_page,start_terminal_coordinates,end_terminal_coordinates)
    values(identifier,project,'probe','point',0,60,403,'XA:8','XD10:1',true,start_point,end_point);
  update public.extraction_connection_rows set remark='unrelated edit' where id=identifier;
  if not exists(select 1 from public.extraction_connection_rows where id=identifier
      and start_terminal_coordinates=start_point and end_terminal_coordinates=end_point) then
    raise exception 'Non-endpoint edit lost coordinates';
  end if;
  perform public.manage_extraction_connection(jsonb_build_object('actor',actor,'project_id',project,
    'action','edit','key','coordinate-edit','connection_id',identifier,
    'body',jsonb_build_object('record_version',2,'changes',jsonb_build_object('end_terminal','XD10:2'))));
  if not exists(select 1 from public.extraction_connection_rows where id=identifier
      and start_terminal_coordinates=start_point and end_terminal_coordinates is null) then
    raise exception 'RPC endpoint edit did not clear only the changed endpoint';
  end if;
  if not exists(select 1 from public.extraction_projects where id=project
      and drawing_index->'management'->'audit'->0->'before'->'end_terminal_coordinates'=end_point
      and drawing_index->'management'->'audit'->0->'after'->'end_terminal_coordinates'='null'::jsonb) then
    raise exception 'Coordinate before/after audit missing';
  end if;
  update public.extraction_connection_rows set start_terminal='XA:9' where id=identifier;
  if exists(select 1 from public.extraction_connection_rows where id=identifier and start_terminal_coordinates is not null) then
    raise exception 'Start endpoint edit kept stale coordinates';
  end if;
  update public.extraction_connection_rows set start_terminal='XA:10',
    start_terminal_coordinates='{"x":0.3,"y":0.6,"pdf_page_number":60}',end_terminal_coordinates=end_point
    where id=identifier;
  if not exists(select 1 from public.extraction_connection_rows where id=identifier and start_terminal_coordinates->>'x'='0.3') then
    raise exception 'New explicit coordinates not preserved';
  end if;
  update public.extraction_connection_rows set target_pdf_page_number=404 where id=identifier;
  if exists(select 1 from public.extraction_connection_rows where id=identifier and end_terminal_coordinates is not null) then
    raise exception 'Target page change kept stale coordinates';
  end if;
  foreach bad in array array[
    '{"x":-0.1,"y":0.5,"pdf_page_number":60}'::jsonb,
    '{"x":0.1,"y":1.5,"pdf_page_number":60}'::jsonb,
    '{"x":0.1,"y":0.5,"pdf_page_number":0}'::jsonb,
    '{"x":0.1,"y":0.5,"pdf_page_number":1.5}'::jsonb,
    '{"x":"0.1","y":0.5,"pdf_page_number":60}'::jsonb,
    '{"x":true,"y":0.5,"pdf_page_number":60}'::jsonb,
    '{"x":0.1,"y":0.5}'::jsonb,
    '{"x":0.1,"y":0.5,"pdf_page_number":60,"extra":1}'::jsonb,
    'null'::jsonb
  ] loop
    begin
      update public.extraction_connection_rows set start_terminal_coordinates=bad where id=identifier;
      raise exception 'Invalid coordinates accepted: %',bad;
    exception when check_violation then null;
    end;
  end loop;
end $$;
rollback to savepoint terminal_coordinate_probe;
release savepoint terminal_coordinate_probe;
select 'coordinate shape/bounds, per-endpoint page, stale clearing and CRUD audit passed' as validation;
