begin;
-- Tokens remain inaccessible to client roles even if a future grant is accidentally widened.
create policy deny_client_tokens on private.oauth_tokens for all to anon,authenticated
using (false) with check (false);
create index collections_owner on public.collections(owner_id);
create index notifications_owner_created on public.notifications(owner_id,created_at desc);
create index shares_owner_expiry on public.share_links(owner_id,expires_at);
create index drafts_owner_created on public.social_drafts(owner_id,created_at desc);
create index audit_owner_created on public.audit_events(owner_id,created_at desc);
create index token_connection_owner on private.oauth_tokens(connection_id,owner_id);
create index token_owner on private.oauth_tokens(owner_id);
create index file_certificate_owner on public.certificate_files(certificate_id,owner_id);
create index import_email_owner on public.import_candidates(email_id,owner_id);
create index tag_memberships_tag_owner on public.certificate_tags(tag_id,owner_id);
create index collection_memberships_certificate_owner on public.collection_items(certificate_id,owner_id);
create index featured_certificate_owner on public.featured_certificates(certificate_id,owner_id);
create index shares_certificate_owner on public.share_links(certificate_id,owner_id);
create index drafts_certificate_owner on public.social_drafts(certificate_id,owner_id);
commit;
