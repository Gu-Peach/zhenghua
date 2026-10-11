-- SET NULL on a parent being deleted from its BEFORE DELETE cleanup modifies
-- that same tuple. Defer NO ACTION instead; the parent is absent at COMMIT.
alter table public.projects drop constraint project_classification_snapshot_fk;
alter table public.projects add constraint project_classification_snapshot_fk
  foreign key(published_classification_snapshot_id) references public.agent_artifacts(artifact_id)
  on delete no action deferrable initially deferred;
notify pgrst,'reload schema';
