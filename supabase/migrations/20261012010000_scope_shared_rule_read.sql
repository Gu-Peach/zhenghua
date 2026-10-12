-- Manual rule-library packages are shared; isolated Improvement candidates keep reviewer scope.
-- Rollback: ALTER POLICY profile_package_read ON public.profile_resource_packages
-- TO authenticated USING (true);
alter policy profile_package_read on public.profile_resource_packages
  to authenticated using (
    candidate_id is null
    or created_by = auth.uid()
    or approved_by = auth.uid()
  );
