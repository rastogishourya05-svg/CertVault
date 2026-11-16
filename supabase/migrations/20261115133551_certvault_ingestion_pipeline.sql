begin;
-- Only the backend role can access pipeline secrets; never granted to API clients.
do $$ declare existing_role pg_catalog.pg_roles%rowtype; begin
  select r.* into existing_role from pg_catalog.pg_roles r where r.rolname='certvault_pipeline';
  if not found then
    create role certvault_pipeline nologin noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls;
  elsif existing_role.rolcanlogin or existing_role.rolsuper or existing_role.rolcreatedb
    or existing_role.rolcreaterole or existing_role.rolreplication or existing_role.rolbypassrls
    or existing_role.rolinherit then
    raise exception 'certvault_pipeline exists with unsafe role attributes; refusing to grant pipeline access';
  end if;
end $$;
grant usage on schema public,private to certvault_pipeline;
create table private.mailbox_tokens (
  connection_id uuid primary key, owner_id uuid not null references auth.users(id) on delete cascade,
  ciphertext bytea not null, expires_at timestamptz not null,
  scan_days integer not null check(scan_days between 1 and 365),
  automatic boolean not null default false, next_poll_at timestamptz not null default now(),
  foreign key(connection_id,owner_id) references public.email_connections(id,owner_id) on delete cascade
);
create table private.pipeline_runs (
  job_id uuid primary key,owner_id uuid not null references auth.users(id) on delete cascade,
  lease_until timestamptz, page_token text, anchor text, mode text check(mode in ('backfill','history')),
  foreign key(job_id,owner_id) references public.sync_jobs(id,owner_id) on delete cascade
);
create table private.pipeline_items (
  id uuid primary key default gen_random_uuid(),owner_id uuid not null references auth.users(id) on delete cascade,
  connection_id uuid not null,message_id text not null,attachment_id text not null,filename text not null,
  declared_bytes bigint check(declared_bytes>=0),observed_bytes bigint,
  status text not null check(status in ('eligible','awaiting_approval','downloading','scanning','extracting','stored','duplicate','needs_review','rejected','failed')),
  approved boolean not null default false,certificate_id uuid,safe_error text,
  created_at timestamptz not null default now(),updated_at timestamptz not null default now(),
  unique(owner_id,connection_id,message_id,attachment_id),
  foreign key(connection_id,owner_id) references public.email_connections(id,owner_id),
  foreign key(certificate_id,owner_id) references public.certificates(id,owner_id)
);
create index pipeline_items_pending on private.pipeline_items(owner_id,connection_id,status);
create index pipeline_jobs_dispatch on public.sync_jobs(status,updated_at);
create index mailbox_poll_due on private.mailbox_tokens(next_poll_at) where automatic;
do $$ declare t text; begin
  foreach t in array array['mailbox_tokens','pipeline_runs','pipeline_items'] loop
    execute format('alter table private.%I enable row level security',t);
    execute format('alter table private.%I force row level security',t);
    execute format('revoke all on private.%I from public,anon,authenticated',t);
    execute format('create policy pipeline_owner on private.%I to certvault_pipeline using (owner_id=nullif(current_setting(''certvault.owner'',true),'''')::uuid) with check (owner_id=nullif(current_setting(''certvault.owner'',true),'''')::uuid)',t);
  end loop;
  foreach t in array array['mailbox_tokens'] loop
    execute format('grant select,insert,update,delete on private.%I to certvault_pipeline',t);
  end loop;
  foreach t in array array['pipeline_runs','pipeline_items'] loop
    execute format('grant select,insert,update on private.%I to certvault_pipeline',t);
  end loop;
  foreach t in array array['email_connections','sync_jobs'] loop
    execute format('create policy pipeline_owner on public.%I to certvault_pipeline using (owner_id=nullif(current_setting(''certvault.owner'',true),'''')::uuid) with check (owner_id=nullif(current_setting(''certvault.owner'',true),'''')::uuid)',t);
  end loop;
  foreach t in array array['profiles','certificates','certificate_files','notifications','audit_events'] loop
    execute format('create policy pipeline_owner on public.%I to certvault_pipeline using (owner_id=nullif(current_setting(''certvault.owner'',true),'''')::uuid) with check (owner_id=nullif(current_setting(''certvault.owner'',true),'''')::uuid)',t);
  end loop;
end $$;
-- Table/column grants mirror the worker's SQL operations; the login must SET ROLE first.
grant select(owner_id,download_limit_bytes) on public.profiles to certvault_pipeline;
grant select(id,owner_id,provider,account_label,cursor,state,created_at) on public.email_connections to certvault_pipeline;
grant insert(owner_id,provider,account_label,scopes,state,consent_at) on public.email_connections to certvault_pipeline;
grant update(state,consent_at,cursor) on public.email_connections to certvault_pipeline;
grant select(id,owner_id,connection_id,idempotency_key,status,attempts,safe_error_code,created_at,updated_at) on public.sync_jobs to certvault_pipeline;
grant insert(owner_id,connection_id,idempotency_key) on public.sync_jobs to certvault_pipeline;
grant update(status,attempts,safe_error_code,updated_at) on public.sync_jobs to certvault_pipeline;
grant select(id,owner_id,trashed_at) on public.certificates to certvault_pipeline;
grant insert(id,owner_id,title,source,extracted_text,provenance) on public.certificates to certvault_pipeline;
grant select(id,owner_id,certificate_id,object_path,sha256,bytes) on public.certificate_files to certvault_pipeline;
grant insert(owner_id,certificate_id,object_path,sha256,mime,bytes,scanned_at) on public.certificate_files to certvault_pipeline;
grant select(id,owner_id,event_key,kind,safe_message,read_at,created_at) on public.notifications to certvault_pipeline;
grant insert(owner_id,event_key,kind,safe_message) on public.notifications to certvault_pipeline;
grant insert(owner_id,action,resource_id) on public.audit_events to certvault_pipeline;
-- Scheduler alone can enumerate due IDs. No content/tokens returned. Explicit search_path.
create function private.pipeline_due() returns table(job_id uuid,owner_id uuid)
language plpgsql security definer set search_path='' as $$
#variable_conflict use_column
begin
  update public.sync_jobs j set status='failed',safe_error_code='retry_limit_exceeded',updated_at=now()
    from private.pipeline_runs r where r.job_id=j.id and j.status='running' and j.attempts>=5 and r.lease_until<now();
  insert into public.sync_jobs(owner_id,connection_id,idempotency_key)
    select m.owner_id,m.connection_id,'poll:'||m.connection_id::text||':'||floor(extract(epoch from now())/300)::text
    from private.mailbox_tokens m join public.email_connections c on c.id=m.connection_id
    where m.automatic and m.next_poll_at<=now() and c.state='connected'
    and not exists(select 1 from public.sync_jobs j where j.connection_id=m.connection_id and j.status in ('queued','running','retry'))
    on conflict(owner_id,idempotency_key) do nothing;
  return query select j.id,j.owner_id from public.sync_jobs j join private.mailbox_tokens m on m.connection_id=j.connection_id
    join public.email_connections c on c.id=j.connection_id left join private.pipeline_runs r on r.job_id=j.id
    where c.state='connected' and j.attempts<5 and
      (j.status='queued' or (j.status='retry' and j.updated_at+interval '30 seconds'*power(2,j.attempts)<=now()) or (j.status='running' and r.lease_until<now()))
    order by j.created_at limit 50;
end $$;
revoke all on function private.pipeline_due() from public,anon,authenticated;
grant execute on function private.pipeline_due() to certvault_pipeline;
commit;
