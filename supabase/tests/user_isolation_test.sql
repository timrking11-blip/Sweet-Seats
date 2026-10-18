-- Per-user isolation and the first-party record rule for the Phase 2 user tables.
-- Run against a disposable database after applying supabase/ci/emulate_supabase_roles.sql
-- and supabase/migrations. Everything runs in one transaction and is rolled back.

begin;

do $$
declare
  user_a constant uuid := '00000000-0000-4000-8000-00000000000a';
  user_b constant uuid := '00000000-0000-4000-8000-00000000000b';
  artist uuid;
  unfollowed uuid;
begin
  insert into auth.users (id) values (user_a), (user_b);
  insert into public.user_profiles (user_id, consent_version) values (user_a, 'c1'), (user_b, 'c1');
  insert into public.artists (canonical_name) values ('Isolation Test Artist') returning artist_id into artist;
  insert into public.artist_follows (user_id, artist_id) values (user_a, artist), (user_b, artist);
  insert into public.notification_subscriptions (user_id, channel, endpoint_ref, consent_version, consent_at)
  values (user_a, 'email', 'secret://a', 'c1', now()), (user_b, 'email', 'secret://b', 'c1', now());
  -- Followed by nobody, so a forged insert can only fail on the access check.
  insert into public.artists (canonical_name) values ('Unfollowed Test Artist') returning artist_id into unfollowed;
  perform set_config('ss_test.artist_id', artist::text, true);
  perform set_config('ss_test.unfollowed_id', unfollowed::text, true);
end;
$$;

do $$
declare
  user_a constant text := '00000000-0000-4000-8000-00000000000a';
  user_b constant text := '00000000-0000-4000-8000-00000000000b';
  artist constant text := current_setting('ss_test.artist_id');
  unfollowed constant text := current_setting('ss_test.unfollowed_id');
  user_tables constant text[] := array['user_profiles', 'artist_follows', 'notification_subscriptions'];
  tbl text;
  n bigint;
begin
  -- Acting as user A.
  perform set_config('request.jwt.claim.sub', user_a, true);
  set local role authenticated;

  foreach tbl in array user_tables loop
    execute format('select count(*) from public.%I', tbl) into n;
    if n <> 1 then
      reset role;
      raise exception 'FAIL user A reads % % rows; expected only their own', n, tbl;
    end if;
    execute format('select count(*) from public.%I where user_id = %L', tbl, user_b) into n;
    if n <> 0 then
      reset role;
      raise exception 'FAIL user A reads user B''s % rows', tbl;
    end if;
    execute format('update public.%I set user_id = user_id where user_id = %L', tbl, user_b);
    get diagnostics n = row_count;
    if n <> 0 then
      reset role;
      raise exception 'FAIL user A updated user B''s % rows', tbl;
    end if;
    execute format('delete from public.%I where user_id = %L', tbl, user_b);
    get diagnostics n = row_count;
    if n <> 0 then
      reset role;
      raise exception 'FAIL user A deleted user B''s % rows', tbl;
    end if;
  end loop;

  -- A cannot write rows on B's behalf, or move their own rows to B.
  begin
    execute format('insert into public.artist_follows (user_id, artist_id) values (%L, %L)', user_b, unfollowed);
    reset role;
    raise exception 'FAIL user A inserted a follow for user B';
  exception when insufficient_privilege then null;
  end;
  begin
    execute format('update public.artist_follows set user_id = %L where user_id = %L', user_b, user_a);
    reset role;
    raise exception 'FAIL user A reassigned a follow to user B';
  exception when insufficient_privilege then null;
  end;

  -- A can manage their own rows.
  update public.artist_follows set enabled = false where user_id = user_a::uuid;
  get diagnostics n = row_count;
  if n <> 1 then
    reset role;
    raise exception 'FAIL user A cannot update their own follow';
  end if;

  -- Anonymous requests see and change nothing.
  perform set_config('request.jwt.claim.sub', '', true);
  reset role;
  set local role anon;
  foreach tbl in array user_tables loop
    execute format('select count(*) from public.%I', tbl) into n;
    if n <> 0 then
      reset role;
      raise exception 'FAIL anon reads % % rows', n, tbl;
    end if;
  end loop;
  begin
    execute format('insert into public.artist_follows (user_id, artist_id) values (%L, %L)', user_a, artist);
    reset role;
    raise exception 'FAIL anon inserted a follow';
  exception when insufficient_privilege then null;
  end;
  reset role;
  raise notice 'ok - users see and change only their own rows; anon sees nothing';
end;
$$;

-- First-party record rule: user tables hold only reviewed first-party columns.
-- Adding a column (for example a provider price or title) fails here until reviewed.
do $$
declare
  unexpected text;
begin
  select string_agg(table_name || '.' || column_name, ', ' order by table_name, column_name)
  into unexpected
  from information_schema.columns
  where table_schema = 'public'
    and (table_name, column_name) not in (
      ('user_profiles', 'user_id'), ('user_profiles', 'locale'), ('user_profiles', 'timezone'),
      ('user_profiles', 'consent_version'), ('user_profiles', 'deletion_requested_at'),
      ('user_profiles', 'created_at'), ('user_profiles', 'updated_at'),
      ('artist_follows', 'follow_id'), ('artist_follows', 'user_id'),
      ('artist_follows', 'artist_id'), ('artist_follows', 'enabled'),
      ('artist_follows', 'created_at'), ('artist_follows', 'updated_at'),
      ('notification_subscriptions', 'subscription_id'), ('notification_subscriptions', 'user_id'),
      ('notification_subscriptions', 'channel'), ('notification_subscriptions', 'endpoint_ref'),
      ('notification_subscriptions', 'consent_version'), ('notification_subscriptions', 'consent_at'),
      ('notification_subscriptions', 'revoked_at'), ('notification_subscriptions', 'created_at'))
    and table_name in ('user_profiles', 'artist_follows', 'notification_subscriptions');
  if unexpected is not null then
    raise exception 'FAIL user tables have unreviewed columns: %', unexpected;
  end if;
  raise notice 'ok - user tables hold only reviewed first-party columns';
end;
$$;

-- Consent: a revocation cannot predate the consent it revokes.
do $$
begin
  begin
    insert into public.notification_subscriptions (user_id, channel, endpoint_ref, consent_version, consent_at, revoked_at)
    values ('00000000-0000-4000-8000-00000000000a', 'web_push', 'secret://a2', 'c1', now(), now() - interval '1 day');
    raise exception 'FAIL revocation before consent was accepted';
  exception when check_violation then null;
  end;
  raise notice 'ok - consent checks hold';
end;
$$;

rollback;
