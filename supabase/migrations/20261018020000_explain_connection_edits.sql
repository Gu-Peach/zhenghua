-- User-confirmed Explain edits. New objects only; no changes to existing rows on deployment.
-- Rollback after callers stop: drop new RPCs/helpers and table (audit would be lost).
begin;
create table public.connection_edit_proposals (
  proposal_id uuid primary key,
  project_id uuid not null references public.extraction_projects(id) on delete cascade,
  created_by uuid not null references auth.users(id) on delete restrict,
  batch_id text not null check(length(batch_id) between 1 and 200),
  status text not null default 'pending' check(status in ('pending','applied','rejected')),
  request jsonb not null check(jsonb_typeof(request)='object'),
  user_request text not null,
  selected_rows jsonb not null check(jsonb_typeof(selected_rows)='array'),
  changes jsonb not null check(jsonb_typeof(changes)='array'),
  matched_count integer not null check(matched_count between 0 and 1000),
  changed_count integer not null check(changed_count between 0 and matched_count),
  checksum text not null check(checksum ~ '^sha256:[0-9a-f]{64}$'),
  index_checksum text not null,
  receipt jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  expires_at timestamptz not null default now()+interval '24 hours'
);
create index connection_edit_proposals_project_owner on public.connection_edit_proposals(project_id,created_by,created_at desc);
alter table public.connection_edit_proposals enable row level security;
create policy connection_edit_proposals_read on public.connection_edit_proposals for select to authenticated
using(created_by=auth.uid() and exists(select 1 from public.extraction_projects p where p.id=project_id and p.owner_id=auth.uid()));
revoke all on public.connection_edit_proposals from public,anon,authenticated;
grant select on public.connection_edit_proposals to authenticated;
grant select,insert,update on public.connection_edit_proposals to service_role;

create function public.explain_edit_public(p public.connection_edit_proposals) returns jsonb
language sql immutable set search_path=public as $$
select to_jsonb(p)-'created_by'-'selected_rows'-'user_request'-'receipt'-'updated_at'-'index_checksum'
$$;

create function public.explain_edit_matches(r public.extraction_connection_rows, scope jsonb) returns boolean
language sql immutable set search_path=public as $$
select (not scope ? 'workspace_code' or scope->>'workspace_code' is null or r.workspace_code=scope->>'workspace_code')
and (not scope ? 'drawing_page' or scope->>'drawing_page' is null or r.source_drawing_page=scope->>'drawing_page')
and (jsonb_array_length(coalesce(scope->'principle_numbers','[]'))=0 or exists(select 1 from jsonb_array_elements_text(scope->'principle_numbers') n where n=r.principle_number))
and (jsonb_array_length(coalesce(scope->'connection_ids','[]'))=0 or exists(select 1 from jsonb_array_elements_text(scope->'connection_ids') n where n=r.id::text))
$$;

create function public.explain_edit_fields(r public.extraction_connection_rows, op jsonb, pages jsonb) returns jsonb
language plpgsql set search_path=public as $$
declare result jsonb:='{}'; kind text:=op->>'kind'; side text; prefix_value text; field text;
  src integer; dst integer; page jsonb; count_pages integer; final_value jsonb;
