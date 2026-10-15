-- Run in the migration transaction. All probe rows are rolled back to this savepoint.
-- Uses two existing Auth identities without modifying or printing their data.
savepoint simple_schema_probe;
create temporary table simple_schema_probe_users on commit drop as
select id, row_number() over (order by id) as ordinal from auth.users order by id limit 2;
do $$ begin
  if (select count(*) from simple_schema_probe_users) <> 2 then
    raise exception 'Two existing Auth identities are required for the RLS probe';
  end if;
end $$;

insert into public.extraction_profiles(id,profile_key,profile_version,checksum,resource_ref,display_name,created_by)
values ('ffe00000-0000-0000-0000-000000000001','schema_probe','0.0.0',
  'sha256:0000000000000000000000000000000000000000000000000000000000000000',
  'temporary/schema_probe','Temporary probe',(select id from simple_schema_probe_users where ordinal=1));
insert into public.extraction_projects(id,owner_id,name,profile_id)
select case ordinal when 1 then 'ffe00000-0000-0000-0000-000000000011'::uuid
  else 'ffe00000-0000-0000-0000-000000000012'::uuid end,
  id,'Temporary probe','ffe00000-0000-0000-0000-000000000001'
from simple_schema_probe_users;
insert into public.extraction_connection_rows(id,project_id,batch_id,page_item_id,row_order,source_pdf_page_number)
values
  ('ffe00000-0000-0000-0000-000000000021','ffe00000-0000-0000-0000-000000000011','probe','one',0,1),
  ('ffe00000-0000-0000-0000-000000000022','ffe00000-0000-0000-0000-000000000012','probe','one',0,1);

do $$ begin
  perform set_config('request.jwt.claim.sub', (select id::text from simple_schema_probe_users where ordinal=1),true);
end $$;
set local role authenticated;
do $$ begin
  if (select count(*) from public.extraction_projects) <> 1
     or (select count(*) from public.extraction_connection_rows) <> 1 then
    raise exception 'Owner RLS visibility failed';
  end if;
  update public.extraction_connection_rows set remark='probe update'
    where id='ffe00000-0000-0000-0000-000000000021';
  if (select record_version from public.extraction_connection_rows
      where id='ffe00000-0000-0000-0000-000000000021') <> 2 then
    raise exception 'Record version trigger failed';
  end if;
  begin
    insert into public.extraction_connection_rows(project_id,batch_id,page_item_id,row_order,source_pdf_page_number)
    values ('ffe00000-0000-0000-0000-000000000012','probe','unauthorized',1,1);
    raise exception 'Cross-owner insertion unexpectedly succeeded';
  exception when insufficient_privilege then null;
  end;
  begin
    insert into public.extraction_connection_rows(project_id,batch_id,page_item_id,row_order,source_pdf_page_number)
    values ('ffe00000-0000-0000-0000-000000000011','probe','one',1,1);
    raise exception 'Duplicate page item unexpectedly succeeded';
  exception when unique_violation then null;
  end;
end $$;
reset role;
do $$ begin
  perform set_config('request.jwt.claim.sub', (select id::text from simple_schema_probe_users where ordinal=2),true);
end $$;
set local role authenticated;
do $$ begin
  if exists(select 1 from public.extraction_projects
      where id='ffe00000-0000-0000-0000-000000000011')
     or exists(select 1 from public.extraction_connection_rows
      where project_id='ffe00000-0000-0000-0000-000000000011') then
    raise exception 'Other-owner isolation failed';
  end if;
end $$;
reset role;
set local role anon;
do $$ begin
  begin
    perform 1 from public.extraction_connection_rows;
    raise exception 'Anonymous access unexpectedly succeeded';
  exception when insufficient_privilege then null;
  end;
end $$;
reset role;
rollback to savepoint simple_schema_probe;
release savepoint simple_schema_probe;
select 'owner/other-owner/anonymous RLS, row-version trigger and page-item uniqueness passed' as validation;
