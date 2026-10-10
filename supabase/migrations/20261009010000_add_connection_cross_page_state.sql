-- Stage 2 stores one explicit three-state routing value on each connection.
-- Detailed references remain in evidence and stage artifacts; no new relation is introduced.

alter table public.wiring_connections
  add column if not exists is_cross_page text not null default 'unknown'
  check (is_cross_page in ('same_page', 'cross_page', 'unknown'));

create index if not exists wiring_connections_cross_page_idx
  on public.wiring_connections (is_cross_page, wiring_unit_id);

comment on column public.wiring_connections.is_cross_page is
  'Stage 2 routing state: same_page, cross_page, or unknown.';

create or replace view public.wiring_connection_rows
with (security_invoker = true)
as
select
  connection.id as connection_id,
  project.id as project_id,
  project.name as project_name,
  workspace.id as workspace_id,
  workspace.name as workspace_name,
  drawing.id as drawing_id,
  drawing.workspace_page,
  drawing.pdf_page_number,
  result_version.id as result_version_id,
  result_version.version as result_version,
  unit.id as wiring_unit_id,
  unit.wire_number,
  connection.principle_number,
  unit.voltage_level,
  unit.terminal_strip,
  connection.start_code,
  connection.start_description,
  connection.start_terminal,
  connection.end_code,
  connection.end_description,
  connection.end_terminal,
  connection.current_value,
  connection.remark,
  connection.color_mark,
  connection.core_order,
  connection.confidence,
  connection.status,
  connection.needs_review,
  connection.created_at,
  connection.updated_at,
  connection.is_cross_page
from public.wiring_connections as connection
join public.wiring_units as unit
  on unit.id = connection.wiring_unit_id
join public.result_versions as result_version
  on result_version.id = unit.result_version_id
join public.projects as project
  on project.id = unit.project_id
join public.workspaces as workspace
  on workspace.id = unit.workspace_id
left join public.drawings as drawing
  on drawing.id = coalesce(connection.source_drawing_id, unit.drawing_id);

grant select on public.wiring_connection_rows to authenticated;
grant select on public.wiring_connection_rows to service_role;
