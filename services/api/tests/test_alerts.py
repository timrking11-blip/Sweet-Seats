"""Durable jobs and the alert outbox against disposable PostgreSQL."""

import os
from datetime import timedelta
from uuid import uuid4

import pytest

from app.alerts import (
    LEASE,
    MAX_ATTEMPTS,
    LogTransport,
    Transport,
    TransportError,
    claim_due,
    dispatch_due,
    enqueue_alerts,
    plan_alerts,
    run_job,
    tick,
)
from app.discovery import timestamp

NOW = timestamp("2026-10-18T07:00:00Z")
pytestmark = pytest.mark.skipif(not os.environ.get("SWEET_SEATS_TEST_DATABASE_URL"),
                                reason="requires disposable local PostgreSQL DSN")


class FailingTransport(Transport):
    def send(self, channel, endpoint_ref, message):
        raise TransportError("provider_unavailable")


def connect(store):
    conn = store._connect()
    conn.autocommit = True
    return conn


def add_user(conn, artist_ids, *, consent=True) -> str:
    user = str(uuid4())
    conn.execute("INSERT INTO auth.users(id) VALUES (%s)", (user,))
    conn.execute("INSERT INTO user_profiles(user_id, consent_version) VALUES (%s, 'c1')", (user,))
    for artist in artist_ids:
        conn.execute("INSERT INTO artist_follows(user_id, artist_id) VALUES (%s, %s)", (user, artist))
    if consent:
        conn.execute(
            """INSERT INTO notification_subscriptions(user_id, channel, endpoint_ref,
                   consent_version, consent_at) VALUES (%s, 'email', %s, 'c1', %s)""",
            (user, "secret://" + user, NOW - timedelta(days=1)))
    return user


def seeded(pg_store, fixture=None):
    store, default = pg_store
    store.seed(fixture or default, NOW)
    feed = store.feed(NOW)
    headliners = {p["artist_id"] for e in feed["events"] for p in e["performers"]
                  if p["role"] == "headliner"}
    return store, feed, sorted(headliners)


def alerts(conn):
    return conn.execute("SELECT * FROM alerts ORDER BY dedupe_key").fetchall()


def test_tick_plans_sends_once_and_coalesces_reruns(pg_store):
    store, _, artists = seeded(pg_store)
    transport = LogTransport()
    with connect(store) as conn:
        add_user(conn, artists[:1])
    first = tick(store, transport, NOW, "w1")
    assert first["plan"]["created"] >= 1 and first["dispatch"]["sent"] == first["plan"]["created"]
    sent = len(transport.sent)
    assert sent == first["plan"]["created"]
    # Same tick again: both jobs already succeeded, so nothing re-runs.
    assert tick(store, transport, NOW + timedelta(minutes=1), "w2") == {
        "tick": first["tick"], "plan": None, "dispatch": None}
    # Next tick re-plans, but dedupe keys stop a second alert for the same event.
    later = tick(store, transport, NOW + timedelta(minutes=5), "w2")
    assert later["plan"]["created"] == 0 and len(transport.sent) == sent
    with connect(store) as conn:
        rows = conn.execute("SELECT status, provider_message_id FROM delivery_attempts").fetchall()
        assert rows and all(r["status"] == "sent" and r["provider_message_id"] for r in rows)
    # The message carries display text rendered at send time; the outbox row does not.
    assert {"title", "venue", "headline"} <= set(transport.sent[0][2])


def test_revoked_consent_suppresses_at_send_time(pg_store):
    store, feed, artists = seeded(pg_store)
    transport = LogTransport()
    with connect(store) as conn:
        user = add_user(conn, artists[:1])
        enqueue_alerts(conn, plan_alerts(feed, [(user, artists[0])], NOW), NOW)
        conn.execute("UPDATE notification_subscriptions SET revoked_at = %s", (NOW,))
        assert dispatch_due(conn, transport, feed, NOW, "w1")["suppressed"] >= 1
        assert {a["suppressed_reason"] for a in alerts(conn)} == {"no_current_consent"}
    assert transport.sent == []


def test_withdrawn_display_permission_suppresses(pg_store):
    store, feed, artists = seeded(pg_store)
    with connect(store) as conn:
        user = add_user(conn, artists[:1])
        enqueue_alerts(conn, plan_alerts(feed, [(user, artists[0])], NOW), NOW)
        conn.execute("UPDATE source_permissions SET display_allowed = false")
    current = store.feed(NOW)  # The worker re-projects; the event is no longer displayable.
    with connect(store) as conn:
        dispatch_due(conn, LogTransport(), current, NOW, "w1")
        assert {a["suppressed_reason"] for a in alerts(conn)} == {"not_displayable"}


