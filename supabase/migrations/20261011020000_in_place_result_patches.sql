-- Local corrections keep stable IDs. Full extraction still uses commit_wiring_result.
-- Rollback: disable this RPC call path; preserve revision/receipt/audit data.
alter table public.result_versions add column revision integer not null default 1 check (revision > 0);
alter table public.result_proposals add column commit_receipt jsonb;

create or replace view public.wiring_connection_rows with (security_invoker = true) as
select connection.id as connection_id, project.id as project_id, project.name as project_name,
  workspace.id as workspace_id, workspace.name as workspace_name, drawing.id as drawing_id,
  drawing.workspace_page, drawing.pdf_page_number,
  result_version.id as result_version_id, result_version.version as result_version,
  result_version.status as result_status, unit.id as wiring_unit_id, unit.wire_number,
  connection.principle_number, unit.voltage_level, unit.terminal_strip,
  connection.start_code, connection.start_description, connection.start_terminal,
  connection.end_code, connection.end_description, connection.end_terminal,
  connection.current_value, connection.remark, connection.color_mark, connection.core_order,
  connection.confidence, connection.status, connection.needs_review,
  connection.record_version, connection.created_at, connection.updated_at,
  connection.is_cross_page, source_document.id as source_document_id,
  result_version.revision as result_revision
from public.wiring_connections connection
join public.wiring_units unit on unit.id = connection.wiring_unit_id
join public.result_versions result_version on result_version.id = unit.result_version_id
join public.projects project on project.id = unit.project_id
join public.workspaces workspace on workspace.id = unit.workspace_id
left join public.drawings drawing on drawing.id = coalesce(connection.source_drawing_id, unit.drawing_id)
left join lateral (
  select document.id from public.document_files document
  where document.project_id = project.id and document.kind = 'source_pdf'
  order by document.created_at desc limit 1
) source_document on true;
grant select on public.wiring_connection_rows to authenticated, service_role;

create function public.apply_confirmed_result_patch(value jsonb) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
declare
  proposal public.result_proposals;
  result public.result_versions;
  connection public.wiring_connections;
  unit public.wiring_units;
  actor uuid := (value->>'confirmed_by')::uuid;
  project uuid := (value->>'project_id')::uuid;
  change jsonb;
  approved jsonb;
  record jsonb;
  feedback jsonb;
  receipt jsonb;
  changed_ids jsonb := '[]'::jsonb;
  column_name text;
  changed_count integer;
