-- Catalog contract for the additive discovery tables. Behavior/lineage/DML denial
-- is exercised with seeded facts in test_discovery_postgres.py on PostgreSQL 16.
begin;
do $$
declare
  tbl text;
  policies integer;
  lineage_keys integer;
begin
  foreach tbl in array array['discovery_state','source_event_records','source_event_performers',
                             'source_unresolved_records'] loop
    if not exists (select 1 from pg_class c join pg_namespace n on n.oid=c.relnamespace
                   where n.nspname='public' and c.relname=tbl and c.relrowsecurity) then
      raise exception 'FAIL discovery RLS missing: %', tbl;
    end if;
    select count(*) into policies from pg_policies where schemaname='public' and tablename=tbl;
    if policies <> 0 then
      raise exception 'FAIL discovery table has policies: %', tbl;
    end if;
    if not has_table_privilege('anon', 'public.' || tbl, 'SELECT,INSERT,UPDATE,DELETE')
       or not has_table_privilege('authenticated', 'public.' || tbl, 'SELECT,INSERT,UPDATE,DELETE') then
      raise exception 'FAIL discovery grant emulation missing: %', tbl;
    end if;
  end loop;
  select count(*) into lineage_keys from pg_constraint
  where conrelid='public.source_event_records'::regclass and contype='f';
  if lineage_keys <> 6 then
    raise exception 'FAIL source observation lineage constraints missing';
  end if;
  if not exists (select 1 from information_schema.columns where table_schema='public'
                 and table_name='collection_runs' and column_name='replay_digest') then
    raise exception 'FAIL replay digest missing';
  end if;
  raise notice 'ok - discovery RLS, policies, grants, lineage keys and replay column';
end;
$$;
rollback;
