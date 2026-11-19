-- Historical runs keep NULL because their individual results cannot be reconstructed.
alter table private.pipeline_runs add column if not exists summary jsonb;
create table if not exists private.scan_items (
  owner_id uuid not null,
  job_id uuid not null,
  item_id uuid not null references private.pipeline_items(id) on delete cascade,
  already_stored boolean not null,
  primary key(job_id,item_id),
  foreign key(job_id,owner_id) references public.sync_jobs(id,owner_id) on delete cascade
);
alter table private.scan_items add column if not exists outcome text;
alter table private.scan_items enable row level security;
alter table private.scan_items force row level security;
revoke all on private.scan_items from public, anon, authenticated;
grant select,insert,update(outcome) on private.scan_items to certvault_pipeline;
drop policy if exists pipeline_owner on private.scan_items;
create policy pipeline_owner on private.scan_items to certvault_pipeline
using(owner_id=nullif(current_setting('certvault.owner',true),'')::uuid)
with check(owner_id=nullif(current_setting('certvault.owner',true),'')::uuid
  and exists(select 1 from private.pipeline_items i where i.id=item_id and i.owner_id=scan_items.owner_id));
