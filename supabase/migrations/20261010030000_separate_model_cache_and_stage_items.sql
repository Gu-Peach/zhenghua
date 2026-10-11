-- Model-call cache and finalized page projection are different immutable items.
drop index public.agent_stage_canonical_idx;
create unique index agent_stage_canonical_idx
  on public.agent_artifacts(agent_run_id,stage,kind,item_id)
  where kind in ('gate_a_item','gate_a_model','gate_a_manifest');
notify pgrst,'reload schema';
