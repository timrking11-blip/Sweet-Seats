"""Durable jobs and the alert outbox (Phase 2 runtime; SS-DATA-0.1 JobRun, Alert,
DeliveryAttempt).

The worker runs server-side on a schedule, so alerts go out with the browser closed.

- plan_alerts decides which alerts are due from the permission-filtered feed only.
- enqueue_alerts writes them to the outbox; dedupe keys make re-planning idempotent.
- dispatch_due claims due alerts with a lease and a fresh claim token. Immediately
  before each subscription's send it reads a fresh clock, the event's current
  permission-filtered projection and that subscription's current consent, renders the
  message then (it is never stored), and records each delivery attempt. Delivery state is per
  subscription: a retry goes only to subscriptions still owed, and the alert finishes
  when every subscription is terminal. One alert failing never stops the alerts after it.
- run_job wraps a unit of work in a durable job row with a lease, retries and a
  dead-letter state. Missed ticks coalesce: each tick has one logical key.

Delivery protocol (at-least-once at best, never exactly-once):

1. Intent. Before any send, the attempt is committed as 'sending' under the delivery's
   stable delivery_key, which the provider receives as its idempotency key.
2. Send, outside any database transaction.
3. Outcome, committed separately. A lost response, or a crash or failed commit after the
   send, leaves the delivery 'uncertain' (recovery turns a leftover 'sending' into it).
4. Reconcile before retrying. An uncertain delivery is looked up with the provider, or
   re-sent under the same key only when the provider de-duplicates by key. Otherwise it
   is never re-sent, and the alert ends 'uncertain' for review.

Fencing. Every write after the claim locks the alert row and requires its current
claim_token on a live lease. A worker whose claim was taken over gets LeaseLost and
writes nothing; worker names are never trusted for ownership.

Attempts. alerts.attempts counts claims (dispatch rounds) and is incremented when an
alert is claimed, so a crashed round counts once, never twice. alert_deliveries.attempts
counts sends and is incremented when the intent is committed. Both stop at MAX_ATTEMPTS,
and an expired lease backs off like any other retry.

First-party record rule: alerts and attempts store IDs and fixed codes, never provider
values or exception text.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import psycopg

from .discovery import timestamp

TEMPLATE_VERSION = "alerts-v1"
ONSALE_SOON = timedelta(hours=1)
ONSALE_FRESH = timedelta(hours=24)
ANNOUNCE_WINDOW = timedelta(days=7)
MAX_ATTEMPTS = 5
LEASE = timedelta(minutes=5)
TICK = timedelta(minutes=5)
STATUS_TRIGGERS = {"postponed", "cancelled", "rescheduled"}
# Error codes are fixed identifiers. A transport code that is not one is replaced.
ERROR_CODE = re.compile(r"[a-z][a-z0-9_]{1,40}")
OUTCOMES = ("sent", "suppressed", "retry", "failed", "uncertain", "lease_lost")


class TransportError(Exception):
    """The provider did not take the message. A fixed code; never an address or body.

    permanent=True means retrying cannot help (for example an endpoint the provider
    rejects), so the delivery fails now; otherwise it is retried up to MAX_ATTEMPTS.
    """

    def __init__(self, code: str, *, permanent: bool = False):
        super().__init__(code)
        self.code = code
        self.permanent = permanent


class DeliveryUncertain(Exception):
    """The request may have reached the provider but no answer came back (a timeout, a
    dropped connection). The delivery is recorded as uncertain and reconciled."""

    def __init__(self, code: str = "outcome_unknown"):
        super().__init__(code)
        self.code = code


class LeaseLost(Exception):
    """This worker's claim is no longer the current one; it must not write."""


class Transport:
    """Delivery channel interface. The email/push vendor is an open owner decision.

    send receives the delivery's stable idempotency key on every try. A provider that
    de-duplicates sends by that key sets idempotent; one that can look a key up sets
    reconciles and implements reconcile.
    """

    idempotent = False
    reconciles = False

    def send(self, channel: str, endpoint_ref: str, message: dict, idempotency_key: str) -> str:
        raise NotImplementedError

    def reconcile(self, channel: str, endpoint_ref: str, idempotency_key: str) -> str | bool | None:
        """The provider message id if the key was delivered, False if the provider has no
        record of it, or None if it cannot tell."""
        return None


