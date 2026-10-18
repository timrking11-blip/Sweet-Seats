-- CI-only: reproduce the Supabase Auth surface on plain PostgreSQL.
-- Never apply this to a Supabase project; auth.users and auth.uid() already exist there.
-- Applied separately from the API-role grants so a database built without those grants
-- (the negative control for missing default grants) still has auth.users.

-- auth.uid() reads the request JWT subject the way Supabase's own definition does;
-- tests set request.jwt.claim.sub to act as a user. Supabase projects already have both.
create schema if not exists auth;
create table if not exists auth.users (id uuid primary key);
create or replace function auth.uid() returns uuid
language sql stable
as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim.sub', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')
  )::uuid
$$;
grant usage on schema auth to anon, authenticated, service_role;
grant execute on function auth.uid() to anon, authenticated, service_role;
