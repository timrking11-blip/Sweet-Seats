# Alerts runtime v0.1: durable jobs and the alert outbox

Status: **built and tested locally; not deployed.** No notification vendor is chosen,
no scheduler is provisioned and nothing is sent to a real person. Traces to SS-DATA-0.1
(JobRun, Alert, DeliveryAttempt, OutcomeEvent) and the Notion 02 first-party record rule.

## What it does

A server-side worker tick (`python -m app.alerts --once`, run every 5 minutes by a
scheduler) sends alerts with the browser closed:

1. **Plan** (`plan_alerts`). From the permission-filtered discovery feed only, for each
   followed artist's upcoming event:
   - `announced`: a scheduled event first seen in the last 7 days;
   - `onsale_soon`: public on-sale opens within the hour;
   - `onsale_open`: on-sale opened in the last 24 hours;
   - `status_changed`: the event is postponed, cancelled or rescheduled.

   Stale observations never alert.
2. **Outbox** (`enqueue_alerts`). One row per alert with a dedupe key per user, event,
   trigger (and on-sale time or status). Re-planning is idempotent.
3. **Dispatch** (`dispatch_due`). Leases due alerts with `FOR UPDATE SKIP LOCKED`, so
   several workers can share the queue. Immediately before sending it re-checks expiry,
   that the event is still displayable, freshness, and current consent (an unrevoked
   subscription and no deletion request); otherwise the alert is suppressed with a
   reason. Each attempt per subscription is recorded. Failures back off (2, 4, 8, ...
   up to 60 minutes) and stop as `failed` after 5 attempts.
4. **Jobs** (`run_job`). Each tick's plan and dispatch run as durable jobs keyed by the
   5-minute tick, so missed ticks coalesce instead of replaying. Leases recover a
   crashed worker; failures retry with backoff and end as `dead` after the cap. Error
   records keep a fixed code, never a message.

Delivery is **at-least-once**: a crash after a send but before its commit leaves the
alert `sending`; after the 5-minute lease it is retried. Provider message ids on each
attempt support reconciliation.

## First-party record rule

`alerts`, `delivery_attempts` and `outcome_events` store IDs, statuses and times only.
Message text (title, venue, date) is rendered at send time from the current projection
and never stored. `supabase/tests/user_isolation_test.sql` pins every allowed column;
a negative control adds a provider title column and must be caught.

## Outcome records

`outcome_events` records `alert_opened`, `link_clicked`, `dismissed` and
`purchase_confirmed`. Users insert only their own rows, only while their separate
outcome consent (`user_profiles.outcome_consent_at`) is set and no deletion is
requested, and only against their own alerts. A click is never a purchase: a purchase
requires a user-confirmed total, currency and confirmation method, and other kinds may
not carry a total.

## Not activated (owner decisions)

- Notification vendor and channel (email / web push). Only `LogTransport`, which sends
  nothing, exists.
- Scheduler hosting (proposed: Render cron) and runtime accounts.
- API endpoints for follows, consent and outcomes with Supabase sign-in verification.
- Persisting live provider observations in PostgreSQL. `source_event_records` still
  requires reserved `.invalid` URLs, a deliberate synthetic-only guard; lifting it is a
  separate decision before any live source.