class LogTransport(Transport):
    """Local development transport: records messages in memory, contacts no one.

    It behaves like a provider with idempotency keys: a repeated key returns the first
    message id without recording the message again, and reconcile looks keys up.
    """

    idempotent = True
    reconciles = True

    def __init__(self):
        self.sent: list[tuple[str, str, dict]] = []
        self.ids: dict[str, str] = {}

    def send(self, channel: str, endpoint_ref: str, message: dict, idempotency_key: str) -> str:
        if idempotency_key not in self.ids:
            self.sent.append((channel, endpoint_ref, message))
            self.ids[idempotency_key] = "log-" + uuid4().hex
        return self.ids[idempotency_key]

    def reconcile(self, channel: str, endpoint_ref: str, idempotency_key: str) -> str | bool:
        return self.ids.get(idempotency_key, False)


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


def _backoff(attempts: int) -> timedelta:
    return timedelta(minutes=min(2 ** attempts, 60))


def _code(value: object, default: str) -> str:
    return value if isinstance(value, str) and ERROR_CODE.fullmatch(value) else default


def _one(cursor) -> None:
    """Every write under a held claim touches exactly one row; anything else is a bug."""
    if cursor.rowcount != 1:
        raise RuntimeError("unexpected_row_count")


def claim_due(conn, now: datetime, worker: str, limit: int = 20) -> list[dict]:
    """Lease due alerts under a fresh claim token. SKIP LOCKED lets workers share the queue.

    A claim is one dispatch round and is counted here, once, whether the round finishes
    or the worker crashes.
    """
    with conn.transaction():
        rows = conn.execute(
            """UPDATE alerts SET status = 'sending', lease_owner = %s, lease_expires_at = %s,
                      claim_token = gen_random_uuid(), attempts = attempts + 1
               WHERE alert_id IN (
                 SELECT alert_id FROM alerts
                 WHERE status = 'pending' AND next_attempt_at <= %s AND attempts < %s
                 ORDER BY next_attempt_at, alert_id LIMIT %s FOR UPDATE SKIP LOCKED)
               RETURNING *""", (worker, now + LEASE, now, MAX_ATTEMPTS, limit)).fetchall()
    return sorted(rows, key=lambda row: (row["next_attempt_at"], row["alert_id"]))


def _lock(conn, alert: dict, now: datetime) -> None:
    """Lock the alert row for this claim, or raise LeaseLost: the row must still carry
    this claim's token on an unexpired lease. Call inside the writing transaction."""
    row = conn.execute(
        """SELECT alert_id FROM alerts
           WHERE alert_id = %s AND status = 'sending' AND claim_token = %s
             AND lease_expires_at > %s
           FOR UPDATE""", (alert["alert_id"], alert["claim_token"], now)).fetchone()
    if row is None:
        raise LeaseLost()


def _finish(conn, alert: dict, **fields) -> None:
    """Release the claim with the alert's new state. Only the current claim can."""
    sets = ", ".join(f"{name} = %s" for name in fields)
    cursor = conn.execute(
        f"""UPDATE alerts SET {sets}, lease_owner = NULL, lease_expires_at = NULL,
                   claim_token = NULL
            WHERE alert_id = %s AND status = 'sending' AND claim_token = %s""",  # Constant names.
        (*fields.values(), alert["alert_id"], alert["claim_token"]))
    if cursor.rowcount != 1:
        raise LeaseLost()


