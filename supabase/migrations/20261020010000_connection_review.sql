-- Explicit human review. Rollback: remove the API route, then drop this function.
-- Existing review decisions/audits remain; no historical rows are rewritten here.
begin;
create function public.review_extraction_connection(value jsonb) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
declare
  p public.extraction_projects;
  r public.extraction_connection_rows;
  changed public.extraction_connection_rows;
  management jsonb;
  saved jsonb;
  receipt jsonb;
  actor uuid := (value->>'actor')::uuid;
  request_key text := value->>'key';
  active_batch text;
begin
  if auth.role() is distinct from 'service_role' then
    raise sqlstate 'PT403' using message='Internal review only';
  end if;
  select * into p from public.extraction_projects where id=(value->>'project_id')::uuid for update;
  if not found then raise sqlstate 'PT404' using message='Project not found'; end if;
  if actor is null or actor <> p.owner_id then raise sqlstate 'PT403' using message='Project owner required'; end if;
  if p.status in ('processing','archived') then raise sqlstate 'PT409' using message='Project results are read only'; end if;
  if request_key is null or length(request_key) not between 1 and 200
    or jsonb_typeof(value->'body') is distinct from 'object'
    or (value->'body') - array['record_version','confirmed'] <> '{}'::jsonb
    or value->'body'->'confirmed' is distinct from 'true'::jsonb
    or coalesce((value->'body'->>'record_version')::integer,0) < 1 then
    raise sqlstate 'PT422' using message='Invalid review request';
  end if;
  management := coalesce(p.drawing_index->'management','{}'::jsonb);
  saved := management->'receipts'->request_key;
  if saved is not null then
    if saved->'request' is distinct from value then raise sqlstate 'PT409' using message='Idempotency key reused'; end if;
    return (saved->'receipt') || '{"idempotent":true}'::jsonb;
  end if;
  select * into r from public.extraction_connection_rows
    where id=(value->>'connection_id')::uuid and project_id=p.id for update;
  if not found then raise sqlstate 'PT404' using message='Connection not found'; end if;
  active_batch := p.drawing_index->>'active_batch_id';
  if active_batch is null then
    select batch_id into active_batch from public.extraction_connection_rows
      where project_id=p.id order by created_at desc,id desc limit 1;
  end if;
  if r.batch_id is distinct from active_batch or r.record_version is distinct from (value->'body'->>'record_version')::integer then
    raise sqlstate 'PT409' using message='Result version changed; refresh before review';
  end if;
  if not r.needs_review then raise sqlstate 'PT409' using message='Connection already reviewed'; end if;
  update public.extraction_connection_rows set needs_review=false,
    evidence=coalesce(evidence,'{}'::jsonb) || jsonb_build_object('human_review',jsonb_build_object(
      'actor',actor,'time',now(),'reviewed_record_version',r.record_version))
    where id=r.id returning * into changed;
  -- The existing row trigger increments record_version and updated_at.
  receipt := jsonb_build_object('connection_id',r.id,'batch_id',r.batch_id,'action','review',
    'record_version',changed.record_version,'idempotent',false);
  management := management || jsonb_build_object(
    'receipts',coalesce(management->'receipts','{}'::jsonb) || jsonb_build_object(request_key,jsonb_build_object('request',value,'receipt',receipt)),
    'audit',coalesce(management->'audit','[]'::jsonb) || jsonb_build_array(jsonb_build_object(
      'action','review','actor',actor,'time',now(),'before',to_jsonb(r),'after',to_jsonb(changed))));
  update public.extraction_projects set drawing_index=jsonb_set(drawing_index,'{management}',management) where id=p.id;
  return receipt;
end;
$$;
revoke all on function public.review_extraction_connection(jsonb) from public,anon,authenticated;
grant execute on function public.review_extraction_connection(jsonb) to service_role;
notify pgrst, 'reload schema';
commit;
