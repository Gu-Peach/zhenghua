-- Correction bundles contain internal image paths, prompts and raw evidence.
-- They are available only through the authenticated business/Agent API.

drop policy if exists feedback_items_member_read on public.feedback_items;
revoke select on public.feedback_items from authenticated;
