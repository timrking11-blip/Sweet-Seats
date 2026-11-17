-- Consent history (G-15): every grant and withdrawal is an event tied to a registered
-- copy, events cannot be changed or removed, a user reads only their own, and nobody
-- but the server writes them. Run after the emulation scripts and the migrations.
-- Everything runs in one transaction and is rolled back.

begin;

do $$
declare
  user_a constant uuid := '00000000-0000-4000-8000-0000000000c1';
  user_b constant uuid := '00000000-0000-4000-8000-0000000000c2';
  sub_a uuid;
  n bigint;
  got text;
begin
  insert into auth.users (id) values (user_a), (user_b);
  insert into public.consent_copies (kind, version, copy_sha256) values
    ('alerts_email', 'email-1', repeat('e', 64)), ('outcomes', 'retired-1', repeat('d', 64));
  update public.consent_copies set retired_at = now() where version = 'retired-1';
  insert into public.user_profiles (user_id) values (user_a), (user_b);
  -- The server creates the subscription: a grant with the registered hash.
  insert into public.notification_subscriptions (user_id, channel, endpoint_ref, consent_version, consent_at)
  values (user_a, 'email', 'secret://ca', 'email-1', now()) returning subscription_id into sub_a;
  insert into public.notification_subscriptions (user_id, channel, endpoint_ref, consent_version, consent_at)
  values (user_b, 'email', 'secret://cb', 'email-1', now());

  select copy_sha256 || '/' || source into got from public.consent_events
  where user_id = user_a and kind = 'alerts_email' and action = 'grant';
  if got is distinct from repeat('e', 64) || '/system' then
    raise exception 'FAIL subscription grant not recorded with its copy hash: %', got;
  end if;

  -- The user grants and withdraws outcome consent, and revokes the subscription.
  perform set_config('request.jwt.claim.sub', user_a::text, true);
  set local role authenticated;
  update public.user_profiles set outcome_consent_version = 'outcomes-2026-11-18',
    outcome_consent_at = now() where user_id = user_a;
  begin
    update public.user_profiles set outcome_consent_version = 'made-up', outcome_consent_at = now()
    where user_id = user_a;
    reset role;
    raise exception 'FAIL outcome consent accepted under an unregistered copy';
  exception when insufficient_privilege then null;
  end;
  begin
    update public.user_profiles set outcome_consent_version = 'retired-1', outcome_consent_at = now()
    where user_id = user_a;
    reset role;
    raise exception 'FAIL outcome consent accepted under a retired copy';
  exception when insufficient_privilege then null;
  end;
  update public.user_profiles set outcome_consent_version = null, outcome_consent_at = null
  where user_id = user_a;
  update public.notification_subscriptions set revoked_at = now() where subscription_id = sub_a;

  select string_agg(kind || ':' || action || ':' || source, ',' order by kind, action) into got
  from public.consent_events;
  if got is distinct from 'alerts_email:grant:system,alerts_email:withdraw:user,outcomes:grant:user,outcomes:withdraw:user' then
    reset role;
    raise exception 'FAIL user A sees the wrong consent history: %', got;
  end if;

  -- Events are read-only and the user cannot write one.
  begin
    update public.consent_events set action = 'grant' where user_id = user_a;
    reset role;
    raise exception 'FAIL user A changed a consent event';
  exception when insufficient_privilege then null;
  end;
  begin
    delete from public.consent_events where user_id = user_a;
    reset role;
    raise exception 'FAIL user A deleted a consent event';
  exception when insufficient_privilege then null;
  end;
  begin
    insert into public.consent_events (user_id, kind, action, copy_version, copy_sha256, source)
    values (user_a, 'outcomes', 'grant', 'outcomes-2026-11-18', repeat('f', 64), 'user');
    reset role;
    raise exception 'FAIL user A wrote a consent event directly';
  exception when insufficient_privilege then null;
  end;
  begin
    insert into public.consent_copies (kind, version, copy_sha256) values ('outcomes', 'mine', repeat('0', 64));
    reset role;
    raise exception 'FAIL user A registered a consent copy';
  exception when insufficient_privilege then null;
  end;
  begin
    perform public.append_consent_event(user_a, 'outcomes', 'grant', 'outcomes-2026-11-18', null);
    reset role;
    raise exception 'FAIL user A called the consent event writer';
  exception when insufficient_privilege then null;
  end;
  reset role;

  -- Not even the table owner rewrites history.
  begin
    update public.consent_events set source = 'system' where user_id = user_a;
    raise exception 'FAIL the owner changed a consent event';
  exception when insufficient_privilege then null;
  end;
  begin
    delete from public.consent_events where user_id = user_a;
    raise exception 'FAIL the owner deleted a consent event';
  exception when insufficient_privilege then null;
  end;
  raise notice 'ok - consent history is append-only, copy-bound and per-user';

  -- A bounce named by the server is recorded as one.
  perform set_config('sweet_seats.consent_source', 'bounce', true);
  update public.notification_subscriptions set revoked_at = now() where user_id = user_b;
  perform set_config('sweet_seats.consent_source', '', true);
  select source into got from public.consent_events
  where user_id = user_b and action = 'withdraw';
  if got is distinct from 'bounce' then
    raise exception 'FAIL a bounce withdrawal was recorded as %', got;
  end if;
  select count(*) into n from public.consent_events where user_id = user_b;
  if n <> 2 then
    raise exception 'FAIL user B has % consent events; expected 2', n;
  end if;
  raise notice 'ok - server withdrawals name their cause';
end;
$$;

rollback;