def _settle(conn, alert: dict, now: datetime, transport: Transport, *, reason: str | None = None,
            error_code: str | None = None) -> str:
    """End the round from the per-subscription states: retry what is still owed while
    rounds remain, otherwise finish the alert. Returns the outcome."""
    alert_id = alert["alert_id"]
    rows = conn.execute(
        "SELECT status, sent_at FROM alert_deliveries WHERE alert_id = %s", (alert_id,)).fetchall()
    statuses = {row["status"] for row in rows}
    # An uncertain delivery is still owed if a later round can resolve it.
    resolvable = transport.idempotent or transport.reconciles
    if ("pending" in statuses or ("uncertain" in statuses and resolvable)) \
            and alert["attempts"] < MAX_ATTEMPTS:
        _finish(conn, alert, status="pending", last_error_code=error_code,
                next_attempt_at=now + _backoff(alert["attempts"]))
        return "retry"
    if "pending" in statuses:  # Out of rounds: whatever is still owed fails.
        conn.execute(
            """UPDATE alert_deliveries SET status = 'failed', last_error_code = 'attempts_exhausted',
                      updated_at = %s
               WHERE alert_id = %s AND status = 'pending'""", (now, alert_id))
        statuses = statuses - {"pending"} | {"failed"}
        error_code = error_code or "attempts_exhausted"
    sent_at = max((row["sent_at"] for row in rows if row["sent_at"]), default=None)
    if "uncertain" in statuses:
        _finish(conn, alert, status="uncertain", last_error_code="outcome_unknown", sent_at=sent_at)
        return "uncertain"
    if "sent" in statuses:  # Every subscription is terminal and one was delivered.
        _finish(conn, alert, status="sent", last_error_code=None, sent_at=sent_at)
        return "sent"
    if "failed" in statuses or (not rows and error_code):
        _finish(conn, alert, status="failed", last_error_code=error_code or "delivery_failed")
        return "failed"
    _finish(conn, alert, status="suppressed", last_error_code=None,
            suppressed_reason=reason or "no_current_consent")
    return "suppressed"


def _recover(conn, alert: dict, now: datetime, transport: Transport, code: str) -> str:
    """After a crash or a failed round: sends still 'sending' have an unknown outcome and
    become uncertain. Then retry with backoff, or finish once rounds run out. The other
    delivery states are kept as they are."""
    alert_id = alert["alert_id"]
    conn.execute(
        """UPDATE delivery_attempts SET status = 'uncertain', error_code = %s
           WHERE alert_id = %s AND status = 'sending'""", (code, alert_id))
    conn.execute(
        """UPDATE alert_deliveries SET status = 'uncertain', last_error_code = %s, updated_at = %s
           WHERE alert_id = %s AND status = 'sending'""", (code, now, alert_id))
    if alert["attempts"] < MAX_ATTEMPTS:
        _finish(conn, alert, status="pending", last_error_code=code,
                next_attempt_at=now + _backoff(alert["attempts"]))
        return "retry"
    return _settle(conn, alert, now, transport, error_code="attempts_exhausted")


def reclaim_expired_leases(conn, now: datetime, transport: Transport) -> int:
    """Recover alerts whose worker lost its lease (crashed or stalled). See _recover.

    Clearing the claim token here is what fences the old worker out.
    """
    with conn.transaction():
        expired = conn.execute(
            """SELECT * FROM alerts WHERE status = 'sending' AND lease_expires_at < %s
               ORDER BY alert_id FOR UPDATE SKIP LOCKED""", (now,)).fetchall()
        for alert in expired:
            _recover(conn, alert, now, transport, "lease_expired")
    return len(expired)


def _owed(conn, alert_id) -> list[dict]:
    return conn.execute(
        """SELECT d.subscription_id, d.delivery_key, s.channel, s.endpoint_ref
           FROM alert_deliveries d JOIN notification_subscriptions s USING (subscription_id)
           WHERE d.alert_id = %s AND d.status = 'pending'
           ORDER BY d.subscription_id""", (alert_id,)).fetchall()


def _reconcile(transport: Transport, row: dict) -> str | bool | None:
    """Ask the provider what happened to an uncertain delivery. None: still unknown."""
    if not transport.reconciles:
        return None
    try:
        verdict = transport.reconcile(row["channel"], row["endpoint_ref"], str(row["delivery_key"]))
    except Exception:  # noqa: BLE001 - an unanswered lookup leaves the outcome unknown.
        return None
    return verdict if verdict is False or (isinstance(verdict, str) and verdict) else None


