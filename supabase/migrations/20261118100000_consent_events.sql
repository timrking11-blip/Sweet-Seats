-- Append-only consent history tied to the exact copy shown (G-15; proposed).
--
-- Until now consent was only the latest value on a row: user_profiles.outcome_consent_*
-- and notification_subscriptions.consent_* / revoked_at. A withdrawal overwrote the
-- grant, and outcome consent versions were any string a signed-in user chose, so
-- consent could not be proven later.
--
-- consent_copies registers each published consent text by kind, version and the
-- SHA-256 of the exact copy. Only the server (table owner) adds or retires one.
--
-- consent_events records every grant and withdrawal. It is written only by triggers
-- on the current-state rows, so no path changes consent without an event, and no role
-- can update or delete an event. A signed-in user reads only their own events.
--
--   - outcomes: a signed-in user may set outcome consent only to a registered,
--     unretired outcomes copy; a withdrawal clears it. Each change is an event.
--   - alerts_email: subscriptions are created by the server; creation is a grant and
--     revocation (by the user, a bounce or a complaint) is a withdrawal.
--   - source is 'user' for a signed-in user's change; otherwise the server names it
--     in the transaction setting sweet_seats.consent_source (bounce, complaint), or
--     it is 'system'.
--
-- Events keep the user id after a profile is gone: auth.users cannot be deleted while
-- events exist. Anonymising them at purge time is the G-06 purge job, whose retention
-- period is an owner and counsel decision.

create table public.consent_copies (
  kind text not null check (kind in ('alerts_email', 'outcomes')),
  version text not null check (version ~ '^[a-z0-9][a-z0-9._-]{0,63}$'),
  copy_sha256 text not null check (copy_sha256 ~ '^[0-9a-f]{64}$'),
  published_at timestamptz not null default now(),
  retired_at timestamptz,
  primary key (kind, version),
  check (retired_at is null or retired_at >= published_at)
);

create table public.consent_events (
  consent_event_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id),
  kind text not null check (kind in ('alerts_email', 'outcomes')),
  action text not null check (action in ('grant', 'withdraw')),
  copy_version text,
  -- The registered hash of copy_version, looked up when the event is written; null
  -- for a version never registered (a server-created subscription from before the
  -- registry). A user's outcome grant always has one: the registry trigger refuses
  -- unregistered versions.
  copy_sha256 text check (copy_sha256 ~ '^[0-9a-f]{64}$'),
  -- Not a foreign key: the event must outlive the subscription row.
  subscription_id uuid,
  source text not null check (source in ('user', 'bounce', 'complaint', 'system')),
  created_at timestamptz not null default now(),
  check (action = 'withdraw' or copy_version is not null),
  check ((kind = 'alerts_email') = (subscription_id is not null))
);

create index consent_events_user_idx on public.consent_events (user_id, created_at);

alter table public.consent_copies enable row level security;
alter table public.consent_events enable row level security;
revoke all on public.consent_copies from anon, authenticated;
revoke all on public.consent_events from anon, authenticated;
-- Anyone may read which copies exist (they are what the site shows); nobody else writes.
grant select on public.consent_copies to anon, authenticated;
create policy consent_copies_read on public.consent_copies for select to anon, authenticated
  using (true);
grant select on public.consent_events to authenticated;
create policy consent_events_own on public.consent_events for select to authenticated
  using (user_id = (select auth.uid()));

create function public.refuse_consent_event_change() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception 'consent_events_are_append_only' using errcode = '42501';
end;
$$;

create trigger consent_events_append_only
  before update or delete on public.consent_events
  for each row execute function public.refuse_consent_event_change();

create trigger consent_events_no_truncate
  before truncate on public.consent_events
  for each statement execute function public.refuse_consent_event_change();

-- Who made the change: a signed-in user, or the server naming why.
create function public.consent_source() returns text
language sql
stable
set search_path = ''
as $$
  select case
    when current_setting('role') in ('authenticated', 'anon') then 'user'
    else coalesce(nullif(current_setting('sweet_seats.consent_source', true), ''), 'system')
  end
$$;

