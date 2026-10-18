-- User-requested hard deletion without retained business-row copies.
-- Only a minimal idempotency request/receipt remains; existing unrelated edits keep audit.
-- No historical data rewrite at deployment. Future deletes purge that row's old copies.
-- Rollback: restore manage_extraction_connection from 20261016020000; deleted snapshots cannot be recovered.
begin;

create or replace function public.manage_extraction_connection(value jsonb) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
declare
  p public.extraction_projects;
  r public.extraction_connection_rows;
  changed public.extraction_connection_rows;
  actor uuid := (value->>'actor')::uuid;
  project uuid := (value->>'project_id')::uuid;
  action text := value->>'action';
  key text := value->>'key';
  body jsonb := value->'body';
  fields jsonb;
  saved jsonb;
  receipt jsonb;
  before_value jsonb := 'null'::jsonb;
  after_value jsonb := 'null'::jsonb;
  management jsonb;
  field_name text;
begin
  if auth.role() is distinct from 'service_role' then
    raise sqlstate 'PT403' using message='Internal row management only';
  end if;
  select * into p from public.extraction_projects where id=project for update;
  if not found then raise sqlstate 'PT404' using message='Project not found'; end if;
  if actor is null or p.owner_id <> actor then
    raise sqlstate 'PT403' using message='Project owner required';
  end if;
  if p.status='processing' then raise sqlstate 'PT409' using message='Extraction results are read only while processing'; end if;
  if p.status='archived' then raise sqlstate 'PT409' using message='Project archived'; end if;
  if key is null or length(key) not between 1 and 200 or action not in ('add','edit','remove') then
    raise sqlstate 'PT422' using message='Invalid management request';
  end if;
  management := coalesce(p.drawing_index->'management','{}'::jsonb);
  saved := management->'receipts'->key;
  if saved is not null then
    if saved->'request' is distinct from value then
      raise sqlstate 'PT409' using message='Idempotency key reused with different input';
    end if;
    return (saved->'receipt') || '{"idempotent":true}'::jsonb;
  end if;
  if action in ('edit','remove') then
    select * into r from public.extraction_connection_rows
      where id=(value->>'connection_id')::uuid and project_id=project for update;
    if not found then raise sqlstate 'PT404' using message='Connection not found'; end if;
    if r.record_version is distinct from (body->>'record_version')::integer then
      raise sqlstate 'PT409' using message='Record version changed';
    end if;
    before_value := to_jsonb(r);
  end if;
  if action='remove' then
    if value - array['actor','project_id','action','key','connection_id','body'] <> '{}'::jsonb
      or jsonb_typeof(body) is distinct from 'object'
      or body - array['record_version','confirmed'] <> '{}'::jsonb then
      raise sqlstate 'PT422' using message='Invalid deletion request';
    end if;
    if body->>'confirmed' is distinct from 'true' then
      raise sqlstate 'PT422' using message='Deletion confirmation required';
    end if;
    delete from public.extraction_connection_rows where id=r.id;
    changed := r;
  else
    fields := coalesce(case when action='edit' then body->'changes' else body->'fields' end,'{}'::jsonb);
    if jsonb_typeof(fields)<>'object' then raise sqlstate 'PT422' using message='Invalid fields'; end if;
    for field_name in select jsonb_object_keys(fields) loop
      if field_name not in ('voltage_level','terminal_strip','principle_number','start_code',
        'start_description','start_terminal','end_code','end_description','end_terminal',
        'current_value','remark','color_mark','is_cross_page') then
        raise sqlstate 'PT422' using message='Unsupported connection field';
      end if;
    end loop;
    if action='add' then
      if nullif(btrim(fields->>'start_terminal'),'') is null
         or nullif(btrim(body->>'batch_id'),'') is null
         or not exists(select 1 from jsonb_array_elements(coalesce(p.drawing_index->'pages','[]')) page
           where (page->>'pdf_page_number')::integer=(body->'source'->>'pdf_page_number')::integer) then
        raise sqlstate 'PT422' using message='Source page and start terminal required';
      end if;
      r.id := gen_random_uuid(); r.project_id := project; r.batch_id := body->>'batch_id';
      r.page_item_id := 'manual:' || r.id::text;
      r.source_pdf_page_number := (body->'source'->>'pdf_page_number')::integer;
      r.workspace_code := body->'source'->>'workspace_code';
      r.source_drawing_page := body->'source'->>'workspace_page';
      r.target_pdf_page_number := (body->'target'->>'pdf_page_number')::integer;
      r.target_drawing_page := body->'target'->>'workspace_page';
      if r.target_pdf_page_number is not null and not exists(
        select 1 from jsonb_array_elements(coalesce(p.drawing_index->'pages','[]')) page
        where (page->>'pdf_page_number')::integer=r.target_pdf_page_number) then
        raise sqlstate 'PT422' using message='Target page is not in this project';
      end if;
      select coalesce(max(row_order),-1)+1 into r.row_order from public.extraction_connection_rows
        where project_id=project and batch_id=r.batch_id and source_pdf_page_number=r.source_pdf_page_number;
      r.wire_number := body->>'wire_number'; r.record_version := 1; r.evidence := '{}'::jsonb;
      r.is_cross_page := coalesce(r.target_pdf_page_number<>r.source_pdf_page_number,false);
      r.needs_review := false;
    end if;
    changed := jsonb_populate_record(r,fields-'is_cross_page'-'voltage_level');
    if fields ? 'is_cross_page' and fields->>'is_cross_page' is not null then
      if fields->>'is_cross_page' not in ('same_page','cross_page','unknown') then
        raise sqlstate 'PT422' using message='Invalid cross-page state';
      end if;
      changed.is_cross_page := fields->>'is_cross_page'='cross_page';
      if fields->>'is_cross_page'='unknown' then changed.needs_review := true; end if;
    end if;
    if not changed.is_cross_page then
      changed.target_pdf_page_number := null; changed.target_drawing_page := null;
    end if;
    if fields ? 'voltage_level' then
      changed.evidence := coalesce(changed.evidence,'{}'::jsonb) || jsonb_build_object('voltage_level',fields->'voltage_level');
    end if;
    changed.needs_review := coalesce(changed.needs_review,false)
      or nullif(btrim(changed.start_terminal),'') is null
      or nullif(btrim(changed.end_terminal),'') is null
      or (changed.is_cross_page and changed.target_pdf_page_number is null);
    if action='add' then
      changed.created_at := now(); changed.updated_at := now();
      insert into public.extraction_connection_rows select changed.* returning * into changed;
    else
      update public.extraction_connection_rows set
        principle_number=changed.principle_number,terminal_strip=changed.terminal_strip,
        start_code=changed.start_code,start_description=changed.start_description,start_terminal=changed.start_terminal,
        end_code=changed.end_code,end_description=changed.end_description,end_terminal=changed.end_terminal,
        current_value=changed.current_value,color_mark=changed.color_mark,remark=changed.remark,
        is_cross_page=changed.is_cross_page,target_pdf_page_number=changed.target_pdf_page_number,
        target_drawing_page=changed.target_drawing_page,needs_review=changed.needs_review,evidence=changed.evidence
        where id=r.id returning * into changed;
    end if;
    after_value := to_jsonb(changed);
  end if;
  receipt := jsonb_build_object('connection_id',changed.id,'batch_id',changed.batch_id,
    'action',action,'record_version',changed.record_version,'idempotent',false);
  if action='remove' then
    -- No deleted business-row snapshots, including older edits of this row.
    management := management || jsonb_build_object(
      'receipts',coalesce((select jsonb_object_agg(entry.key,entry.value)
        from jsonb_each(coalesce(management->'receipts','{}'::jsonb)) entry
        where entry.value->'receipt'->>'connection_id' is distinct from r.id::text
          and entry.value->'request'->>'connection_id' is distinct from r.id::text),'{}'::jsonb)
        || jsonb_build_object(key,jsonb_build_object('request',value,'receipt',receipt)),
      'audit',coalesce((select jsonb_agg(entry.value order by entry.ordinality)
        from jsonb_array_elements(coalesce(management->'audit','[]'::jsonb)) with ordinality entry
        where entry.value->'before'->>'id' is distinct from r.id::text
          and entry.value->'after'->>'id' is distinct from r.id::text),'[]'::jsonb));
    -- A proposal cannot retain removed row values or be confirmed with a partial scope.
    delete from public.connection_edit_proposals proposal where proposal.project_id=project
      and (exists(select 1 from jsonb_array_elements(proposal.selected_rows) item where item->>'id'=r.id::text)
        or exists(select 1 from jsonb_array_elements(proposal.changes) item where item->>'connection_id'=r.id::text));
  else
    management := management || jsonb_build_object(
      'receipts',coalesce(management->'receipts','{}'::jsonb) || jsonb_build_object(key,jsonb_build_object('request',value,'receipt',receipt)),
      'audit',coalesce(management->'audit','[]'::jsonb) || jsonb_build_array(jsonb_build_object(
        'action',action,'actor',actor,'time',now(),'before',before_value,'after',after_value)));
  end if;
  update public.extraction_projects set drawing_index=jsonb_set(drawing_index,'{management}',management)
    where id=project;
  return receipt;
end;
$$;

revoke all on function public.manage_extraction_connection(jsonb) from public,anon,authenticated;
grant execute on function public.manage_extraction_connection(jsonb) to service_role;
notify pgrst,'reload schema';
commit;