def _apply_reconciliation(conn, alert_id, subscription_id, verdict, transport: Transport,
                          now: datetime) -> None:
    latest = """attempt_no = (SELECT max(attempt_no) FROM delivery_attempts
                              WHERE alert_id = %s AND subscription_id = %s AND status = 'uncertain')"""
    if isinstance(verdict, str):  # It was delivered: record that; never send it again.
        conn.execute(
            f"""UPDATE delivery_attempts SET status = 'sent', provider_message_id = %s, error_code = NULL
                WHERE alert_id = %s AND subscription_id = %s AND status = 'uncertain' AND {latest}""",
            (verdict, alert_id, subscription_id, alert_id, subscription_id))
        _one(conn.execute(
            """UPDATE alert_deliveries SET status = 'sent', sent_at = %s, last_error_code = NULL,
                      updated_at = %s
               WHERE alert_id = %s AND subscription_id = %s AND status = 'uncertain'""",
            (now, now, alert_id, subscription_id)))
    elif verdict is False or transport.idempotent:
        # Not delivered, or a re-send under the same key cannot deliver twice: owed again.
        if verdict is False:
            conn.execute(
                f"""UPDATE delivery_attempts SET status = 'failed', error_code = 'not_delivered'
                    WHERE alert_id = %s AND subscription_id = %s AND status = 'uncertain'
                      AND {latest}""", (alert_id, subscription_id, alert_id, subscription_id))
        _one(conn.execute(
            """UPDATE alert_deliveries
               SET status = CASE WHEN attempts < %s THEN 'pending' ELSE 'failed' END, updated_at = %s
               WHERE alert_id = %s AND subscription_id = %s AND status = 'uncertain'""",
            (MAX_ATTEMPTS, now, alert_id, subscription_id)))
    # Otherwise it stays uncertain and is never re-sent.


def _send(transport: Transport, sub: dict, message: dict) -> tuple[str, str | None, str | None, bool]:
    """(status, provider_message_id, error_code, permanent) of one send. Never raises."""
    try:
        provider_id = transport.send(sub["channel"], sub["endpoint_ref"], message,
                                     str(sub["delivery_key"]))
    except TransportError as exc:
        return "failed", None, _code(exc.code, "transport_error"), exc.permanent
    except DeliveryUncertain as exc:
        return "uncertain", None, _code(exc.code, "outcome_unknown"), False
    except Exception:  # noqa: BLE001 - it may have reached the provider; reconcile, never assume.
        return "uncertain", None, "transport_exception", False
    if not isinstance(provider_id, str) or not provider_id:
        return "uncertain", None, "missing_message_id", False
    return "sent", provider_id, None, False


Clock = Callable[[], datetime]
# The current permission-filtered projection of one event at a time, or None when it is
# no longer displayable. Called immediately before every send.
EventLookup = Callable[[str, datetime], dict | None]


def _reason(alert: dict, event: dict | None, at: datetime) -> str | None:
    """Why this alert may not be sent at time at, from the current projection."""
    return ("expired" if at >= alert["expires_at"]
            else "not_displayable" if event is None
            else "stale_source" if event["stale"] else None)


def _consented(conn, alert: dict, subscription_id, at: datetime) -> bool:
    """That subscription's consent is current at time at, and no deletion is requested.

    Locks the subscription row (FOR SHARE) until the intent commits, so a revocation
    either lands first and is seen here, or waits for the intent and is seen next time.
    """
    return conn.execute(
        """SELECT 1 FROM notification_subscriptions s
           JOIN user_profiles p ON p.user_id = s.user_id
           WHERE s.subscription_id = %s AND s.user_id = %s AND s.revoked_at IS NULL
             AND s.consent_at <= %s AND p.deletion_requested_at IS NULL
           FOR SHARE OF s""", (subscription_id, alert["user_id"], at)).fetchone() is not None