create function public.append_consent_event(
  p_user uuid, p_kind text, p_action text, p_version text, p_subscription uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.consent_events
    (user_id, kind, action, copy_version, copy_sha256, subscription_id, source)
  values (p_user, p_kind, p_action, p_version,
          (select c.copy_sha256 from public.consent_copies c
           where c.kind = p_kind and c.version = p_version),
          p_subscription, public.consent_source());
end;
$$;

-- A signed-in user may consent to outcomes only under a registered, current copy.
create function public.require_registered_outcome_copy() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if current_setting('role') in ('authenticated', 'anon')
     and new.outcome_consent_version is not null
     and new.outcome_consent_version is distinct from
         (case when tg_op = 'UPDATE' then old.outcome_consent_version end)
     and not exists (
       select 1 from public.consent_copies c
       where c.kind = 'outcomes' and c.version = new.outcome_consent_version
         and c.retired_at is null) then
    raise exception 'unregistered_consent_copy' using errcode = '42501';
  end if;
  return new;
end;
$$;

create trigger user_profiles_require_registered_outcome_copy
  before insert or update on public.user_profiles
  for each row execute function public.require_registered_outcome_copy();

create function public.record_outcome_consent_event() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.outcome_consent_at is not null
     and (tg_op = 'INSERT' or old.outcome_consent_at is null
          or new.outcome_consent_at is distinct from old.outcome_consent_at
          or new.outcome_consent_version is distinct from old.outcome_consent_version) then
    perform public.append_consent_event(new.user_id, 'outcomes', 'grant',
                                        new.outcome_consent_version, null);
  elsif tg_op = 'UPDATE' and new.outcome_consent_at is null and old.outcome_consent_at is not null then
    perform public.append_consent_event(new.user_id, 'outcomes', 'withdraw',
                                        old.outcome_consent_version, null);
  end if;
  return null;
end;
$$;

create trigger user_profiles_record_outcome_consent
  after insert or update of outcome_consent_version, outcome_consent_at on public.user_profiles
  for each row execute function public.record_outcome_consent_event();

create function public.record_subscription_consent_event() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op = 'INSERT' then
    perform public.append_consent_event(new.user_id, 'alerts_email', 'grant',
                                        new.consent_version, new.subscription_id);
    if new.revoked_at is not null then
      perform public.append_consent_event(new.user_id, 'alerts_email', 'withdraw',
                                          new.consent_version, new.subscription_id);
    end if;
  elsif new.revoked_at is not null and old.revoked_at is null then
    perform public.append_consent_event(new.user_id, 'alerts_email', 'withdraw',
                                        new.consent_version, new.subscription_id);
  elsif new.consent_at is distinct from old.consent_at
        or new.consent_version is distinct from old.consent_version
        or (new.revoked_at is null and old.revoked_at is not null) then
    -- A server re-consent on the same row is a new grant.
    perform public.append_consent_event(new.user_id, 'alerts_email', 'grant',
                                        new.consent_version, new.subscription_id);
  end if;
  return null;
end;
$$;

create trigger notification_subscriptions_record_consent
  after insert or update of consent_version, consent_at, revoked_at
  on public.notification_subscriptions
  for each row execute function public.record_subscription_consent_event();

revoke all on function public.refuse_consent_event_change() from public, anon, authenticated;
revoke all on function public.consent_source() from public, anon, authenticated;
revoke all on function public.append_consent_event(uuid, text, text, text, uuid)
  from public, anon, authenticated;
revoke all on function public.require_registered_outcome_copy() from public, anon, authenticated;
revoke all on function public.record_outcome_consent_event() from public, anon, authenticated;
revoke all on function public.record_subscription_consent_event() from public, anon, authenticated;

-- The outcome consent copy the API shows (services/api/app/consent.py; proposed wording,
-- for owner and counsel review). tests/ checks that this hash matches the API's copy.
insert into public.consent_copies (kind, version, copy_sha256) values
  ('outcomes', 'outcomes-2026-11-18',
   'b3f030c4e2ec37c5714d88614cfa8ae056a1d6b8b87dba636d96213d7ee5c883');
