"""Durable jobs and the alert outbox (Phase 2 runtime; SS-DATA-0.1 JobRun, Alert,
DeliveryAttempt).

The worker runs server-side on a schedule, so alerts go out with the browser closed.

- plan_alerts decides which alerts are due from the permission-filtered feed only.
- enqueue_alerts writes them to the outbox; dedupe keys make re-planning idempotent.
- dispatch_due claims due alerts with a lease, re-checks expiry, display permission,
  freshness and current consent at send time, renders the message then (it is never
  stored), records each delivery attempt, and retries with backoff up to a cap.
  Delivery state is per subscription: a retry goes only to subscriptions not yet
  delivered, and the alert finishes when every subscription is terminal.
- run_job wraps a unit of work in a durable job row with a lease, retries and a
  dead-letter state. Missed ticks coalesce: each tick has one logical key.

Delivery is at-least-once. A crash between a send and its commit leaves the alert
"sending"; when the lease expires it is retried, so a duplicate send is possible and
the provider message id on each attempt supports reconciliation.

First-party record rule: alerts and attempts store IDs, never provider values.
"""
from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from .discovery import timestamp

TEMPLATE_VERSION = "alerts-v1"
ONSALE_SOON = timedelta(hours=1)
ONSALE_FRESH = timedelta(hours=24)
ANNOUNCE_WINDOW = timedelta(days=7)
MAX_ATTEMPTS = 5
LEASE = timedelta(minutes=5)
TICK = timedelta(minutes=5)
STATUS_TRIGGERS = {"postponed", "cancelled", "rescheduled"}