begin
  if auth.role() is distinct from 'service_role' then
    raise sqlstate 'PT403' using message = 'Internal patch commit only';
  end if;
  perform 1 from public.projects where id = project for update;
  if not found then raise sqlstate 'PT409' using message = 'Project no longer exists'; end if;
  if not exists(select 1 from public.projects where id=project and owner_id=actor)
     and not exists(select 1 from public.project_members
                    where project_id=project and user_id=actor and role in ('owner','editor')) then
    raise sqlstate 'PT403' using message = 'Project correction permission denied';
  end if;
  select * into proposal from public.result_proposals
    where id=value->>'proposal_id' and project_id=project for update;
  if not found then raise sqlstate 'PT409' using message = 'Proposal scope mismatch'; end if;
  if proposal.committed_result_version_id is not null then
    if proposal.confirmed_by is distinct from actor then
      raise sqlstate 'PT403' using message = 'Proposal confirmed by another actor';
    end if;
    if proposal.commit_receipt is not null then return proposal.commit_receipt; end if;
    -- Legacy snapshot confirmations remain idempotent after deployment.
    select * into result from public.result_versions where id=proposal.committed_result_version_id;
    return jsonb_build_object('result_version_id',result.id,'result_version',result.version,
                             'result_revision',1,'update_mode','snapshot','updated_connection_ids','[]'::jsonb);
  end if;
  if (proposal.payload->'validation'->>'schema_valid')::boolean is distinct from true
     or (proposal.payload->'validation'->>'business_rules_valid')::boolean is distinct from true
     or not (proposal.payload ? 'feedback_id') then
    raise sqlstate 'PT409' using message = 'Unvalidated correction proposal';
  end if;
  select * into result from public.result_versions where project_id=project
    order by version desc limit 1 for update;
  if result.status not in ('draft','needs_review','accepted')
     or result.version <> (proposal.payload->>'base_result_version')::integer
     or result.revision is distinct from (proposal.payload->>'base_result_revision')::integer
     or result.profile is distinct from proposal.payload->'profile' then
    raise sqlstate 'PT409' using message = 'Result generation, revision or Profile changed';
  end if;
  if jsonb_typeof(value->'changes') <> 'array' or jsonb_array_length(value->'changes')=0
     or jsonb_array_length(value->'changes') <> jsonb_array_length(proposal.payload->'operations') then
    raise sqlstate 'PT409' using message = 'Correction operation set mismatch';
  end if;
  for change in select item from jsonb_array_elements(value->'changes') item
  loop
    if changed_ids @> jsonb_build_array(change->>'target_id') then
      raise sqlstate 'PT409' using message = 'Duplicate correction target';
    end if;
    select item into approved from jsonb_array_elements(proposal.payload->'operations') item
      where item->>'target_id'=change->>'target_id';
    if not found or approved->>'op' <> 'replace' or approved->>'target_type' <> 'CONNECTION'
       or approved->'after' is distinct from change->'after'
       or approved->'before' is distinct from change->'before'
       or approved->'expected_version' is distinct from change->'expected_version' then
      raise sqlstate 'PT409' using message = 'Unapproved correction operation';
    end if;
    select c.* into connection from public.wiring_connections c
      join public.wiring_units u on u.id=c.wiring_unit_id
      where c.id=(change->>'target_id')::uuid and u.project_id=project and u.result_version_id=result.id
      for update of c;
    if not found or connection.record_version is distinct from (change->>'expected_version')::integer then
      raise sqlstate 'PT409' using message = 'Connection changed or is outside current result';
    end if;
    select * into unit from public.wiring_units where id=connection.wiring_unit_id for update;
    foreach column_name in array array['principle_number','start_code','start_description','start_terminal',
      'end_code','end_description','end_terminal','current_value','remark','color_mark','is_cross_page'] loop
      if change->'before' ? column_name and
         to_jsonb(connection)->column_name is distinct from change->'before'->column_name then
        raise sqlstate 'PT409' using message = 'Connection before value changed';
      end if;
    end loop;
    record := change->'record';
    update public.wiring_connections set
      principle_number=record->>'principle_number', start_code=record->>'start_code',
      start_description=record->>'start_description', start_terminal=record->>'start_terminal',
      end_code=record->>'end_code', end_description=record->>'end_description',
      end_terminal=record->>'end_terminal', current_value=record->>'current_value',
      remark=record->>'remark', color_mark=record->>'color_mark',
      is_cross_page=record->>'is_cross_page', confidence=(record->>'confidence')::numeric,
      raw_payload=approved->'after', record_version=record_version+1,
      status='confirmed', needs_review=false where id=connection.id;
    foreach column_name in array array['voltage_level','terminal_strip'] loop
      if change->'after' ? column_name and change->'after'->column_name
         is distinct from change->'before'->column_name then
        if to_jsonb(unit)->column_name is distinct from change->'before'->column_name then
          raise sqlstate 'PT409' using message = 'Terminal strip metadata changed';
        end if;
        update public.wiring_units set
          voltage_level=case when column_name='voltage_level' then change->'after'->>column_name
                             else voltage_level end,
          terminal_strip=case when column_name='terminal_strip' then change->'after'->>column_name
                              else terminal_strip end where id=unit.id;
      end if;
    end loop;
    changed_ids := changed_ids || jsonb_build_array(connection.id::text);
  end loop;
  update public.result_versions set status='superseded'
    where project_id=project and status='accepted' and id<>result.id;
  update public.result_versions set revision=revision+1,status='accepted',confirmed_by=actor
    where id=result.id returning * into result;
  for feedback in select item from jsonb_array_elements(value->'feedback_updates') item loop
    if not exists(select 1 from jsonb_array_elements_text(
      case when jsonb_array_length(coalesce(proposal.payload->'feedback_ids','[]'::jsonb))>0
           then proposal.payload->'feedback_ids' else jsonb_build_array(proposal.payload->>'feedback_id') end
    ) key where key=feedback->>'feedback_id') then
      raise sqlstate 'PT409' using message = 'Feedback is outside the approved proposal';
    end if;
    update public.feedback_items set status='accepted', proposal_id=proposal.id,
      committed_result_version_id=result.id, before_value=feedback->'before', after_value=feedback->'after',
      accepted_at=now(), accepted_payload=jsonb_set(
        jsonb_set(feedback->'accepted_payload','{result_version_id}',to_jsonb(result.id::text)),
        '{context}', coalesce(feedback->'accepted_payload'->'context','{}'::jsonb) ||
          jsonb_build_object('result_revision',result.revision,'update_mode','in_place'))
      where id=feedback->>'feedback_id' and project_id=project and status='prepared';
    get diagnostics changed_count = row_count;
    if changed_count <> 1 then raise sqlstate 'PT409' using message = 'Feedback scope/status changed'; end if;
  end loop;
  if jsonb_array_length(value->'feedback_updates')=0 then
    raise sqlstate 'PT409' using message = 'Correction audit is required';
  end if;
  receipt := jsonb_build_object('result_version_id',result.id,'result_version',result.version,
    'result_revision',result.revision,'update_mode','in_place','updated_connection_ids',changed_ids);
  update public.result_proposals set committed_result_version_id=result.id,committed_at=now(),
    confirmed_by=actor,commit_receipt=receipt where id=proposal.id;
  return receipt;
end;
$$;
revoke all on function public.apply_confirmed_result_patch(jsonb) from public,anon,authenticated;
grant execute on function public.apply_confirmed_result_patch(jsonb) to service_role;
