-- Waitlist privacy: the Data API roles can neither read nor write sign-ups, and the
-- table holds only normalised, consented rows. Run after the emulation scripts and the
-- migrations. Everything runs in one transaction and is rolled back.

begin;

do $$
declare
  api_role text;
  n bigint;
  policy_count integer;
begin
  insert into public.waitlist_signups (email, consent_version, consent_copy_sha256, source, artists)
  values ('fan@example.test', 'waitlist-2026-11-17', repeat('a', 64), 'instagram', array['Synthetic Band']);

  select count(*) into policy_count from pg_policies
  where schemaname = 'public' and tablename = 'waitlist_signups';
  if policy_count > 0 then
    raise exception 'FAIL waitlist_signups has % RLS policies; expected none', policy_count;
  end if;

  foreach api_role in array array['anon', 'authenticated'] loop
    if has_table_privilege(api_role, 'public.waitlist_signups', 'SELECT')
       or has_table_privilege(api_role, 'public.waitlist_signups', 'INSERT') then
      raise exception 'FAIL % holds privileges on waitlist_signups', api_role;
    end if;
    execute format('set local role %I', api_role);
    begin
      execute 'select count(*) from public.waitlist_signups' into n;
      execute 'reset role';
      raise exception 'FAIL % can read waitlist_signups (% rows)', api_role, n;
    exception when insufficient_privilege then null;
    end;
    begin
      execute $i$insert into public.waitlist_signups (email, consent_version, consent_copy_sha256)
        values ('intruder@example.test', 'v1', repeat('b', 64))$i$;
      execute 'reset role';
      raise exception 'FAIL % inserted a waitlist sign-up', api_role;
    exception when insufficient_privilege then null;
    end;
    execute 'reset role';
  end loop;
  raise notice 'ok - API roles cannot read or write the waitlist';

  begin
    insert into public.waitlist_signups (email, consent_version, consent_copy_sha256)
    values ('Mixed@Example.test', 'waitlist-2026-11-17', repeat('a', 64));
    raise exception 'FAIL an email that is not normalised was accepted';
  exception when check_violation then null;
  end;
  begin
    insert into public.waitlist_signups (email, consent_version, consent_copy_sha256)
    values ('other@example.test', 'waitlist-2026-11-17', 'not-a-hash');
    raise exception 'FAIL a sign-up without a consent copy hash was accepted';
  exception when check_violation then null;
  end;
  raise notice 'ok - waitlist rows are normalised and carry consent evidence';
end;
$$;

rollback;
