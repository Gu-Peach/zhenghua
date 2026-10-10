-- PostgreSQL RESTRICT checks are immediate. Delete result/run dependents before
-- the project's workspace and document cascades so the project is removable as
-- one domain aggregate without weakening direct workspace/document protection.

create or replace function public.prepare_project_cascade_delete()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  delete from public.result_versions
  where project_id = old.id;

  delete from public.agent_runs
  where project_id = old.id;

  return old;
end;
$$;

drop trigger if exists projects_prepare_cascade_delete on public.projects;
create trigger projects_prepare_cascade_delete
before delete on public.projects
for each row execute function public.prepare_project_cascade_delete();

revoke all on function public.prepare_project_cascade_delete() from public;
grant execute on function public.prepare_project_cascade_delete() to service_role;
