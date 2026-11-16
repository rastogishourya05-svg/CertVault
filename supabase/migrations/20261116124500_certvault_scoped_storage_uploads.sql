begin;

-- The pipeline role may mint a short-lived authorization only after the API
-- has validated and scanned a PDF. Storage writes still use the owner's JWT,
-- so the worker never needs a project-wide Storage key.
create table private.storage_upload_tickets (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  object_path text not null,
  expires_at timestamptz not null default (now() + interval '3 minutes'),
  consumed_at timestamptz,
  created_at timestamptz not null default now(),
  unique(owner_id, object_path),
  check (split_part(object_path, '/', 1) = owner_id::text)
);
alter table private.storage_upload_tickets enable row level security;
alter table private.storage_upload_tickets force row level security;
revoke all on private.storage_upload_tickets from public, anon, authenticated;
create policy pipeline_owner on private.storage_upload_tickets
  to certvault_pipeline
  using (owner_id = nullif(current_setting('certvault.owner', true), '')::uuid)
  with check (owner_id = nullif(current_setting('certvault.owner', true), '')::uuid);
grant select, insert, update, delete on private.storage_upload_tickets to certvault_pipeline;
grant insert(issuer, recipient, issued_on, category) on public.certificates to certvault_pipeline;

-- This narrowly-scoped SECURITY DEFINER function consumes one exact ticket.
-- It accepts no owner argument: ownership comes from the verified Auth JWT.
create function private.consume_certificate_upload_ticket(object_name text)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  update private.storage_upload_tickets
     set consumed_at = pg_catalog.now()
   where owner_id = (select auth.uid())
     and object_path = object_name
     and expires_at > pg_catalog.now()
     and consumed_at is null;
  return found;
end
$$;
revoke all on function private.consume_certificate_upload_ticket(text) from public, anon;
grant execute on function private.consume_certificate_upload_ticket(text) to authenticated;

create policy private_certificate_scanned_upload on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'certificates'
    and (storage.foldername(name))[1] = (select auth.uid())::text
    and private.consume_certificate_upload_ticket(name)
  );

commit;