begin
  if kind='remove_terminal_prefix' then
    side:=op->>'endpoint'; prefix_value:=op->>'prefix';
    if side not in ('start','end') or prefix_value is null or length(prefix_value) not between 1 and 80 then
      raise sqlstate 'PT422' using message='Invalid terminal prefix operation'; end if;
    field:=side||'_terminal';
    if left(to_jsonb(r)->>field,length(prefix_value))=prefix_value then
      result:=jsonb_build_object(field,nullif(substr(to_jsonb(r)->>field,length(prefix_value)+1),''));
      if result->>field is null then result:=result||jsonb_build_object(side||'_terminal_coordinates',null); end if;
    end if;
  elsif kind in ('swap_endpoints','swap_terminals') then
    result:=jsonb_build_object('start_terminal',r.end_terminal,'end_terminal',r.start_terminal);
    if kind='swap_terminals' then
      result:=result||jsonb_build_object('start_terminal_coordinates',null,'end_terminal_coordinates',null);
    else
      src:=case when r.is_cross_page then r.target_pdf_page_number else r.source_pdf_page_number end;
      dst:=r.source_pdf_page_number;
      if src is null then raise sqlstate 'PT422' using message='SWAP_TARGET_UNCONFIRMED'; end if;
      select count(*) into count_pages from jsonb_array_elements(coalesce(pages,'[]')) t where (t->>'pdf_page_number')::integer=src;
      if count_pages<>1 then raise sqlstate 'PT422' using message='SWAP_SOURCE_NOT_INDEXED'; end if;
      select t into page from jsonb_array_elements(pages) t where (t->>'pdf_page_number')::integer=src;
      result:=result||jsonb_build_object(
        'start_code',r.end_code,'end_code',r.start_code,
        'start_description',r.end_description,'end_description',r.start_description,
        'start_terminal_coordinates',r.end_terminal_coordinates,'end_terminal_coordinates',r.start_terminal_coordinates,
        'source_pdf_page_number',src,'source_drawing_page',coalesce(page->>'drawing_page',r.target_drawing_page,r.source_drawing_page),
        'workspace_code',coalesce(page->>'workspace_code',r.workspace_code),
        'target_pdf_page_number',case when src<>dst then dst else null end,
        'target_drawing_page',case when src<>dst then r.source_drawing_page else null end);
    end if;
  elsif kind='set_fields' then
    result:=op->'changes';
    if jsonb_typeof(result) is distinct from 'object' or result='{}' then raise sqlstate 'PT422' using message='Empty fields'; end if;
    for field in select jsonb_object_keys(result) loop
      if field not in ('principle_number','terminal_strip','start_code','start_description','start_terminal',
        'end_code','end_description','end_terminal','current_value','color_mark','remark')
        or jsonb_typeof(result->field) not in ('string','null') or length(result->>field)>2000 then
        raise sqlstate 'PT422' using message='Unsupported field'; end if;
    end loop;
    if result ? 'start_terminal' and result->'start_terminal' is distinct from to_jsonb(r)->'start_terminal' then result:=result||jsonb_build_object('start_terminal_coordinates',null); end if;
    if result ? 'end_terminal' and result->'end_terminal' is distinct from to_jsonb(r)->'end_terminal' then result:=result||jsonb_build_object('end_terminal_coordinates',null); end if;
  else raise sqlstate 'PT422' using message='Unsupported edit operation'; end if;
  -- Match the established clear_stale_extraction_coordinates trigger exactly.
  final_value:=to_jsonb(r)||result;
  if (final_value->'start_terminal' is distinct from to_jsonb(r)->'start_terminal'
      or final_value->'source_pdf_page_number' is distinct from to_jsonb(r)->'source_pdf_page_number')
    and final_value->'start_terminal_coordinates' is not distinct from to_jsonb(r)->'start_terminal_coordinates' then
    result:=result||jsonb_build_object('start_terminal_coordinates',null);
  end if;
  if (final_value->'end_terminal' is distinct from to_jsonb(r)->'end_terminal'
      or final_value->'target_pdf_page_number' is distinct from to_jsonb(r)->'target_pdf_page_number'
      or final_value->'source_pdf_page_number' is distinct from to_jsonb(r)->'source_pdf_page_number')
    and final_value->'end_terminal_coordinates' is not distinct from to_jsonb(r)->'end_terminal_coordinates' then
    result:=result||jsonb_build_object('end_terminal_coordinates',null);
  end if;
  if result<>'{}' and (nullif(btrim((to_jsonb(r)||result)->>'start_terminal'),'') is null
    or nullif(btrim((to_jsonb(r)||result)->>'end_terminal'),'') is null) then
    result:=result||'{"needs_review":true}'::jsonb;
  end if;
  -- Exclude no-op assignments. Only changed columns enter the user's preview.
  select coalesce(jsonb_object_agg(e.key,e.value),'{}') into result from jsonb_each(result) e
    where e.value is distinct from to_jsonb(r)->e.key;
  return result;
end $$;

create function public.prepare_explain_connection_edit(value jsonb) returns jsonb
language plpgsql security definer set search_path=public as $$
declare p public.extraction_projects; proposal public.connection_edit_proposals; r public.extraction_connection_rows;
  actor uuid:=(value->>'actor')::uuid; project uuid:=(value->>'project_id')::uuid;
  bid text:=value->>'batch_id'; request jsonb:=value->'request'; scope jsonb:=request->'scope'; op jsonb:=request->'operation';
  selected jsonb:='[]'; changes jsonb:='[]'; fields jsonb; before_value jsonb; active text; counter integer:=0;
