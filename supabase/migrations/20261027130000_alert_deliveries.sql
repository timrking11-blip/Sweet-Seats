-- Per-subscription delivery state for the alert outbox (SS-DATA-0.1 Alert, DeliveryAttempt).
--
-- An alert goes to every current subscription of its user. One alert-level status
-- cannot say "email delivered, push still owed", so each (alert, subscription) pair
-- keeps its own state. A retry sends only to pairs still pending; a delivered pair is
-- never sent again. An alert is finished once every pair is terminal:
--   sent       - delivered;
--   failed     - failed on MAX_ATTEMPTS attempts (services/api/app/alerts.py);
--   suppressed - not delivered and no longer owed: consent withdrawn for that
--                subscription, or the alert expired or lost display permission first.
-- IDs, statuses, counts and times only (first-party record rule). Worker-only: RLS on
-- and no policies, like delivery_attempts.
create table public.alert_deliveries (
  alert_id uuid not null references public.alerts(alert_id) on delete cascade,
  subscription_id uuid not null references public.notification_subscriptions(subscription_id)
    on delete cascade,
  status text not null default 'pending'
    check (status in ('pending', 'sent', 'failed', 'suppressed')),
  attempts integer not null default 0 check (attempts >= 0),
  last_error_code text,
  suppressed_reason text,
  sent_at timestamptz,
  updated_at timestamptz not null default now(),
  primary key (alert_id, subscription_id),
  check ((status = 'sent') = (sent_at is not null)),
  check ((status = 'suppressed') = (suppressed_reason is not null)),
  check (status <> 'failed' or (attempts > 0 and last_error_code is not null))
);

alter table public.alert_deliveries enable row level security;
