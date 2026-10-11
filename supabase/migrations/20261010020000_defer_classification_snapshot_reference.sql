-- Classification publication and its manifest are inserted in one transaction.
-- Validate the project pointer at COMMIT, rather than before manifest INSERT.
alter table public.projects alter constraint project_classification_snapshot_fk
  deferrable initially deferred;
notify pgrst,'reload schema';
