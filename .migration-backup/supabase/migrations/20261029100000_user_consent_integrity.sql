-- Consent evidence integrity for signed-in users (Phase 2 closure; proposed, see
-- docs/phase-assessment.md G-04).
--
-- Supabase grants anon and authenticated full table privileges by default, and the
-- Phase 2 user-core policies are "for all" own-row policies. Through the Data API a
-- signed-in user could therefore create a notification subscription with any endpoint
-- reference (including another person's), rewrite or back-date consent, reverse a
-- revocation, and delete delivery evidence by cascade. Consent is evidence the worker
-- relies on before every send, so it is now written by the server:
--
-- notification_subscriptions
--   - authenticated may only UPDATE revoked_at (column grant); no INSERT or DELETE.
--     Creating a subscription needs a verified endpoint and a recorded consent version,
--     which is a server flow (notification vendor is an open owner decision).
--   - a revocation by a signed-in user is stamped with the database time and is one
--     way: it cannot be back-dated, changed or reversed. Re-consent is a server flow.
-- user_profiles
--   - outcome_consent_at and deletion_requested_at set by a signed-in user are stamped
--     with the database time; changing the outcome consent version re-stamps it.
--   - no direct DELETE: deleting the profile row would cascade away follows, consent
--     and delivery evidence and let a user re-create a profile without their deletion
--     request. Erasure is a server purge (retention period: owner decision, G-06).
--   - after a deletion request the user can no longer change the profile or follows
--     (proposed: cancellation needs a recorded server flow, if the owner wants one).
--
-- Service-role workers and the migration owner are unaffected. RLS policies are
-- unchanged and still scope every row to auth.uid().

revoke insert, update, delete on public.notification_subscriptions from anon, authenticated;
grant update (revoked_at) on public.notification_subscriptions to authenticated;
revoke delete on public.user_profiles from anon, authenticated;
-- TRUNCATE ignores row-level security. The Data API cannot issue it, but these roles
-- never need it on user or outbox tables (defence in depth).
revoke truncate, trigger, references on public.user_profiles, public.artist_follows,
  public.notification_subscriptions, public.alerts, public.alert_deliveries,
  public.delivery_attempts, public.outcome_events, public.job_runs from anon, authenticated;

create function public.stamp_user_revocation() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if current_user <> 'authenticated' then
    return new;
  end if;
  if old.revoked_at is not null then
    if new.revoked_at is distinct from old.revoked_at then
      raise exception 'revocation_is_final' using errcode = '42501';
    end if;
    return new;
  end if;
  if new.revoked_at is not null then
    new.revoked_at := now();
  end if;
  return new;
end;
$$;

create trigger notification_subscriptions_stamp_revocation
  before update on public.notification_subscriptions
  for each row execute function public.stamp_user_revocation();

create function public.stamp_user_profile_consent() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if current_user <> 'authenticated' then
    return new;
  end if;
  if tg_op = 'UPDATE' and old.deletion_requested_at is not null then
    raise exception 'deletion_requested' using errcode = '42501';
  end if;
  if new.deletion_requested_at is not null
     and (tg_op = 'INSERT' or old.deletion_requested_at is null) then
    new.deletion_requested_at := now();
  end if;
  if new.outcome_consent_at is not null
     and (tg_op = 'INSERT' or new.outcome_consent_at is distinct from old.outcome_consent_at
          or new.outcome_consent_version is distinct from old.outcome_consent_version) then
    new.outcome_consent_at := now();
  end if;
  return new;
end;
$$;

create trigger user_profiles_stamp_consent
  before insert or update on public.user_profiles
  for each row execute function public.stamp_user_profile_consent();

-- A signed-in user with a deletion request cannot add or change follows.
create function public.refuse_follow_after_deletion_request() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if current_user = 'authenticated' and exists (
       select 1 from public.user_profiles p
       where p.user_id = new.user_id and p.deletion_requested_at is not null) then
    raise exception 'deletion_requested' using errcode = '42501';
  end if;
  return new;
end;
$$;

create trigger artist_follows_refuse_after_deletion_request
  before insert or update on public.artist_follows
  for each row execute function public.refuse_follow_after_deletion_request();

-- Trigger functions are not callable as functions; keep them out of the API surface.
revoke all on function public.stamp_user_revocation() from public, anon, authenticated;
revoke all on function public.stamp_user_profile_consent() from public, anon, authenticated;
revoke all on function public.refuse_follow_after_deletion_request() from public, anon, authenticated;