def _dispatch_one(conn, transport: Transport, alert: dict, clock: Clock,
                  lookup: EventLookup) -> str:
    """Deliver one claimed alert to the subscriptions still owed it; returns the outcome.

    Authorization is never carried over from the tick: immediately before each send the
    worker reads a fresh clock, the event's current permission-filtered projection, and
    that subscription's current consent. A change after projection or between two
    subscriptions suppresses the sends that follow it.
    """
    alert_id, event_id = alert["alert_id"], str(alert["event_id"])
    now = clock()
    reason = _reason(alert, lookup(event_id, now), now)
    # 1. Reconcile before anything is re-sent. The provider lookup is external I/O, so it
    #    runs between transactions, never inside one.
    with conn.transaction():
        _lock(conn, alert, now)
        uncertain = conn.execute(
            """SELECT d.subscription_id, d.delivery_key, s.channel, s.endpoint_ref
               FROM alert_deliveries d JOIN notification_subscriptions s USING (subscription_id)
               WHERE d.alert_id = %s AND d.status = 'uncertain'""", (alert_id,)).fetchall()
    verdicts = {row["subscription_id"]: _reconcile(transport, row) for row in uncertain}
    # 2. Apply the verdicts, re-check consent, and decide who is owed this round.
    now = clock()
    with conn.transaction():
        _lock(conn, alert, now)
        for subscription_id, verdict in verdicts.items():
            _apply_reconciliation(conn, alert_id, subscription_id, verdict, transport, now)
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
        # An uncertain one is evidence and stays as it is.
        conn.execute(
            """UPDATE alert_deliveries SET status = 'suppressed', suppressed_reason = %s,
                      updated_at = %s
               WHERE alert_id = %s AND status = 'pending' AND NOT subscription_id = ANY(%s::uuid[])""",
            (reason or "no_current_consent", now, alert_id, current))
        owed = _owed(conn, alert_id)
    # 3. One delivery at a time: re-authorize and commit the intent, send outside any
    #    transaction, then commit the outcome. A crash or failed commit in between leaves
    #    a 'sending' row that recovery turns into 'uncertain'.
    for sub in owed:
        now = clock()
        event = lookup(event_id, now)
        reason = _reason(alert, event, now)
        message = None
        if reason is None:
            try:
                message = render(alert, event)
            except Exception:  # noqa: BLE001 - permanent: the same projection renders the same way.
                with conn.transaction():
                    _lock(conn, alert, now)
                    conn.execute(
                        """UPDATE alert_deliveries SET status = 'failed',
                                  last_error_code = 'render_error', updated_at = %s
                           WHERE alert_id = %s AND status = 'pending'""", (now, alert_id))
                    return _settle(conn, alert, now, transport, error_code="render_error")
        with conn.transaction():
            _lock(conn, alert, now)
            if reason is None and not _consented(conn, alert, sub["subscription_id"], now):
                reason = "no_current_consent"
            if reason is not None:  # Not authorized now: this delivery is no longer owed.
                _one(conn.execute(
                    """UPDATE alert_deliveries SET status = 'suppressed', suppressed_reason = %s,
                              updated_at = %s
                       WHERE alert_id = %s AND subscription_id = %s AND status = 'pending'""",
                    (reason, now, alert_id, sub["subscription_id"])))
                continue
            row = conn.execute(
                """UPDATE alert_deliveries SET status = 'sending', attempts = attempts + 1,
                          updated_at = %s
                   WHERE alert_id = %s AND subscription_id = %s AND status = 'pending'
                   RETURNING attempts""", (now, alert_id, sub["subscription_id"])).fetchone()
            if row is None:
                raise RuntimeError("unexpected_row_count")
            attempt_no = row["attempts"]
            conn.execute(
                """INSERT INTO delivery_attempts(alert_id, subscription_id, attempt_no, status,
                                                 attempted_at)
                   VALUES (%s, %s, %s, 'sending', %s)""",
                (alert_id, sub["subscription_id"], attempt_no, now))
        status, provider_id, code, permanent = _send(transport, sub, message)
        now = clock()
        with conn.transaction():
            _lock(conn, alert, now)
            _one(conn.execute(
                """UPDATE delivery_attempts SET status = %s, provider_message_id = %s, error_code = %s
                   WHERE alert_id = %s AND subscription_id = %s AND attempt_no = %s
                     AND status = 'sending'""",
                (status, provider_id, code, alert_id, sub["subscription_id"], attempt_no)))
            # Terminal failure: a permanent error, or MAX_ATTEMPTS sends to this subscription.
            if status == "failed" and not permanent and attempt_no < MAX_ATTEMPTS:
                status = "pending"
            _one(conn.execute(
                """UPDATE alert_deliveries SET status = %s, last_error_code = %s, sent_at = %s,
                          updated_at = %s
                   WHERE alert_id = %s AND subscription_id = %s AND status = 'sending'""",
                (status, code, now if status == "sent" else None, now,
                 alert_id, sub["subscription_id"])))
    now = clock()
    with conn.transaction():
        _lock(conn, alert, now)
        return _settle(conn, alert, now, transport, reason=reason)


