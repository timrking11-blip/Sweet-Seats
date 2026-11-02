-- CI-only: reproduce the Supabase API roles and their default grants on plain PostgreSQL.
-- Supabase grants anon/authenticated full table privileges in public by default, so
-- row-level security is the only barrier. Apply this before supabase/migrations so the
-- migration's tables inherit the same grants they would get on a Supabase project.
-- Never apply this to a Supabase project; those roles already exist there.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role nologin noinherit bypassrls;
  end if;
end;
$$;

grant usage on schema public to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
alter default privileges in schema public grant all on functions to anon, authenticated, service_role;
