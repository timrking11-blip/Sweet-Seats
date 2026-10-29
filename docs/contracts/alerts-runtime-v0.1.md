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
   several workers can share the queue; each claim gets a fresh `claim_token`.
   Authorization is never carried over from the tick: immediately before **each
   subscription's** send the worker reads a fresh clock, re-projects the event's
   permission-filtered state (`store_lookup`), and re-checks that subscription's
   consent (unrevoked, no deletion request) in the same transaction that records the
   send intent. Expiry, lost display permission, a stale source or withdrawn consent,
   whether it happens after projection or between two subscriptions, suppresses the
   sends that follow it with a reason. Each attempt per subscription is recorded.

   Delivery state is kept per subscription (`alert_deliveries`). When email succeeds
   and push fails, the alert stays `pending`; the retry sends to push only, and email
   is never sent again. A subscription is terminal when it is `sent`, `failed` (5
   failed attempts for that subscription), or `suppressed` (its consent was withdrawn,
   or the alert expired or lost display permission before it was delivered there).
   The alert finishes only when every subscription is terminal: `uncertain` if any
   delivery's outcome is unresolved, else `sent` if any delivery succeeded, otherwise
   `failed` or `suppressed`. Retries back off (2, 4, 8, ... up to 60 minutes). A
   permanent transport error (`TransportError(..., permanent=True)`) fails that
   subscription at once; a retryable one is retried. Transport codes that are not
   fixed identifiers are stored as `transport_error`.

   One alert failing never stops the batch. A rendering error fails that alert
   (`render_error`). Any other error rolls back that alert's transaction, then records
   recovery in a fresh one (`dispatch_error`, with backoff). A lost database connection
   is not isolated: the batch ends with the error and the job is never marked
   succeeded; its leases expire into recovery.
4. **Jobs** (`run_job`). Each tick's plan and dispatch run as durable jobs keyed by the
   5-minute tick, so missed ticks coalesce instead of replaying. Each claim is a new
   attempt generation. Success and failure are written only by the current generation:
   same attempt, same lease owner, still `running`, on a live lease; a stale worker gets
   `lease_lost` and writes nothing. A crashed run is re-claimed after its lease and a
   backoff while attempts remain, then dead-lettered (`lease_expired`). Failures retry
   with backoff and end as `dead` after the cap. Error records keep a fixed code, never
   a message.

### Delivery protocol

Delivery is **at-least-once at best; it is never exactly-once**.

1. **Intent.** Each (alert, subscription) has a stable `delivery_key`. Before the send,
   the attempt is committed as `sending`; the key goes to the provider as its
   idempotency key on every try.
2. **Send**, outside any database transaction.
3. **Outcome**, committed separately. A lost response (`DeliveryUncertain`, or any
   unexpected transport exception) records the delivery `uncertain`. If the worker
   crashes or the post-send commit fails, the committed `sending` row stays as durable
   evidence and lease recovery turns it into `uncertain` (`lease_expired`).
4. **Reconcile before retrying.** An uncertain delivery is looked up with the provider
   (`Transport.reconcile`) when it supports lookups, or re-sent under the same key
   only when it de-duplicates by key (`Transport.idempotent`). Otherwise it is never
   re-sent and the alert ends `uncertain` for an operator to review.

**Fencing.** Every write after the claim locks the alert row and requires its current
`claim_token` on a live lease; row-state guards and affected-row counts back it up. A
worker whose lease expired, even under a reused worker name, cannot record an outcome
over its replacement.

**Attempt counting.** `alerts.attempts` counts claims and is incremented when an alert
is claimed, so a crashed round counts exactly once. `alert_deliveries.attempts` counts
sends and is incremented when the intent commits. Both stop at 5; an alert out of
rounds fails what it still owes (`attempts_exhausted`). Per-subscription state survives
recovery unchanged.

## First-party record rule

`alerts`, `alert_deliveries`, `delivery_attempts` and `outcome_events` store IDs,
statuses and times only. Message text (title, venue, date) is rendered at send time from the current projection
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
