alter table public.certificates add column if not exists reviewed_at timestamptz;
grant update(trashed_at, reviewed_at) on public.certificates to authenticated;
