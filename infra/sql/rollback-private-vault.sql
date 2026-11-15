-- DEVELOPMENT ONLY. Destructive; never run automatically. Export data and obtain approval first.
begin;
drop policy if exists private_certificate_read on storage.objects;
drop table if exists private.oauth_tokens;
drop table if exists public.audit_events, public.social_drafts, public.featured_certificates,
public.public_profiles, public.share_links, public.notification_preferences,public.notifications,
public.collection_items,public.collections,public.certificate_tags,public.tags,public.certificate_files,
public.certificates,public.import_candidates,public.candidate_emails,public.sync_jobs,public.email_connections,public.profiles;
-- Storage bucket/objects intentionally retained to avoid silently deleting documents.
commit;
