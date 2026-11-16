\set ON_ERROR_STOP on
begin;
insert into auth.users(id) values
  ('11111111-1111-4111-8111-111111111111'),
  ('22222222-2222-4222-8222-222222222222');

set local role certvault_pipeline;
select set_config('certvault.owner','11111111-1111-4111-8111-111111111111',true);
insert into private.storage_upload_tickets(owner_id,object_path,expires_at) values
  ('11111111-1111-4111-8111-111111111111','11111111-1111-4111-8111-111111111111/allowed.pdf',now()+interval '3 minutes'),
  ('11111111-1111-4111-8111-111111111111','11111111-1111-4111-8111-111111111111/expired.pdf',now()-interval '1 second'),
  ('11111111-1111-4111-8111-111111111111','11111111-1111-4111-8111-111111111111/other-owner.pdf',now()+interval '3 minutes');
reset role;

set local role authenticated;
select set_config('request.jwt.claim.sub','11111111-1111-4111-8111-111111111111',true);
insert into storage.objects(bucket_id,name) values
  ('certificates','11111111-1111-4111-8111-111111111111/allowed.pdf');
do $$ begin
  begin
    insert into storage.objects(bucket_id,name) values
      ('certificates','11111111-1111-4111-8111-111111111111/allowed.pdf');
    raise exception 'Consumed upload ticket unexpectedly allowed a replay';
  exception when insufficient_privilege then null; end;
  begin
    insert into storage.objects(bucket_id,name) values
      ('certificates','11111111-1111-4111-8111-111111111111/expired.pdf');
    raise exception 'Expired upload ticket unexpectedly allowed an upload';
  exception when insufficient_privilege then null; end;
end $$;

select set_config('request.jwt.claim.sub','22222222-2222-4222-8222-222222222222',true);
do $$ begin
  begin
    insert into storage.objects(bucket_id,name) values
      ('certificates','11111111-1111-4111-8111-111111111111/other-owner.pdf');
    raise exception 'Cross-owner upload unexpectedly allowed';
  exception when insufficient_privilege then null; end;
  if (select count(*) from storage.objects)<>0 then
    raise exception 'Cross-owner Storage objects visible';
  end if;
end $$;
reset role;
select 'Storage upload ticket expiry, replay and owner isolation passed' as result;
rollback;