class TransportError(Exception):
    """Raised by a transport with a fixed code; never an address or message body."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class Transport:
    """Delivery channel interface. The email/push vendor is an open owner decision."""

    def send(self, channel: str, endpoint_ref: str, message: dict) -> str:
        raise NotImplementedError


class LogTransport(Transport):
    """Local development transport: records messages in memory, contacts no one."""

    def __init__(self):
        self.sent: list[tuple[str, str, dict]] = []

    def send(self, channel: str, endpoint_ref: str, message: dict) -> str:
        self.sent.append((channel, endpoint_ref, message))
        return "log-" + uuid4().hex


@dataclass(frozen=True)
class AlertIntent:
    user_id: str
    event_id: str
    trigger_type: str
    dedupe_key: str
    expires_at: datetime


def _event_end(event: dict) -> datetime:
    if event["starts_at"]:
        return timestamp(event["starts_at"])
    local_end = datetime.fromisoformat(event["local_date"]).replace(
        hour=23, minute=59, second=59, tzinfo=ZoneInfo(event["timezone"]))
    return local_end.astimezone(UTC)


def plan_alerts(feed: dict, follows: Iterable[tuple[str, str]], now: datetime) -> list[AlertIntent]:
    """Alert intents for followed artists' events in the current projection.

    Only displayable, fresh events are considered: the feed is already permission-
    filtered, and a stale observation never triggers an alert.
    """
    followers: dict[str, set[str]] = {}
    for user_id, artist_id in follows:
        followers.setdefault(str(artist_id), set()).add(str(user_id))
    intents = []
    for event in feed["events"]:
        if event["stale"]:
            continue
        users = set().union(*(followers.get(p["artist_id"], set()) for p in event["performers"]))
        if not users:
            continue
        end = _event_end(event)
        if end <= now:
            continue
        eid = event["event_id"]
        due = []
        first_seen = timestamp(event["first_seen_at"])
        if now - first_seen <= ANNOUNCE_WINDOW and event["status"] == "scheduled":
            due.append(("announced", f"announced:{eid}", min(end, first_seen + ANNOUNCE_WINDOW)))
        if event["status"] in STATUS_TRIGGERS:
            due.append(("status_changed", f"status:{eid}:{event['status']}", end))
        if event.get("onsale_at") and event["status"] in {"scheduled", "rescheduled"}:
            onsale = timestamp(event["onsale_at"])
            if timedelta(0) < onsale - now <= ONSALE_SOON:
                due.append(("onsale_soon", f"onsale_soon:{eid}:{event['onsale_at']}", onsale))
            elif timedelta(0) <= now - onsale < ONSALE_FRESH:
                due.append(("onsale_open", f"onsale_open:{eid}:{event['onsale_at']}",
                            min(end, onsale + ONSALE_FRESH)))
        for user in sorted(users):
            for trigger, key, expires in due:
                intents.append(AlertIntent(user, eid, trigger, f"{key}:{user}", expires))
    return intents


def enqueue_alerts(conn, intents: Iterable[AlertIntent], now: datetime) -> int:
    """Write intents to the outbox. An existing dedupe key is left untouched."""
    created = 0
    for intent in intents:
        cursor = conn.execute(
            """INSERT INTO alerts(user_id, event_id, trigger_type, dedupe_key, template_version,
                                  next_attempt_at, expires_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (dedupe_key) DO NOTHING""",
            (intent.user_id, intent.event_id, intent.trigger_type, intent.dedupe_key,
             TEMPLATE_VERSION, now, intent.expires_at))
        created += cursor.rowcount
    return created


def render(alert: dict, event: dict) -> dict:
    """Message built at send time from the current projection; never stored."""
    lead = {"announced": "Just announced", "onsale_soon": "On sale within the hour",
            "onsale_open": "On sale now", "status_changed": f"Now {event['status']}"}
    return {"template_version": alert["template_version"], "alert_id": str(alert["alert_id"]),
            "event_id": event["event_id"], "headline": lead[alert["trigger_type"]],
            "title": event["title"], "venue": event["venue"]["name"],
            "local_date": event["local_date"], "starts_at": event["starts_at"]}


def reclaim_expired_leases(conn, now: datetime) -> int:
    """An alert left 'sending' past its lease (worker crash) goes back to pending."""
    return conn.execute(
        """UPDATE alerts SET status = 'pending', lease_owner = NULL, lease_expires_at = NULL,
                  attempts = attempts + 1, next_attempt_at = %s
           WHERE status = 'sending' AND lease_expires_at < %s""", (now, now)).rowcount


def claim_due(conn, now: datetime, worker: str, limit: int = 20) -> list[dict]:
    """Lease due alerts. SKIP LOCKED lets several workers share the queue safely."""
    with conn.transaction():
        return conn.execute(
            """UPDATE alerts SET status = 'sending', lease_owner = %s, lease_expires_at = %s
               WHERE alert_id IN (
                 SELECT alert_id FROM alerts WHERE status = 'pending' AND next_attempt_at <= %s
                 ORDER BY next_attempt_at, alert_id LIMIT %s FOR UPDATE SKIP LOCKED)
               RETURNING *""", (worker, now + LEASE, now, limit)).fetchall()


def _finish(conn, alert_id, worker: str, **fields) -> None:
    sets = ", ".join(f"{name} = %s" for name in fields)
    conn.execute(
        f"""UPDATE alerts SET {sets}, lease_owner = NULL, lease_expires_at = NULL
            WHERE alert_id = %s AND lease_owner = %s""",  # Column names are constants.
        (*fields.values(), alert_id, worker))


def _dispatch_one(conn, transport: Transport, alert: dict, event: dict | None, now: datetime,
                  worker: str) -> str:
    """Deliver one claimed alert to the subscriptions still owed it; returns the outcome."""
    alert_id = alert["alert_id"]
    reason = ("expired" if now >= alert["expires_at"]
              else "not_displayable" if event is None
              else "stale_source" if event["stale"] else None)
    current = [] if reason else [row["subscription_id"] for row in conn.execute(
        """SELECT s.subscription_id
           FROM notification_subscriptions s
           JOIN user_profiles p ON p.user_id = s.user_id
           WHERE s.user_id = %s AND s.revoked_at IS NULL AND s.consent_at <= %s
             AND p.deletion_requested_at IS NULL""", (alert["user_id"], now))]
    for subscription_id in current:
        conn.execute(
            """INSERT INTO alert_deliveries(alert_id, subscription_id, updated_at)
               VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""", (alert_id, subscription_id, now))
    # A pending delivery no longer owed: the alert lapsed, or that consent was withdrawn.
    conn.execute(
        """UPDATE alert_deliveries SET status = 'suppressed', suppressed_reason = %s, updated_at = %s
           WHERE alert_id = %s AND status = 'pending' AND NOT subscription_id = ANY(%s::uuid[])""",
        (reason or "no_current_consent", now, alert_id, current))
    owed = conn.execute(
        """SELECT d.subscription_id, d.attempts, s.channel, s.endpoint_ref
           FROM alert_deliveries d JOIN notification_subscriptions s USING (subscription_id)
           WHERE d.alert_id = %s AND d.status = 'pending'
           ORDER BY d.subscription_id""", (alert_id,)).fetchall()
    message = render(alert, event) if owed else None
    for sub in owed:
        attempt_no = sub["attempts"] + 1
        try:
            provider_id = transport.send(sub["channel"], sub["endpoint_ref"], message)
            row = ("sent", provider_id, None)
        except TransportError as exc:
            row = ("failed", None, exc.code)
        conn.execute(
            """INSERT INTO delivery_attempts(alert_id, subscription_id, attempt_no, status,
                                             provider_message_id, error_code, attempted_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (alert_id, sub["subscription_id"], attempt_no, *row, now))
        # Terminal failure rule: MAX_ATTEMPTS failed attempts for this subscription.
        status = row[0] if row[0] == "sent" or attempt_no >= MAX_ATTEMPTS else "pending"
        conn.execute(
            """UPDATE alert_deliveries SET status = %s, attempts = %s, last_error_code = %s,
                      sent_at = %s, updated_at = %s
               WHERE alert_id = %s AND subscription_id = %s""",
            (status, attempt_no, row[2], now if status == "sent" else None, now,
             alert_id, sub["subscription_id"]))
    deliveries = conn.execute(
        "SELECT status, sent_at FROM alert_deliveries WHERE alert_id = %s", (alert_id,)).fetchall()
    attempts = alert["attempts"] + (1 if owed else 0)
    statuses = {d["status"] for d in deliveries}
    if "pending" in statuses:
        backoff = timedelta(minutes=min(2 ** attempts, 60))
        _finish(conn, alert_id, worker, status="pending", attempts=attempts,
                next_attempt_at=now + backoff)
        return "retry"
    # Every subscription is terminal. Sent if any delivery succeeded.
    if "sent" in statuses:
        _finish(conn, alert_id, worker, status="sent", attempts=attempts,
                sent_at=max(d["sent_at"] for d in deliveries if d["sent_at"]))
        return "sent"
    if "failed" in statuses:
        _finish(conn, alert_id, worker, status="failed", attempts=attempts)
        return "failed"
    _finish(conn, alert_id, worker, status="suppressed",
            suppressed_reason=reason or "no_current_consent")
    return "suppressed"


def dispatch_due(conn, transport: Transport, feed: dict, now: datetime, worker: str,
                 limit: int = 20) -> dict:
    """Send due alerts. Each alert's outcome is committed on its own.

    Delivery state is kept per subscription (alert_deliveries). A retry sends only to
    subscriptions still pending, so one channel failing never re-sends another's message.
    The alert finishes once every subscription is sent, failed MAX_ATTEMPTS times, or
    suppressed (consent withdrawn, or the alert expired or lost display permission).
    """
    reclaim_expired_leases(conn, now)
    events = {e["event_id"]: e for e in feed["events"]}
    counts = {"sent": 0, "suppressed": 0, "retry": 0, "failed": 0}
    for alert in claim_due(conn, now, worker, limit):
        with conn.transaction():
            event = events.get(str(alert["event_id"]))
            counts[_dispatch_one(conn, transport, alert, event, now, worker)] += 1
    return counts


def run_job(conn, job_type: str, logical_key: str, work: Callable[[], dict], now: datetime,
            worker: str, max_attempts: int = MAX_ATTEMPTS) -> dict | None:
    """Run work once per (job_type, logical_key). Returns None if not claimable now.

    Claimable: new, failed and due for retry, or running with an expired lease.
    Succeeded and dead jobs are never re-run. Errors keep a fixed code (the exception
    type), never a message that could carry provider or user data.
    """
    with conn.transaction():
        job = conn.execute(
            """INSERT INTO job_runs(job_type, logical_key, status, attempt, max_attempts,
                                    lease_owner, lease_expires_at, started_at, run_after)
               VALUES (%s, %s, 'running', 1, %s, %s, %s, %s, %s)
               ON CONFLICT (job_type, logical_key) DO UPDATE
                 SET status = 'running', attempt = job_runs.attempt + 1,
                     lease_owner = excluded.lease_owner, lease_expires_at = excluded.lease_expires_at,
                     started_at = excluded.started_at
                 WHERE (job_runs.status = 'failed' AND job_runs.run_after <= excluded.run_after)
                    OR (job_runs.status = 'running' AND job_runs.lease_expires_at < excluded.run_after)
               RETURNING *""",
            (job_type, logical_key, max_attempts, worker, now + LEASE, now, now)).fetchone()
    if job is None:
        return None
    try:
        result = work()
    except Exception as exc:  # noqa: BLE001 - recorded as a fixed code, then retried.
        dead = job["attempt"] >= job["max_attempts"]
        with conn.transaction():
            conn.execute(
                """UPDATE job_runs SET status = %s, last_error_code = %s, lease_owner = NULL,
                          lease_expires_at = NULL, finished_at = %s, run_after = %s
                   WHERE job_run_id = %s""",
                ("dead" if dead else "failed", type(exc).__name__, now,
                 now + timedelta(minutes=min(2 ** job["attempt"], 60)), job["job_run_id"]))
        return {"status": "dead" if dead else "failed", "error_code": type(exc).__name__}
    with conn.transaction():
        conn.execute(
            """UPDATE job_runs SET status = 'succeeded', lease_owner = NULL, lease_expires_at = NULL,
                      finished_at = %s, last_error_code = NULL WHERE job_run_id = %s""",
            (now, job["job_run_id"]))
    return {"status": "succeeded", **result}


def tick_key(now: datetime) -> str:
    floored = now.astimezone(UTC).replace(second=0, microsecond=0)
    floored -= timedelta(minutes=floored.minute % int(TICK.total_seconds() // 60))
    return floored.strftime("%Y-%m-%dT%H:%MZ")


def tick(store, transport: Transport, now: datetime, worker: str) -> dict:
    """One scheduler tick: plan alerts, then dispatch. Each is a durable job."""
    key = tick_key(now)
    feed = store.feed(now)
    with store._connect() as conn:
        conn.autocommit = True

        def plan():
            follows = conn.execute(
                "SELECT user_id, artist_id FROM artist_follows WHERE enabled").fetchall()
            intents = plan_alerts(feed, [(r["user_id"], r["artist_id"]) for r in follows], now)
            with conn.transaction():
                return {"planned": len(intents), "created": enqueue_alerts(conn, intents, now)}

        planned = run_job(conn, "plan_alerts", key, plan, now, worker)
        dispatched = run_job(conn, "dispatch_alerts", key,
                             lambda: dispatch_due(conn, transport, feed, now, worker), now, worker)
    return {"tick": key, "plan": planned, "dispatch": dispatched}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one local alert worker tick.")
    parser.add_argument("--once", action="store_true", required=True)
    parser.parse_args()
    from .discovery_postgres import PostgresStore

    dsn = os.environ.get("SWEET_SEATS_LOCAL_DATABASE_URL")
    if not dsn:
        parser.exit(1, "SWEET_SEATS_LOCAL_DATABASE_URL is required; no hosted database is used.\n")
    result = tick(PostgresStore(dsn), LogTransport(), datetime.now(UTC), "local-" + uuid4().hex[:8])
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
