-- Alert delivery reliability (PR #23 review): fenced claims, bounded crash recovery and
-- delivery intent recorded before any external send. services/api/app/alerts.py and
-- docs/contracts/alerts-runtime-v0.1.md describe the protocol.
--
-- claim_token   - a fresh UUID per claim. Every completion, failure and delivery-state
--                 write requires the current token on a live lease, so a worker whose
--                 lease expired (even one reusing a worker name) cannot report ownership.
-- delivery_key  - a stable UUID per (alert, subscription), committed before the first
--                 send and passed to the provider as the idempotency key on every try.
-- 'sending'     - a delivery attempt whose intent is committed but whose outcome is not.
--                 A crash leaves it here as durable evidence.
-- 'uncertain'   - the provider may or may not have delivered (lost response, failed
--                 post-send commit, expired lease). It is reconciled before any retry
--                 and never blindly re-sent. An alert that ends with an unresolved
--                 delivery is 'uncertain' and needs review.
-- IDs, statuses, codes and times only (first-party record rule).

alter table public.alerts
  add column claim_token uuid,
  add column last_error_code text;

-- Rows mid-claim under the old protocol keep their lease and get a token, so the new
-- worker recovers them through the normal expired-lease path.
update public.alerts set claim_token = gen_random_uuid() where status = 'sending';

-- Historical failed alerts predate last_error_code. Backfill before validating the
-- terminal-state constraint; preserve their IDs, state and delivery history.
update public.alerts set last_error_code = 'legacy_delivery_failed' where status = 'failed';

alter table public.alerts
  drop constraint alerts_status_check,
  add constraint alerts_status_check
    check (status in ('pending', 'sending', 'sent', 'suppressed', 'failed', 'uncertain')),
  drop constraint alerts_check1,
  add constraint alerts_claim_pair
    check ((status = 'sending') = (lease_owner is not null and lease_expires_at is not null
                                   and claim_token is not null)),
  drop constraint alerts_check2,
  add constraint alerts_sent_at
    check ((status <> 'sent' or sent_at is not null)
           and (sent_at is null or status in ('sent', 'uncertain'))),
  add constraint alerts_terminal_error
    check (status not in ('failed', 'uncertain') or last_error_code is not null);

alter table public.alert_deliveries
  add column delivery_key uuid not null default gen_random_uuid() unique;

alter table public.alert_deliveries
  drop constraint alert_deliveries_status_check,
  add constraint alert_deliveries_status_check
    check (status in ('pending', 'sending', 'sent', 'failed', 'suppressed', 'uncertain')),
  -- A delivery can fail before any send (a permanent render error, or the alert ran out
  -- of attempts), so a failure needs a code but not an attempt.
  drop constraint alert_deliveries_check2,
  add constraint alert_deliveries_error_code
    check (status not in ('failed', 'uncertain') or last_error_code is not null),
  add constraint alert_deliveries_sending_attempted
    check (status not in ('sending', 'uncertain') or attempts > 0);

alter table public.delivery_attempts
  drop constraint delivery_attempts_status_check,
  add constraint delivery_attempts_status_check
    check (status in ('sending', 'sent', 'failed', 'uncertain')),
  drop constraint delivery_attempts_check1,
  add constraint delivery_attempts_error_code
    check ((status in ('failed', 'uncertain')) = (error_code is not null));