begin
  if auth.role() is distinct from 'service_role' then raise sqlstate 'PT403' using message='Internal proposal preparation only'; end if;
  select * into p from public.extraction_projects where id=project for update;
  if not found or p.owner_id is distinct from actor then raise sqlstate 'PT403' using message='Project owner required'; end if;
  if p.status in ('archived','processing') then raise sqlstate 'PT409' using message='Project not editable'; end if;
  if bid is null or length(bid) not between 1 and 200 or jsonb_typeof(scope) is distinct from 'object'
    or not (nullif(scope->>'workspace_code','') is not null or nullif(scope->>'drawing_page','') is not null
      or jsonb_array_length(coalesce(scope->'principle_numbers','[]'))>0 or jsonb_array_length(coalesce(scope->'connection_ids','[]'))>0) then
    raise sqlstate 'PT422' using message='Exact scope and batch required'; end if;
  active:=coalesce(p.drawing_index->>'active_batch_id',(select batch_id from public.extraction_connection_rows where project_id=project order by created_at desc,id desc limit 1));
  if active is distinct from bid then raise sqlstate 'PT409' using message='Active batch changed'; end if;
  select * into proposal from public.connection_edit_proposals where proposal_id=(value->>'proposal_id')::uuid;
  if found then
    if proposal.project_id<>project or proposal.created_by<>actor or proposal.batch_id<>bid or proposal.request is distinct from request
      or proposal.user_request is distinct from value->>'user_request' then raise sqlstate 'PT409' using message='Proposal request changed'; end if;
    return public.explain_edit_public(proposal);
  end if;
  for r in select * from public.extraction_connection_rows rows where rows.project_id=project and rows.batch_id=bid
    and public.explain_edit_matches(rows,scope) order by id for update loop
    counter:=counter+1;
    if counter>1000 then raise sqlstate 'PT422' using message='EDIT_SCOPE_TOO_LARGE'; end if;
    selected:=selected||jsonb_build_array(jsonb_build_object('id',r.id,'version',r.record_version));
    fields:=public.explain_edit_fields(r,op,p.drawing_index->'pages');
    if fields<>'{}' then
      select jsonb_object_agg(key,to_jsonb(r)->key) into before_value from jsonb_object_keys(fields) key;
      changes:=changes||jsonb_build_array(jsonb_build_object('connection_id',r.id,'record_version',r.record_version,
        'principle_number',r.principle_number,'workspace_code',r.workspace_code,'source_drawing_page',r.source_drawing_page,'before',before_value,'after',fields));
    end if;
  end loop;
  insert into public.connection_edit_proposals(proposal_id,project_id,created_by,batch_id,request,user_request,selected_rows,changes,matched_count,changed_count,checksum,index_checksum)
    values((value->>'proposal_id')::uuid,project,actor,bid,request,left(coalesce(value->>'user_request',''),8000),selected,changes,counter,jsonb_array_length(changes),
      'sha256:'||encode(sha256(convert_to(jsonb_build_array(project,actor,bid,request,selected,changes)::text,'UTF8')),'hex'),
      encode(sha256(convert_to(coalesce(p.drawing_index->'pages','[]')::text,'UTF8')),'hex')) returning * into proposal;
  return public.explain_edit_public(proposal);
end $$;

create function public.decide_explain_connection_edit(value jsonb) returns jsonb
language plpgsql security definer set search_path=public as $$
declare p public.extraction_projects; proposal public.connection_edit_proposals; r public.extraction_connection_rows;
  actor uuid:=(value->>'actor')::uuid; project uuid:=(value->>'project_id')::uuid; accepted boolean:=(value->>'accepted')::boolean;
  selected jsonb:='[]'; change jsonb; updated public.extraction_connection_rows; active text; versions jsonb:='{}'; decision_receipt jsonb;
