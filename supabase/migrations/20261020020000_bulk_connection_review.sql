-- Atomic review of the selected directory/search scope across all result pages.
-- Rollback: remove callers, then drop this function; existing reviews/audits remain.
begin;
create function public.review_extraction_scope(value jsonb) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
declare
  p public.extraction_projects;
  actor uuid := (value->>'actor')::uuid;
  request_key text := value->>'key';
  body jsonb := value->'body';
  scope jsonb := value->'scope';
  workspace text := scope->>'workspace_code';
  pdf integer := (scope->>'pdf_page_number')::integer;
  query text := coalesce(scope->>'search','');
  active_batch text;
  management jsonb;
  saved jsonb;
  receipt jsonb;
  audit_rows jsonb;
  reviewed integer;
begin
  if auth.role() is distinct from 'service_role' then raise sqlstate 'PT403' using message='Internal review only'; end if;
  select * into p from public.extraction_projects where id=(value->>'project_id')::uuid for update;
  if not found then raise sqlstate 'PT404' using message='Project not found'; end if;
  if actor is null or actor<>p.owner_id then raise sqlstate 'PT403' using message='Project owner required'; end if;
  if p.status in ('processing','archived') then raise sqlstate 'PT409' using message='Project results are read only'; end if;
  if request_key is null or length(request_key) not between 1 and 200
    or jsonb_typeof(body) is distinct from 'object' or body->'confirmed' is distinct from 'true'::jsonb
    or nullif(body->>'batch_id','') is null or nullif(body->>'expected_updated_at','') is null
    or jsonb_typeof(scope) is distinct from 'object' or length(query)>100 then
    raise sqlstate 'PT422' using message='Invalid bulk review request';
  end if;
  management := coalesce(p.drawing_index->'management','{}'::jsonb);
  saved := management->'receipts'->request_key;
  if saved is not null then
    if saved->'request' is distinct from value then raise sqlstate 'PT409' using message='Idempotency key reused'; end if;
    return (saved->'receipt') || '{"idempotent":true}'::jsonb;
  end if;
  active_batch := p.drawing_index->>'active_batch_id';
  if active_batch is null then
    select batch_id into active_batch from public.extraction_connection_rows where project_id=p.id order by created_at desc,id desc limit 1;
  end if;
  if active_batch is distinct from body->>'batch_id' or p.updated_at is distinct from (body->>'expected_updated_at')::timestamptz then
    raise sqlstate 'PT409' using message='Result version changed; refresh before bulk review';
  end if;
  if (workspace is not null or pdf is not null) and not exists(
    select 1 from jsonb_array_elements(coalesce(p.drawing_index->'pages','[]')) page
    where (workspace is null or coalesce(page->>'workspace_code','')=workspace)
      and (pdf is null or (page->>'pdf_page_number')::integer=pdf)
  ) then raise sqlstate 'PT422' using message='Review scope is not in this project'; end if;

  with picked as materialized (
    select r.* from public.extraction_connection_rows r
    where r.project_id=p.id and r.batch_id=active_batch and r.needs_review
      and (workspace is null or coalesce(r.workspace_code,'')=workspace)
      and (pdf is null or r.source_pdf_page_number=pdf)
      and (query='' or r.start_terminal ilike '%'||query||'%' or r.end_terminal ilike '%'||query||'%'
        or r.principle_number ilike '%'||query||'%' or r.start_description ilike '%'||query||'%'
        or r.end_description ilike '%'||query||'%')
    order by r.source_pdf_page_number,r.row_order,r.id for update
  ), changed as (
    update public.extraction_connection_rows r set needs_review=false,
      evidence=coalesce(r.evidence,'{}'::jsonb) || jsonb_build_object('human_review',jsonb_build_object(
        'actor',actor,'time',now(),'reviewed_record_version',r.record_version,'scope_request_key',request_key))
    from picked old where r.id=old.id
    returning to_jsonb(old) as before_value,to_jsonb(r) as after_value
  )
  select count(*),coalesce(jsonb_agg(jsonb_build_object('action','review','actor',actor,'time',now(),
    'scope_request_key',request_key,'before',before_value,'after',after_value)),'[]'::jsonb)
    into reviewed,audit_rows from changed;
  receipt := jsonb_build_object('project_id',p.id,'batch_id',active_batch,'reviewed_count',reviewed,'idempotent',false);
  management := management || jsonb_build_object(
    'receipts',coalesce(management->'receipts','{}'::jsonb) || jsonb_build_object(request_key,jsonb_build_object('request',value,'receipt',receipt)),
    'audit',coalesce(management->'audit','[]'::jsonb) || audit_rows);
  update public.extraction_projects set drawing_index=jsonb_set(drawing_index,'{management}',management) where id=p.id;
  return receipt;
end;
$$;
revoke all on function public.review_extraction_scope(jsonb) from public,anon,authenticated;
grant execute on function public.review_extraction_scope(jsonb) to service_role;
notify pgrst, 'reload schema';
commit;
