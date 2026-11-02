-- Phase 2 runtime: durable jobs, the alert outbox, delivery attempts and consented
-- outcome records (SS-DATA-0.1 JobRun, Alert, DeliveryAttempt, OutcomeEvent).
--
-- First-party record rule (Notion 02, 2026-10-18): none of these tables stores a
-- licensed provider value. Alerts and outcomes reference provider-derived data only by
-- internal ID (event_id); message text is rendered at send time from the current,
-- permission-filtered projection and is not stored. supabase/tests/user_isolation_test.sql
-- pins the allowed columns.

-- Durable jobs: one row per logical run; retries re-use the row; leases recover crashes.
create table public.job_runs (
  job_run_id uuid primary key default gen_random_uuid(),
  job_type text not null check (job_type ~ '^[a-z][a-z0-9_]{1,40}$'),
  logical_key text not null check (btrim(logical_key) <> ''),
  status text not null default 'queued'
    check (status in ('queued', 'running', 'succeeded', 'failed', 'dead')),
  attempt integer not null default 0 check (attempt >= 0),
  max_attempts integer not null default 5 check (max_attempts > 0),
  run_after timestamptz not null default now(),
  lease_owner text,
  lease_expires_at timestamptz,
  last_error_code text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz,
  unique (job_type, logical_key),
  check ((status = 'running') = (lease_owner is not null and lease_expires_at is not null))
);

-- The outbox: an alert is a logical notification intent, separate from transport.
create table public.alerts (
  alert_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.user_profiles(user_id) on delete cascade,
  event_id uuid not null references public.events(event_id) on delete restrict,
  trigger_type text not null
    check (trigger_type in ('announced', 'onsale_soon', 'onsale_open', 'status_changed')),
  dedupe_key text not null unique check (btrim(dedupe_key) <> ''),
  template_version text not null check (btrim(template_version) <> ''),
  status text not null default 'pending'
    check (status in ('pending', 'sending', 'sent', 'suppressed', 'failed')),
  suppressed_reason text,
  attempts integer not null default 0 check (attempts >= 0),
  next_attempt_at timestamptz not null default now(),
  lease_owner text,
  lease_expires_at timestamptz,
  expires_at timestamptz not null,
  created_at timestamptz not null default now(),
  sent_at timestamptz,
  check ((status = 'suppressed') = (suppressed_reason is not null)),
  check ((status = 'sending') = (lease_owner is not null and lease_expires_at is not null)),
  check ((status = 'sent') = (sent_at is not null))
);

create index alerts_due_idx on public.alerts (next_attempt_at) where status = 'pending';

create table public.delivery_attempts (
  delivery_attempt_id uuid primary key default gen_random_uuid(),
  alert_id uuid not null references public.alerts(alert_id) on delete cascade,
  subscription_id uuid not null references public.notification_subscriptions(subscription_id)
    on delete cascade,
  attempt_no integer not null check (attempt_no > 0),
  status text not null check (status in ('sent', 'failed')),
  provider_message_id text,
  error_code text,
  attempted_at timestamptz not null default now(),
  unique (alert_id, subscription_id, attempt_no),
  check ((status = 'sent') = (provider_message_id is not null)),
  check ((status = 'failed') = (error_code is not null))
);

-- Outcome research needs its own consent, separate from notification consent.
alter table public.user_profiles
  add column outcome_consent_version text,
  add column outcome_consent_at timestamptz,
  add constraint user_profiles_outcome_consent_pair
    check ((outcome_consent_version is null) = (outcome_consent_at is null));

-- Observed user responses. A click is never a purchase; a purchase total is what the
-- user confirmed (first-party), never a provider price.
create table public.outcome_events (
  outcome_event_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.user_profiles(user_id) on delete cascade,
  alert_id uuid references public.alerts(alert_id) on delete set null,
  event_id uuid not null references public.events(event_id) on delete restrict,
  kind text not null
    check (kind in ('alert_opened', 'link_clicked', 'dismissed', 'purchase_confirmed')),
  occurred_at timestamptz not null,
  recorded_at timestamptz not null default now(),
  confirmation_method text check (confirmation_method in ('user_entered', 'receipt_uploaded')),
  paid_total_minor bigint check (paid_total_minor is null or paid_total_minor >= 0),
  currency text check (currency is null or currency ~ '^[A-Z]{3}$'),
  check (
    (kind = 'purchase_confirmed'
      and confirmation_method is not null and paid_total_minor is not null and currency is not null)
    or (kind <> 'purchase_confirmed'
      and confirmation_method is null and paid_total_minor is null and currency is null)
  ),
  check (occurred_at <= recorded_at + interval '5 minutes')
);

alter table public.job_runs enable row level security;
alter table public.alerts enable row level security;
alter table public.delivery_attempts enable row level security;
alter table public.outcome_events enable row level security;

-- Jobs and delivery attempts are worker-only (service role). Users read their own
-- alerts and record their own outcomes, only while outcome consent is current.
create policy alerts_read_own on public.alerts
  for select to authenticated
  using (user_id = (select auth.uid()));

create policy outcome_events_read_own on public.outcome_events
  for select to authenticated
  using (user_id = (select auth.uid()));

create policy outcome_events_insert_with_consent on public.outcome_events
  for insert to authenticated
  with check (
    user_id = (select auth.uid())
    and exists (
      select 1 from public.user_profiles profile
      where profile.user_id = (select auth.uid())
        and profile.outcome_consent_at is not null
        and profile.deletion_requested_at is null
    )
    and (alert_id is null or exists (
      select 1 from public.alerts alert
      where alert.alert_id = outcome_events.alert_id and alert.user_id = (select auth.uid())
    ))
  );