def _connection_lost(conn, exc: Exception) -> bool:
    return (isinstance(exc, (psycopg.OperationalError, psycopg.InterfaceError))
            or conn.closed or bool(getattr(conn, "broken", False)))


def feed_lookup(feed: dict) -> EventLookup:
    """An EventLookup over one fixed projection. For tests; a live worker re-projects."""
    events = {e["event_id"]: e for e in feed["events"]}
    return lambda event_id, at: events.get(event_id)


def store_lookup(store) -> EventLookup:
    """Re-project the store's permission-filtered feed at the time of each send."""
    def lookup(event_id: str, at: datetime) -> dict | None:
        return next((e for e in store.feed(at)["events"] if e["event_id"] == event_id), None)
    return lookup


def dispatch_due(conn, transport: Transport, feed: dict | None, now: datetime, worker: str,
                 limit: int = 20, *, clock: Clock | None = None,
                 lookup: EventLookup | None = None) -> dict:
    """Send due alerts, isolating each one.

    now is when the round starts (reclaiming and claiming). clock gives the time for each
    later step and lookup the event's current projection; both are read again before
    every send. Without them the round uses now and the given feed throughout, which is
    only right for a test with a frozen projection.

    Delivery state is kept per subscription (alert_deliveries). A retry sends only to
    subscriptions still owed, so one channel failing never re-sends another's message.
    The alert finishes once every subscription is sent, failed (a permanent error or
    MAX_ATTEMPTS sends), suppressed (consent withdrawn, or the alert expired or lost
    display permission) or left uncertain.

    An alert that raises (a database error on one row, a bug) has its transaction rolled
    back and is then recovered on its own, with a fixed code and backoff; the alerts after
    it still run. A lost database connection is not isolated: it ends the batch with the
    error, and the leases it held expire into recovery.
    """
    clock = clock or (lambda: now)
    lookup = lookup or feed_lookup(feed)
    reclaim_expired_leases(conn, now, transport)
    counts = dict.fromkeys(OUTCOMES, 0)
    for alert in claim_due(conn, now, worker, limit):
        try:
            outcome = _dispatch_one(conn, transport, alert, clock, lookup)
        except LeaseLost:
            outcome = "lease_lost"
        except Exception as exc:
            if _connection_lost(conn, exc):
                raise
            # The failing transaction has rolled back; record recovery in a fresh one.
            try:
                at = clock()
                with conn.transaction():
                    _lock(conn, alert, at)
                    outcome = _recover(conn, alert, at, transport, "dispatch_error")
            except LeaseLost:
                outcome = "lease_lost"
        counts[outcome] += 1
    return counts


def _close_job(conn, job: dict, now: datetime, **fields) -> bool:
    """Write a job's result. Only the claim that is still current can: the same attempt
    generation and lease owner, still running, on an unexpired lease."""
    sets = ", ".join(f"{name} = %s" for name in fields)
    with conn.transaction():
        return conn.execute(
            f"""UPDATE job_runs SET {sets}, lease_owner = NULL, lease_expires_at = NULL,
                       finished_at = %s
                WHERE job_run_id = %s AND attempt = %s AND lease_owner = %s
                  AND status = 'running' AND lease_expires_at > %s""",  # Constant names.
            (*fields.values(), now, job["job_run_id"], job["attempt"], job["lease_owner"],
             now)).rowcount == 1


