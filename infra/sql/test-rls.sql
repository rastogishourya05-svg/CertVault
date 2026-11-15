\set ON_ERROR_STOP on
begin;
insert into auth.users(id) values ('11111111-1111-4111-8111-111111111111'),('22222222-2222-4222-8222-222222222222');
insert into public.profiles(owner_id) select id from auth.users;
insert into public.certificates(id,owner_id,title,source) values
('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','11111111-1111-4111-8111-111111111111','User A certificate','test'),
('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','22222222-2222-4222-8222-222222222222','User B certificate','test');
insert into storage.objects(bucket_id,name) values
('certificates','11111111-1111-4111-8111-111111111111/a.pdf'),
('certificates','22222222-2222-4222-8222-222222222222/b.pdf');
set local role authenticated;
select set_config('request.jwt.claim.sub','11111111-1111-4111-8111-111111111111',true);
do $$ begin
  if (select count(*) from public.certificates)<>1 then raise exception 'Cross-user certificate read'; end if;
  if (select count(*) from public.profiles)<>1 then raise exception 'Cross-user profile read'; end if;
  if (select count(*) from storage.objects)<>1 then raise exception 'Cross-user storage read'; end if;
  update public.certificates set title='Illegal update' where id='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
  if found then raise exception 'Cross-user certificate update'; end if;
  begin
    update public.certificates set owner_id='22222222-2222-4222-8222-222222222222';
    raise exception 'Ownership reassignment unexpectedly allowed';
  exception when insufficient_privilege then null; end;
  begin
    insert into public.share_links(owner_id,certificate_id,token_hash,expires_at) values
    ('11111111-1111-4111-8111-111111111111','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',repeat('a',64),now()+interval '1 hour');
    raise exception 'Direct sharing bypass unexpectedly allowed';
  exception when insufficient_privilege then null; end;
  begin
    insert into public.collections(owner_id,name) values ('22222222-2222-4222-8222-222222222222','Not mine');
    raise exception 'Cross-user insert unexpectedly allowed';
  exception when insufficient_privilege then null; end;
  update public.certificates set title='Reviewed by owner' where id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
  if not found then raise exception 'Owner update denied'; end if;
end $$;
reset role;
select 'RLS ownership, storage, consent boundary and column grants passed' as result;
rollback;