begin
  if auth.role() is distinct from 'service_role' then raise sqlstate 'PT403' using message='Internal edit confirmation only'; end if;
  select * into p from public.extraction_projects where id=project for update;
  if not found or p.owner_id is distinct from actor then raise sqlstate 'PT403' using message='Project owner required'; end if;
  select * into proposal from public.connection_edit_proposals where proposal_id=(value->>'proposal_id')::uuid and project_id=project and created_by=actor for update;
  if not found then raise sqlstate 'PT404' using message='Edit proposal not found'; end if;
  if accepted is null or value->>'checksum' is distinct from proposal.checksum then raise sqlstate 'PT409' using message='Proposal checksum changed'; end if;
  if proposal.status<>'pending' then
    if (proposal.status='applied') is distinct from accepted then raise sqlstate 'PT409' using message='Proposal already decided'; end if;
    return proposal.receipt||'{"idempotent":true}'::jsonb;
  end if;
  if accepted then
    if p.status in ('archived','processing') then raise sqlstate 'PT409' using message='Project not editable'; end if;
    if proposal.expires_at<now() then raise sqlstate 'PT409' using message='Edit proposal expired'; end if;
    active:=coalesce(p.drawing_index->>'active_batch_id',(select batch_id from public.extraction_connection_rows where project_id=project order by created_at desc,id desc limit 1));
    if active is distinct from proposal.batch_id then raise sqlstate 'PT409' using message='Active batch changed'; end if;
    if proposal.request->'operation'->>'kind'='swap_endpoints' and proposal.index_checksum is distinct from
      encode(sha256(convert_to(coalesce(p.drawing_index->'pages','[]')::text,'UTF8')),'hex') then
      raise sqlstate 'PT409' using message='Drawing index changed'; end if;
    for r in select * from public.extraction_connection_rows rows where rows.project_id=project and rows.batch_id=proposal.batch_id
      and public.explain_edit_matches(rows,proposal.request->'scope') order by id for update loop
      selected:=selected||jsonb_build_array(jsonb_build_object('id',r.id,'version',r.record_version));
      if jsonb_array_length(selected)>1000 then raise sqlstate 'PT409' using message='Edit scope changed'; end if;
    end loop;
    if selected is distinct from proposal.selected_rows then raise sqlstate 'PT409' using message='Edit scope or row version changed'; end if;
    for change in select * from jsonb_array_elements(proposal.changes) loop
      select * into r from public.extraction_connection_rows where id=(change->>'connection_id')::uuid and project_id=project;
      updated:=jsonb_populate_record(r,change->'after');
      update public.extraction_connection_rows set
        principle_number=updated.principle_number,terminal_strip=updated.terminal_strip,
        start_code=updated.start_code,start_description=updated.start_description,start_terminal=updated.start_terminal,
        end_code=updated.end_code,end_description=updated.end_description,end_terminal=updated.end_terminal,
        start_terminal_coordinates=updated.start_terminal_coordinates,end_terminal_coordinates=updated.end_terminal_coordinates,
        source_pdf_page_number=updated.source_pdf_page_number,source_drawing_page=updated.source_drawing_page,workspace_code=updated.workspace_code,
        target_pdf_page_number=updated.target_pdf_page_number,target_drawing_page=updated.target_drawing_page,
        current_value=updated.current_value,color_mark=updated.color_mark,remark=updated.remark,needs_review=updated.needs_review,
        evidence=coalesce(r.evidence,'{}')||jsonb_build_object('manual_change',jsonb_build_object('proposal_id',proposal.proposal_id,
          'operation',proposal.request->'operation'->>'kind','time',now(),'fields',change->'after'))
        where id=r.id returning record_version into updated.record_version;
      versions:=versions||jsonb_build_object(r.id::text,updated.record_version);
    end loop;
    update public.extraction_projects set updated_at=now() where id=project;
  end if;
  decision_receipt:=jsonb_build_object('proposal_id',proposal.proposal_id,'project_id',project,'batch_id',proposal.batch_id,
    'status',case when accepted then 'applied' else 'rejected' end,'changed_count',case when accepted then proposal.changed_count else 0 end,
    'versions',versions,'idempotent',false);
  update public.connection_edit_proposals set status=decision_receipt->>'status',receipt=decision_receipt,updated_at=now() where proposal_id=proposal.proposal_id;
  return decision_receipt;
end $$;
revoke all on function public.explain_edit_public(public.connection_edit_proposals),public.explain_edit_matches(public.extraction_connection_rows,jsonb),
  public.explain_edit_fields(public.extraction_connection_rows,jsonb,jsonb),public.prepare_explain_connection_edit(jsonb),public.decide_explain_connection_edit(jsonb) from public,anon,authenticated;
grant execute on function public.prepare_explain_connection_edit(jsonb),public.decide_explain_connection_edit(jsonb) to service_role;
notify pgrst,'reload schema';
commit;