def run_job(conn, job_type: str, logical_key: str, work: Callable[[], dict], now: datetime,
            worker: str, max_attempts: int = MAX_ATTEMPTS) -> dict | None:
    """Run work once per (job_type, logical_key). Returns None if not claimable now.

    Claimable: new; failed and due for retry; or running with an expired lease, after a
    backoff, while attempts remain. A crashed run already at the cap is dead-lettered
    instead. Succeeded and dead jobs are never re-run.

    Each claim is a new attempt generation. Only the current generation on a live lease
    can record success or failure; an older one gets {"status": "lease_lost"} and writes
    nothing. Errors keep a fixed code (the exception type), never a message that could
    carry provider or user data.
    """
    with conn.transaction():
        conn.execute(
            """UPDATE job_runs SET status = 'dead', last_error_code = 'lease_expired',
                      lease_owner = NULL, lease_expires_at = NULL, finished_at = %s
               WHERE job_type = %s AND logical_key = %s AND status = 'running'
                 AND lease_expires_at < %s AND attempt >= max_attempts""",
            (now, job_type, logical_key, now))
        job = conn.execute(
            """INSERT INTO job_runs(job_type, logical_key, status, attempt, max_attempts,
                                    lease_owner, lease_expires_at, started_at, run_after)
               VALUES (%s, %s, 'running', 1, %s, %s, %s, %s, %s)
               ON CONFLICT (job_type, logical_key) DO UPDATE
                 SET status = 'running', attempt = job_runs.attempt + 1,
                     lease_owner = excluded.lease_owner, lease_expires_at = excluded.lease_expires_at,
                     started_at = excluded.started_at
                 WHERE job_runs.attempt < job_runs.max_attempts AND (
                   (job_runs.status = 'failed' AND job_runs.run_after <= excluded.run_after)
                   OR (job_runs.status = 'running' AND job_runs.lease_expires_at
                       + make_interval(mins => least(power(2, job_runs.attempt), 60)::int)
                       <= excluded.run_after))
               RETURNING *""",
            (job_type, logical_key, max_attempts, worker, now + LEASE, now, now)).fetchone()
    if job is None:
        return None
    try:
        result = work()
    except Exception as exc:  # noqa: BLE001 - recorded as a fixed code, then retried.
        # A lost connection fails again here and propagates: never recorded as success.
        dead = job["attempt"] >= job["max_attempts"]
        status = "dead" if dead else "failed"
        if not _close_job(conn, job, now, status=status, last_error_code=type(exc).__name__,
                          run_after=now + _backoff(job["attempt"])):
            return {"status": "lease_lost"}
        return {"status": status, "error_code": type(exc).__name__}
    if not _close_job(conn, job, now, status="succeeded", last_error_code=None):
        return {"status": "lease_lost"}
    return {"status": "succeeded", **result}


def tick_key(now: datetime) -> str:
    floored = now.astimezone(UTC).replace(second=0, microsecond=0)
    floored -= timedelta(minutes=floored.minute % int(TICK.total_seconds() // 60))
    return floored.strftime("%Y-%m-%dT%H:%MZ")


def tick(store, transport: Transport, now: datetime, worker: str,
         clock: Clock | None = None) -> dict:
    """One scheduler tick: plan alerts, then dispatch. Each is a durable job.

    Planning uses the tick's projection. Dispatch re-reads the clock (clock, default the
    tick time) and re-projects the store before every send.
    """
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
                             lambda: dispatch_due(conn, transport, feed, now, worker, clock=clock,
                                                  lookup=store_lookup(store)), now, worker)
    return {"tick": key, "plan": planned, "dispatch": dispatched}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one local alert worker tick.")
    parser.add_argument("--once", action="store_true", required=True)
    parser.parse_args()
    from .discovery_postgres import PostgresStore

    dsn = os.environ.get("SWEET_SEATS_LOCAL_DATABASE_URL")
    if not dsn:
        parser.exit(1, "SWEET_SEATS_LOCAL_DATABASE_URL is required; no hosted database is used.\n")
    result = tick(PostgresStore(dsn), LogTransport(), datetime.now(UTC), "local-" + uuid4().hex[:8],
                  clock=lambda: datetime.now(UTC))
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
