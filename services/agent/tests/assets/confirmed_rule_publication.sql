-- Synthetic rows only. Executed in disposable migration databases and rolled back.
begin;
set local request.jwt.claim.role = 'service_role';
insert into auth.users(id) values('00000000-0000-4000-8000-000000000001'),
  ('00000000-0000-4000-8000-000000000009');
insert into public.projects(id,owner_id,name) values(
  '00000000-0000-4000-8000-000000000002','00000000-0000-4000-8000-000000000001','synthetic rules');
insert into public.document_files(id,project_id,original_filename,storage_path,checksum,mime_type,size_bytes)
values('00000000-0000-4000-8000-000000000003','00000000-0000-4000-8000-000000000002',
  'synthetic.pdf','synthetic.pdf','synthetic','application/pdf',1);
insert into public.agent_runs(id,idempotency_key,request_fingerprint,run_type,status,project_id,
  source_document_id,requested_by,scope)
values('00000000-0000-4000-8000-000000000004','rule-test','synthetic','SCOPED_CORRECTION','NEEDS_REVIEW',
  '00000000-0000-4000-8000-000000000002','00000000-0000-4000-8000-000000000003',
  '00000000-0000-4000-8000-000000000001','{}');
insert into public.feedback_items(id,project_id,target_type,target_id,issue_kind,status,
  base_result_version,correction_bundle,accepted_payload)
values('rule-test-feedback','00000000-0000-4000-8000-000000000002','CONNECTION','synthetic','DIRECT_VALUE_CHANGE',
  'accepted',1,'{}',jsonb_build_object('correction_run_id','00000000-0000-4000-8000-000000000004',
  'profile',jsonb_build_object('key','synthetic-rule','version','1.0.0','checksum','sha256:'||repeat('a',64))));
insert into public.profile_candidates(id,profile_key,profile_version,status,payload)
select 'synthetic-rule-candidate','synthetic-rule','1.0.0','DRAFT',jsonb_build_object(
  'candidate_id','synthetic-rule-candidate','status','DRAFT','profile',accepted_payload->'profile',
  'source_feedback_ids',jsonb_build_array(id),'resource_package_id','00000000-0000-4000-8000-000000000006',
  'resource_package_checksum','sha256:'||repeat('c',64),'checksum','sha256:'||repeat('b',64))
from public.feedback_items where id='rule-test-feedback';
insert into public.profile_resource_packages(id,profile_key,profile_version,source_profile_checksum,
  package_checksum,manifest_checksum,storage_prefix,manifest_path,status,created_by,created_at)
values('00000000-0000-4000-8000-000000000005','synthetic-rule','1.0.0','sha256:'||repeat('a',64),
  'sha256:'||repeat('a',64),'sha256:'||repeat('a',64),'synthetic/base','synthetic/base/manifest.json','active',
  '00000000-0000-4000-8000-000000000001',now()-interval '1 day');
insert into public.profile_resource_packages(id,profile_key,profile_version,source_profile_checksum,
  package_checksum,manifest_checksum,storage_prefix,manifest_path,status,created_by,base_package_id,candidate_id)
values('00000000-0000-4000-8000-000000000006','synthetic-rule','1.0.0-candidate.test','sha256:'||repeat('b',64),
  'sha256:'||repeat('c',64),'sha256:'||repeat('c',64),'synthetic/new','synthetic/new/manifest.json','candidate',
  '00000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000005','synthetic-rule-candidate');
do $$
declare receipt jsonb; rejected boolean;
begin
  rejected := false;
  begin
    perform public.confirm_and_publish_profile_candidate('synthetic-rule-candidate',
      '00000000-0000-4000-8000-000000000001',false);
  exception when others then rejected := true; end;
  if not rejected then raise exception 'Missing confirmation accepted'; end if;
  rejected := false;
  begin
    perform public.confirm_and_publish_profile_candidate('synthetic-rule-candidate',
      '00000000-0000-4000-8000-000000000009',true);
  exception when others then rejected := true; end;
  if not rejected then raise exception 'Wrong owner accepted'; end if;
  perform set_config('request.jwt.claim.role','authenticated',true);
  rejected := false;
  begin
    perform public.confirm_and_publish_profile_candidate('synthetic-rule-candidate',
      '00000000-0000-4000-8000-000000000001',true);
  exception when others then rejected := true; end;
  if not rejected then raise exception 'Non-service caller accepted'; end if;
  perform set_config('request.jwt.claim.role','service_role',true);
  update public.profile_resource_packages set status='retired'
    where id='00000000-0000-4000-8000-000000000005';
  rejected := false;
  begin
    perform public.confirm_and_publish_profile_candidate('synthetic-rule-candidate',
      '00000000-0000-4000-8000-000000000001',true);
  exception when others then rejected := true; end;
  if not rejected then raise exception 'Changed active baseline accepted'; end if;
  update public.profile_resource_packages set status='active'
    where id='00000000-0000-4000-8000-000000000005';
end $$;
create function public.synthetic_rule_audit_failure() returns trigger language plpgsql as $$
begin raise exception 'synthetic rule audit failure'; end $$;
create trigger synthetic_rule_audit_failure before insert on public.profile_candidate_audit
for each row execute function public.synthetic_rule_audit_failure();
do $$
begin
  begin
    perform public.confirm_and_publish_profile_candidate('synthetic-rule-candidate',
      '00000000-0000-4000-8000-000000000001',true);
    raise exception 'Audit failure was ignored';
  exception when others then
    if sqlerrm <> 'synthetic rule audit failure' then raise; end if;
  end;
  if (select status from public.profile_candidates where id='synthetic-rule-candidate') <> 'DRAFT'
    or (select status from public.profile_resource_packages
      where id='00000000-0000-4000-8000-000000000006') <> 'candidate' then
    raise exception 'Audit failure left partially published rules';
  end if;
end $$;
drop trigger synthetic_rule_audit_failure on public.profile_candidate_audit;
do $$
declare receipt jsonb;
begin
  receipt := public.confirm_and_publish_profile_candidate('synthetic-rule-candidate',
    '00000000-0000-4000-8000-000000000001',true);
  if receipt->>'status' <> 'ACTIVE' then raise exception 'Candidate not active'; end if;
  if (select gate_passed from public.profile_candidates where id='synthetic-rule-candidate') then
    raise exception 'Fabricated evaluation gate'; end if;
  if public.confirm_and_publish_profile_candidate('synthetic-rule-candidate',
    '00000000-0000-4000-8000-000000000001',true) <> receipt then raise exception 'Replay changed'; end if;
  if (select count(*) from public.profile_candidate_audit where candidate_id='synthetic-rule-candidate'
    and action='confirmed_publish') <> 1 then raise exception 'Duplicate audit'; end if;
  if (select status from public.profile_resource_packages
    where id='00000000-0000-4000-8000-000000000006') <> 'active' then raise exception 'Package inactive'; end if;
  if not exists(select 1 from public.profile_resource_packages
    where id='00000000-0000-4000-8000-000000000005' and status='active') then
    raise exception 'Historical package changed'; end if;
end $$;
rollback;