def test_transport_failures_back_off_then_stop_at_the_cap(pg_store):
    store, feed, artists = seeded(pg_store)
    with connect(store) as conn:
        user = add_user(conn, artists[:1])
        enqueue_alerts(conn, plan_alerts(feed, [(user, artists[0])], NOW)[:1], NOW)
        at = NOW
        for _ in range(MAX_ATTEMPTS):
            dispatch_due(conn, FailingTransport(), feed, at, "w1")
            (alert,) = alerts(conn)
            if alert["status"] == "pending":
                assert alert["next_attempt_at"] > at  # Backed off, not retried at once.
                at = alert["next_attempt_at"]
        (alert,) = alerts(conn)
        assert (alert["status"], alert["attempts"]) == ("failed", MAX_ATTEMPTS)
        codes = conn.execute("SELECT DISTINCT error_code FROM delivery_attempts").fetchall()
        assert [c["error_code"] for c in codes] == ["provider_unavailable"]


def test_crashed_send_is_reclaimed_after_its_lease(pg_store):
    store, feed, artists = seeded(pg_store)
    transport = LogTransport()
    with connect(store) as conn:
        user = add_user(conn, artists[:1])
        enqueue_alerts(conn, plan_alerts(feed, [(user, artists[0])], NOW)[:1], NOW)
        assert len(claim_due(conn, NOW, "crashed-worker")) == 1  # ...then the worker dies.
        assert dispatch_due(conn, transport, feed, NOW + timedelta(seconds=1), "w2")["sent"] == 0
        later = NOW + LEASE + timedelta(seconds=1)
        assert dispatch_due(conn, transport, feed, later, "w2")["sent"] == 1
        (alert,) = alerts(conn)
        assert alert["attempts"] == 2  # The lost attempt counts; delivery is at-least-once.


def test_two_workers_never_claim_the_same_alert(pg_store):
    store, feed, artists = seeded(pg_store)
    with connect(store) as conn:
        user = add_user(conn, artists)  # A fresh announcement and a cancellation.
        enqueue_alerts(conn, plan_alerts(feed, [(user, a) for a in artists], NOW), NOW)
        total = len(alerts(conn))
        assert total >= 2
    with connect(store) as a, connect(store) as b:
        first = claim_due(a, NOW, "a", limit=1)
        second = claim_due(b, NOW, "b", limit=total)
    claimed = [r["alert_id"] for r in first + second]
    assert len(claimed) == len(set(claimed)) == total


def test_onsale_soon_then_onsale_open(pg_store):
    store, fixture = pg_store
    # The shared, fresh show: both sources state the same on-sale time. (On-sale time is
    # not a conflict fact, and the other single-source show is already stale.)
    for batch in fixture["batches"]:
        for record in batch["records"]:
            if record["vendor_event_id"] in {"artist-101", "venue-202"}:
                record["onsale_at"] = "2026-10-18T07:30:00Z"
    store.seed(fixture, NOW)
    feed = store.feed(NOW)
    event = next(e for e in feed["events"] if e["onsale_at"])
    artist = event["performers"][0]["artist_id"]
    user = str(uuid4())
    soon = {i.trigger_type for i in plan_alerts(feed, [(user, artist)], NOW)
            if i.event_id == event["event_id"]}
    assert "onsale_soon" in soon and "onsale_open" not in soon
    after = NOW + timedelta(hours=1)
    opened = {i.trigger_type for i in plan_alerts(store.feed(after), [(user, artist)], after)
              if i.event_id == event["event_id"]}
    assert "onsale_open" in opened and "onsale_soon" not in opened


def test_stale_events_never_alert(pg_store):
    store, _, artists = seeded(pg_store)
    later = NOW + timedelta(days=2)
    assert plan_alerts(store.feed(later), [(str(uuid4()), a) for a in artists], later) == []


def test_jobs_retry_then_dead_letter_and_never_rerun_success(pg_store):
    store, _ = pg_store
    with connect(store) as conn:
        def boom():
            raise ValueError("payload text that must not be stored")

        assert run_job(conn, "collect", "k1", boom, NOW, "w", max_attempts=2)["status"] == "failed"
        assert run_job(conn, "collect", "k1", boom, NOW, "w", max_attempts=2) is None  # Backing off.
        retry_at = NOW + timedelta(hours=1)
        assert run_job(conn, "collect", "k1", boom, retry_at, "w", max_attempts=2)["status"] == "dead"
        assert run_job(conn, "collect", "k1", dict, retry_at + timedelta(hours=2), "w") is None
        (job,) = conn.execute("SELECT * FROM job_runs").fetchall()
        assert (job["status"], job["attempt"], job["last_error_code"]) == ("dead", 2, "ValueError")
        assert run_job(conn, "collect", "k2", lambda: {"n": 1}, NOW, "w")["status"] == "succeeded"
        assert run_job(conn, "collect", "k2", lambda: {"n": 2}, NOW + timedelta(days=1), "w") is None
