-- Initial production schema. Apply only to an explicitly authorized Supabase environment.
begin;
create table public.profiles (
  owner_id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null default '',
  download_limit_bytes bigint not null default 52428800 check (download_limit_bytes between 1048576 and 104857600),
  ai_content_consent boolean not null default false,
  created_at timestamptz not null default now()
);
create table public.email_connections (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id) on delete cascade,
  provider text not null check(provider in ('gmail','outlook')), account_label text not null,
  token_reference uuid, scopes text[] not null default '{}', cursor text,
  state text not null default 'disconnected' check(state in ('connected','disconnected','error')),
  consent_at timestamptz, created_at timestamptz not null default now(), unique(id,owner_id), unique(owner_id,provider,account_label)
);
-- OAuth secrets are outside the Data API schema. Store authenticated ciphertext, never plaintext.
create schema if not exists private;
revoke all on schema private from public, anon, authenticated;
create table private.oauth_tokens (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id) on delete cascade,
  connection_id uuid not null, ciphertext bytea not null, key_version integer not null,
  foreign key(connection_id,owner_id) references public.email_connections(id,owner_id) on delete cascade
);
alter table private.oauth_tokens enable row level security;
revoke all on private.oauth_tokens from public,anon,authenticated;
create table public.sync_jobs (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id) on delete cascade,
  connection_id uuid not null, idempotency_key text not null,
  status text not null default 'queued' check(status in ('queued','running','retry','completed','failed','cancelled')),
  attempts integer not null default 0 check(attempts>=0), safe_error_code text,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  unique(id,owner_id), unique(owner_id,idempotency_key),
  foreign key(connection_id,owner_id) references public.email_connections(id,owner_id)
);
create table public.candidate_emails (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id) on delete cascade,
  connection_id uuid not null, provider_message_id text not null, subject_hint text not null default '',
  expires_at timestamptz not null default (now()+interval '7 days'), unique(id,owner_id),
  unique(owner_id,connection_id,provider_message_id),
  foreign key(connection_id,owner_id) references public.email_connections(id,owner_id)
);
create table public.import_candidates (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id) on delete cascade,
  email_id uuid, source_key text not null, declared_bytes bigint check(declared_bytes>=0), observed_bytes bigint check(observed_bytes>=0),
  status text not null default 'discovered' check(status in ('discovered','classified','awaiting_approval','eligible','needs_review','downloading','quarantined','scanning','extracting','stored','notified','retry','failed','rejected','duplicate')),
  approved_at timestamptz, approved_by uuid, approval_limit_bytes bigint check(approval_limit_bytes<=104857600),
  check(approved_by is null or approved_by=owner_id),
  created_at timestamptz not null default now(), unique(id,owner_id), unique(owner_id,source_key),
  foreign key(email_id,owner_id) references public.candidate_emails(id,owner_id)
);
create table public.certificates (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id) on delete cascade,
  title text not null check(length(title) between 1 and 160), issuer text,
  recipient text, issued_on date, expires_on date, credential_id text, verification_url text,
  category text not null default 'Other', source text not null, favorite boolean not null default false,
  confidence numeric check(confidence between 0 and 1), provenance jsonb not null default '{}',
  extracted_text text not null default '', trashed_at timestamptz, created_at timestamptz not null default now(),
  search_document tsvector generated always as (to_tsvector('simple',coalesce(title,'')||' '||coalesce(issuer,'')||' '||coalesce(extracted_text,''))) stored,
  unique(id,owner_id)
);
create index certificates_owner_created on public.certificates(owner_id,created_at desc);
create index certificates_search on public.certificates using gin(search_document);
create table public.certificate_files (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id) on delete cascade,
  certificate_id uuid not null, object_path text not null unique,
  sha256 text not null check(sha256 ~ '^[a-f0-9]{64}$'), mime text not null check(mime in ('application/pdf','image/png','image/jpeg')),
  bytes bigint not null check(bytes between 1 and 104857600), scanned_at timestamptz not null,
  unique(owner_id,sha256), foreign key(certificate_id,owner_id) references public.certificates(id,owner_id) on delete cascade,
  check(split_part(object_path,'/',1)=owner_id::text)
);
create table public.tags (
  id uuid primary key default gen_random_uuid(),owner_id uuid not null references auth.users(id) on delete cascade,
  name text not null,unique(id,owner_id),unique(owner_id,name)
);
create table public.certificate_tags (
  owner_id uuid not null references auth.users(id) on delete cascade,certificate_id uuid not null,tag_id uuid not null,
  primary key(owner_id,certificate_id,tag_id),
  foreign key(certificate_id,owner_id) references public.certificates(id,owner_id) on delete cascade,
  foreign key(tag_id,owner_id) references public.tags(id,owner_id) on delete cascade
);
create table public.collections (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id) on delete cascade,
  name text not null check(length(name) between 1 and 100),unique(id,owner_id)
);
create table public.collection_items (
  owner_id uuid not null references auth.users(id) on delete cascade, collection_id uuid not null, certificate_id uuid not null,
  primary key(owner_id,collection_id,certificate_id),
  foreign key(collection_id,owner_id) references public.collections(id,owner_id) on delete cascade,
  foreign key(certificate_id,owner_id) references public.certificates(id,owner_id) on delete cascade
);
create table public.notifications (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id) on delete cascade,
  event_key text not null, kind text not null, safe_message text not null, read_at timestamptz,
  created_at timestamptz not null default now(),unique(owner_id,event_key)
);
create table public.notification_preferences (
  owner_id uuid primary key references auth.users(id) on delete cascade,
  in_app boolean not null default true,email_digest boolean not null default false,expiry_reminders boolean not null default true
);
create table public.share_links (
  id uuid primary key default gen_random_uuid(),owner_id uuid not null references auth.users(id) on delete cascade,
  certificate_id uuid not null,token_hash text not null unique check(length(token_hash)=64),
  expires_at timestamptz not null, revoked_at timestamptz,created_at timestamptz not null default now(),
  foreign key(certificate_id,owner_id) references public.certificates(id,owner_id) on delete cascade,
  check(expires_at>created_at)
);
create table public.public_profiles (
  owner_id uuid primary key references auth.users(id) on delete cascade,
  slug text not null unique check(slug ~ '^[a-z0-9-]{3,40}$'),display_name text not null,
  enabled boolean not null default false,consented_at timestamptz
);
create table public.featured_certificates (
  owner_id uuid not null references public.public_profiles(owner_id) on delete cascade,certificate_id uuid not null,
  primary key(owner_id,certificate_id),
  foreign key(certificate_id,owner_id) references public.certificates(id,owner_id) on delete cascade
);
create table public.social_drafts (
  id uuid primary key default gen_random_uuid(),owner_id uuid not null references auth.users(id) on delete cascade,
  certificate_id uuid not null,content text not null check(length(content)<=3000),tone text not null,
  generator text not null check(generator in ('template','ai')), created_at timestamptz not null default now(),
  foreign key(certificate_id,owner_id) references public.certificates(id,owner_id) on delete cascade
);
create table public.audit_events (
  id uuid primary key default gen_random_uuid(),owner_id uuid not null references auth.users(id) on delete cascade,
  action text not null,resource_id uuid,safe_error_code text,created_at timestamptz not null default now()
);
-- Ownership is defense in depth. Pipeline writes remain backend-only through column/table grants.
do $$ declare t text; begin
  foreach t in array array['profiles','email_connections','sync_jobs','candidate_emails','import_candidates','certificates','certificate_files','tags','certificate_tags','collections','collection_items','notifications','notification_preferences','share_links','public_profiles','featured_certificates','social_drafts','audit_events'] loop
    execute format('alter table public.%I enable row level security',t);
    execute format('create policy owner_access on public.%I for all to authenticated using ((select auth.uid())=owner_id) with check ((select auth.uid())=owner_id)',t);
    execute format('revoke all on public.%I from anon,authenticated',t);
    execute format('grant select on public.%I to authenticated',t);
  end loop;
end $$;
grant update(display_name,download_limit_bytes,ai_content_consent) on public.profiles to authenticated;
grant update(title,issuer,recipient,issued_on,expires_on,credential_id,verification_url,category,favorite) on public.certificates to authenticated;
grant update(read_at) on public.notifications to authenticated;
grant insert,update,delete on public.tags,public.certificate_tags,public.collections,public.collection_items to authenticated;
grant insert,update on public.notification_preferences to authenticated;
-- Publishing/profile mutations and shares pass through API consent checks, no direct Data API writes.
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values ('certificates','certificates',false,104857600,array['application/pdf','image/png','image/jpeg']);
create policy private_certificate_read on storage.objects for select to authenticated
using (bucket_id='certificates' and (storage.foldername(name))[1]=(select auth.uid())::text);
-- No client uploads: validated, scanned ingestion is performed server-side only.
commit;
