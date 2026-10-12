-- ADR-0013: explicit human confirmation, not model evaluation, enables a rule version.
-- Rollback: revoke/drop this new RPC and deploy the previous gated application.
-- Published versions/audits are immutable history and must not be deleted on rollback.
create or replace function public.confirm_and_publish_profile_candidate(
  candidate_key text, reviewer uuid, confirmed_value boolean
) returns jsonb language plpgsql security definer set search_path = public as $$
declare
  c public.profile_candidates%rowtype;
  p public.profile_resource_packages%rowtype;
  base public.profile_resource_packages%rowtype;
  latest uuid;
  previous text;
  feedback_key text;
begin
  if auth.role() is distinct from 'service_role' then raise exception 'Internal publisher only'; end if;
  if confirmed_value is distinct from true or reviewer is null then
    raise exception 'Explicit human confirmation required';
  end if;
  select * into c from public.profile_candidates where id = candidate_key;
  if not found then raise exception 'Candidate not found'; end if;
  perform pg_advisory_xact_lock(hashtext('profile-key:' || c.profile_key));
  select * into c from public.profile_candidates where id = candidate_key for update;
  if jsonb_array_length(coalesce(c.payload->'source_feedback_ids', '[]'::jsonb)) = 0 then
    raise exception 'Missing accepted feedback provenance';
  end if;
  for feedback_key in select jsonb_array_elements_text(c.payload->'source_feedback_ids') loop
    if not exists (
      select 1 from public.feedback_items f join public.agent_runs r
        on r.id::text = f.accepted_payload->>'correction_run_id'
      where f.id::text = feedback_key and f.status = 'accepted'
        and r.requested_by::text = reviewer::text
        and r.project_id = f.project_id
        and (exists(select 1 from public.projects where id=f.project_id and owner_id=reviewer)
          or exists(select 1 from public.project_members
            where project_id=f.project_id and user_id=reviewer and role in ('owner','editor')))
        and f.accepted_payload->'profile' = c.payload->'profile'
    ) then raise exception 'Feedback owner or frozen Profile mismatch'; end if;
  end loop;
  select * into p from public.profile_resource_packages
    where id::text = c.payload->>'resource_package_id' for update;
  if not found or p.candidate_id is distinct from c.id
    or p.profile_key is distinct from c.profile_key
    or p.package_checksum is distinct from c.payload->>'resource_package_checksum'
    or p.source_profile_checksum is distinct from c.payload->>'checksum' then
    raise exception 'Candidate package identity/checksum mismatch';
  end if;
  if c.status = 'ACTIVE' then
    if p.status <> 'active' or not exists (
      select 1 from public.profile_candidate_audit
      where candidate_id = c.id and action = 'confirmed_publish' and reviewer_id = reviewer::text
    ) then raise exception 'Publication receipt mismatch'; end if;
    return c.payload;
  end if;
  if c.status not in ('DRAFT','EVALUATING','REJECTED','APPROVED','CANARY') or p.status <> 'candidate' then
    raise exception 'Candidate is not publishable';
  end if;
  select * into base from public.profile_resource_packages where id = p.base_package_id;
  if not found or base.profile_key is distinct from c.profile_key
    or base.profile_version is distinct from c.payload->'profile'->>'version'
    or base.source_profile_checksum is distinct from c.payload->'profile'->>'checksum' then
    raise exception 'Baseline package mismatch';
  end if;
  select id into latest from public.profile_resource_packages
    where profile_key = c.profile_key and status = 'active' order by created_at desc, id desc limit 1;
  if latest is distinct from base.id then raise exception 'Active rules changed; regenerate suggestion'; end if;
  select id into previous from public.profile_candidates
    where profile_key = c.profile_key and status = 'ACTIVE' and id <> c.id for update;
  if previous is not null then
    update public.profile_candidates set status = 'RETIRED',
      payload = jsonb_set(payload, '{status}', '"RETIRED"') where id = previous;
    insert into public.profile_candidate_audit(candidate_id, action, from_status, to_status, reviewer_id)
      values(previous, 'superseded', 'ACTIVE', 'RETIRED', reviewer::text);
  end if;
  update public.profile_resource_packages
    set status = 'active', approved_by = reviewer, published_at = coalesce(published_at, now()) where id = p.id;
  update public.profile_candidates set status = 'ACTIVE',
    payload = jsonb_set(payload, '{status}', '"ACTIVE"'), previous_active_candidate_id = previous
    where id = c.id returning payload into c.payload;
  insert into public.profile_candidate_reviews(candidate_id, reviewer_id, action)
    values(c.id, reviewer::text, 'confirmed_publish');
  insert into public.profile_candidate_audit(candidate_id, action, from_status, to_status, reviewer_id, payload)
    values(c.id, 'confirmed_publish', c.status, 'ACTIVE', reviewer::text,
      jsonb_build_object('evaluation_required', false, 'package_id', p.id,
        'before_checksum', base.package_checksum, 'after_checksum', p.package_checksum));
  return c.payload;
end;
$$;
revoke all on function public.confirm_and_publish_profile_candidate(text, uuid, boolean) from public;
grant execute on function public.confirm_and_publish_profile_candidate(text, uuid, boolean) to service_role;
