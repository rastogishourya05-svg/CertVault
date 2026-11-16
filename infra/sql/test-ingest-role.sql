\set ON_ERROR_STOP on
begin;

do $$ begin
  if exists (select 1 from pg_catalog.pg_roles where rolname='certvault_ingest_test') then
    raise exception 'certvault_ingest_test already exists; refusing to change it';
  end if;
end $$;

create role certvault_ingest_test login noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls;
grant certvault_pipeline to certvault_ingest_test with set true;

do $$ declare r pg_catalog.pg_roles%rowtype; begin
  select * into r from pg_catalog.pg_roles where rolname='certvault_ingest_test';
  if not r.rolcanlogin or r.rolinherit or r.rolsuper or r.rolcreatedb or r.rolcreaterole
     or r.rolreplication or r.rolbypassrls then
    raise exception 'certvault_ingest_test has an unsafe role attribute';
  end if;
  if not pg_catalog.pg_has_role('certvault_ingest_test','certvault_pipeline','SET') then
    raise exception 'login cannot SET ROLE certvault_pipeline';
  end if;
  if pg_catalog.has_table_privilege('certvault_ingest_test','private.mailbox_tokens','select') then
    raise exception 'NOINHERIT login unexpectedly inherits pipeline table privileges';
  end if;
end $$;

set local role certvault_ingest_test;
do $$ begin
  if current_user <> 'certvault_ingest_test' then
    raise exception 'login could not assume its own role';
  end if;
end $$;
set local role certvault_pipeline;
do $$ begin
  if current_user <> 'certvault_pipeline' then
    raise exception 'SET ROLE certvault_pipeline failed';
  end if;
  if not pg_catalog.has_table_privilege(current_user,'private.mailbox_tokens','select') then
    raise exception 'pipeline role is missing expected ingestion access';
  end if;
end $$;
reset role;
rollback;

select 'Least-privileged ingestion login and SET ROLE passed; all role changes rolled back' as result;
