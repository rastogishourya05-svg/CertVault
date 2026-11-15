begin;
-- Authenticated users can initialize only their own preferences; ownership stays immutable.
grant insert(owner_id,display_name,download_limit_bytes) on public.profiles to authenticated;
commit;
