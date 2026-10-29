"""Durable jobs and the alert outbox against disposable PostgreSQL."""

import copy
import os
from datetime import timedelta
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from app import alerts as alerts_module
from app.alerts import (
    LEASE,
    MAX_ATTEMPTS,
    LogTransport,
    Transport,
    TransportError,
    claim_due,
    dispatch_due,
    enqueue_alerts,
    feed_lookup,
    plan_alerts,
    run_job,
    store_lookup,
    tick,
)
from app.discovery import timestamp

NOW = timestamp("2026-10-18T07:00:00Z")
pytestmark = pytest.mark.skipif(not os.environ.get("SWEET_SEATS_TEST_DATABASE_URL"),
                                reason="requires disposable local PostgreSQL DSN")


class FailingTransport(Transport):
    def send(self, channel, endpoint_ref, message, idempotency_key):
        raise TransportError("provider_unavailable")


class ChannelTransport(LogTransport):
    """Fails every send to the given channels and records the rest."""

    def __init__(self, failing):
        super().__init__()
        self.failing = set(failing)

    def send(self, channel, endpoint_ref, message, idempotency_key):
        if channel in self.failing:
            raise TransportError("provider_unavailable")
        return super().send(channel, endpoint_ref, message, idempotency_key)


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


def add_subscription(conn, user, channel) -> None:
    conn.execute(
        """INSERT INTO notification_subscriptions(user_id, channel, endpoint_ref,
               consent_version, consent_at) VALUES (%s, %s, %s, 'c1', %s)""",
        (user, channel, f"secret://{channel}/{user}", NOW - timedelta(days=1)))


def two_channel_alert(pg_store):
    """One due alert for a user subscribed by email and web push."""
    store, feed, artists = seeded(pg_store)
    conn = connect(store)
    user = add_user(conn, artists[:1])
    add_subscription(conn, user, "web_push")
    enqueue_alerts(conn, plan_alerts(feed, [(user, artists[0])], NOW)[:1], NOW)
    return conn, feed


def deliveries(conn) -> dict:
    return {r["channel"]: r for r in conn.execute(
        """SELECT s.channel, d.* FROM alert_deliveries d
           JOIN notification_subscriptions s USING (subscription_id)""")}


def sent_channels(transport) -> list[str]:
    return [channel for channel, _, _ in transport.sent]


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


def test_partial_delivery_retries_only_the_failed_subscription(pg_store):
    conn, feed = two_channel_alert(pg_store)
    with conn:
        flaky = ChannelTransport({"web_push"})
        assert dispatch_due(conn, flaky, feed, NOW, "w1") == {
            "sent": 0, "suppressed": 0, "retry": 1, "failed": 0, "uncertain": 0, "lease_lost": 0}
        (alert,) = alerts(conn)
        # Email was delivered but push is still owed, so the alert is not sent yet.
        assert (alert["status"], alert["sent_at"]) == ("pending", None)
        assert {c: d["status"] for c, d in deliveries(conn).items()} == {
            "email": "sent", "web_push": "pending"}
        assert sent_channels(flaky) == ["email"]

        # Push recovers: the retry goes to push only, never to email again.
        healthy = LogTransport()
        assert dispatch_due(conn, healthy, feed, alert["next_attempt_at"], "w1")["sent"] == 1
        assert sent_channels(healthy) == ["web_push"]
        (alert,) = alerts(conn)
        assert (alert["status"], alert["attempts"]) == ("sent", 2)
        assert {d["status"] for d in deliveries(conn).values()} == {"sent"}
        # A finished alert is never claimed again.
        later = alert["next_attempt_at"] + timedelta(hours=1)
        assert dispatch_due(conn, healthy, feed, later, "w1") == {
            "sent": 0, "suppressed": 0, "retry": 0, "failed": 0, "uncertain": 0, "lease_lost": 0}
        assert sent_channels(flaky) + sent_channels(healthy) == ["email", "web_push"]
        rows = conn.execute(
            """SELECT s.channel, a.attempt_no, a.status FROM delivery_attempts a
               JOIN notification_subscriptions s USING (subscription_id)
               ORDER BY s.channel, a.attempt_no""").fetchall()
        assert [(r["channel"], r["attempt_no"], r["status"]) for r in rows] == [
            ("email", 1, "sent"), ("web_push", 1, "failed"), ("web_push", 2, "sent")]


def test_alert_finishes_once_the_failing_subscription_hits_the_cap(pg_store):
    conn, feed = two_channel_alert(pg_store)
    with conn:
        flaky = ChannelTransport({"web_push"})
        at = NOW
        for _ in range(MAX_ATTEMPTS):
            dispatch_due(conn, flaky, feed, at, "w1")
            (alert,) = alerts(conn)
            at = alert["next_attempt_at"]
        # Push failed terminally; email was delivered exactly once. Nothing is owed.
        assert (alert["status"], alert["attempts"]) == ("sent", MAX_ATTEMPTS)
        state = deliveries(conn)
        assert (state["email"]["status"], state["email"]["attempts"]) == ("sent", 1)
        assert (state["web_push"]["status"], state["web_push"]["attempts"],
                state["web_push"]["last_error_code"]) == ("failed", MAX_ATTEMPTS, "provider_unavailable")
        assert sent_channels(flaky) == ["email"]
        assert dispatch_due(conn, flaky, feed, at + timedelta(hours=1), "w1")["retry"] == 0


def test_consent_withdrawn_before_a_retry_ends_that_delivery(pg_store):
    conn, feed = two_channel_alert(pg_store)
    with conn:
        flaky = ChannelTransport({"web_push"})
        dispatch_due(conn, flaky, feed, NOW, "w1")
        conn.execute("UPDATE notification_subscriptions SET revoked_at = %s WHERE channel = 'web_push'",
                     (NOW,))
        (alert,) = alerts(conn)
        assert dispatch_due(conn, flaky, feed, alert["next_attempt_at"], "w1")["sent"] == 1
        push = deliveries(conn)["web_push"]
        assert (push["status"], push["suppressed_reason"]) == ("suppressed", "no_current_consent")
        assert sent_channels(flaky) == ["email"]


def test_crashed_send_is_reclaimed_after_its_lease(pg_store):
    store, feed, artists = seeded(pg_store)
    transport = LogTransport()
    with connect(store) as conn:
        user = add_user(conn, artists[:1])
        enqueue_alerts(conn, plan_alerts(feed, [(user, artists[0])], NOW)[:1], NOW)
        assert len(claim_due(conn, NOW, "crashed-worker")) == 1  # ...then the worker dies.
        assert dispatch_due(conn, transport, feed, NOW + timedelta(seconds=1), "w2")["sent"] == 0
        later = NOW + LEASE + timedelta(seconds=1)
        # The expired lease backs off like any retry before the alert is claimed again.
        assert dispatch_due(conn, transport, feed, later, "w2")["sent"] == 0
        (alert,) = alerts(conn)
        assert (alert["status"], alert["last_error_code"]) == ("pending", "lease_expired")
        assert dispatch_due(conn, transport, feed, alert["next_attempt_at"], "w2")["sent"] == 1
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


# --- Reliability regressions (PR #23 review) ---------------------------------------


class BlindTransport(Transport):
    """A provider without idempotency keys or lookups: an unanswered send stays unknown."""

    def __init__(self, on_send=None):
        self.keys: list[str] = []
        self.on_send = on_send

    def send(self, channel, endpoint_ref, message, idempotency_key):
        self.keys.append(idempotency_key)  # The provider has accepted the message...
        if self.on_send:
            self.on_send()  # ...and then something goes wrong on our side.
        return "blind-" + idempotency_key


class LookupProvider(LogTransport):
    """Answers lookups but does not de-duplicate sends, so only reconciling is safe."""

    idempotent = False


def queue_one(store, feed, artists):
    with connect(store) as setup:
        user = add_user(setup, artists[:1])
        enqueue_alerts(setup, plan_alerts(feed, [(user, artists[0])], NOW)[:1], NOW)


def one_alert_per_event(pg_store):
    """A user following every headliner, with one queued alert for each of two events.
    The first alert (poison) is ahead of the second (healthy) in the queue."""
    store, feed, artists = seeded(pg_store)
    conn = connect(store)
    user = add_user(conn, artists)
    by_event = {}
    for intent in plan_alerts(feed, [(user, a) for a in artists], NOW):
        by_event.setdefault(intent.event_id, intent)
    assert len(by_event) >= 2
    enqueue_alerts(conn, list(by_event.values())[:2], NOW)
    poison, healthy = alerts(conn)
    conn.execute("UPDATE alerts SET next_attempt_at = %s WHERE alert_id = %s",
                 (NOW - timedelta(minutes=1), poison["alert_id"]))
    return conn, feed, poison, healthy


def by_id(conn) -> dict:
    return {a["alert_id"]: a for a in alerts(conn)}


def other_connection(conn):
    another = psycopg.connect(conn.info.dsn, row_factory=dict_row)
    another.autocommit = True
    return another


def test_a_malformed_alert_does_not_block_a_healthy_one(pg_store):
    conn, feed, poison, healthy = one_alert_per_event(pg_store)
    with conn:
        broken = copy.deepcopy(feed)
        next(e for e in broken["events"]
             if e["event_id"] == str(poison["event_id"]))["venue"] = None
        transport = LogTransport()
        counts = dispatch_due(conn, transport, broken, NOW, "w1")
        assert (counts["failed"], counts["sent"]) == (1, 1)
        state = by_id(conn)
        assert (state[poison["alert_id"]]["status"],
                state[poison["alert_id"]]["last_error_code"]) == ("failed", "render_error")
        assert state[healthy["alert_id"]]["status"] == "sent"
        assert [m["event_id"] for _, _, m in transport.sent] == [str(healthy["event_id"])]


def test_a_failing_alert_rolls_back_then_recovers_without_stopping_the_batch(
        pg_store, monkeypatch):
    conn, feed, poison, healthy = one_alert_per_event(pg_store)
    with conn:
        owed = alerts_module._owed

        def flaky_owed(c, alert_id):
            if alert_id == poison["alert_id"]:
                raise psycopg.errors.DataError("row-level failure")
            return owed(c, alert_id)

        monkeypatch.setattr(alerts_module, "_owed", flaky_owed)
        counts = dispatch_due(conn, LogTransport(), feed, NOW, "w1")
        assert (counts["retry"], counts["sent"]) == (1, 1)
        state = by_id(conn)
        bad = state[poison["alert_id"]]
        assert (bad["status"], bad["last_error_code"], bad["claim_token"]) == (
            "pending", "dispatch_error", None)
        assert bad["next_attempt_at"] > NOW  # Backed off, with a fixed code.
        # The delivery rows written before the failure were rolled back with it.
        assert conn.execute("SELECT count(*) AS n FROM alert_deliveries WHERE alert_id = %s",
                            (poison["alert_id"],)).fetchone()["n"] == 0
        assert state[healthy["alert_id"]]["status"] == "sent"


def test_an_unexpected_transport_exception_is_uncertain_and_isolated(pg_store):
    conn, feed, poison, healthy = one_alert_per_event(pg_store)
    with conn:
        class Exploding(LogTransport):
            def send(self, channel, endpoint_ref, message, idempotency_key):
                if message["alert_id"] == str(poison["alert_id"]):
                    raise RuntimeError("client bug after the request may have left")
                return super().send(channel, endpoint_ref, message, idempotency_key)

        counts = dispatch_due(conn, Exploding(), feed, NOW, "w1")
        assert (counts["retry"], counts["sent"]) == (1, 1)
        (state,) = conn.execute("SELECT * FROM alert_deliveries WHERE alert_id = %s",
                                (poison["alert_id"],)).fetchall()
        assert (state["status"], state["last_error_code"]) == ("uncertain", "transport_exception")
        assert by_id(conn)[healthy["alert_id"]]["status"] == "sent"


def test_permanent_transport_errors_fail_without_retrying(pg_store):
    store, feed, artists = seeded(pg_store)
    queue_one(store, feed, artists)

    class Rejecting(Transport):
        def send(self, channel, endpoint_ref, message, idempotency_key):
            raise TransportError("Endpoint <x@y> rejected!", permanent=True)

    with connect(store) as conn:
        assert dispatch_due(conn, Rejecting(), feed, NOW, "w1")["failed"] == 1
        (alert,) = alerts(conn)
        assert (alert["status"], alert["attempts"]) == ("failed", 1)
        # A code that is not a fixed identifier is never stored as given.
        assert deliveries(conn)["email"]["last_error_code"] == "transport_error"


def test_repeated_crashes_reach_a_terminal_state(pg_store):
    store, feed, artists = seeded(pg_store)
    queue_one(store, feed, artists)
    transport = LogTransport()
    with connect(store) as conn:
        at, claims, gaps = NOW, 0, []
        for i in range(MAX_ATTEMPTS + 3):
            if not claim_due(conn, at, f"crashing-{i}"):  # ...each worker dies holding it.
                break
            claims += 1
            at += LEASE + timedelta(seconds=1)
            dispatch_due(conn, transport, feed, at, "reaper")  # Recovers; nothing is due yet.
            (alert,) = alerts(conn)
            if alert["status"] != "pending":
                break
            gaps.append(alert["next_attempt_at"] - at)
            at = alert["next_attempt_at"]
        (alert,) = alerts(conn)
        assert claims == MAX_ATTEMPTS  # Each crashed round counted exactly once.
        assert (alert["status"], alert["attempts"], alert["last_error_code"]) == (
            "failed", MAX_ATTEMPTS, "attempts_exhausted")
        assert gaps == sorted(gaps) and gaps[0] > timedelta(0)  # Growing backoff.
        assert transport.sent == []
        assert claim_due(conn, at + timedelta(days=1), "late") == []


def test_provider_acceptance_then_persistence_failure_leaves_reconciliation_evidence(pg_store):
    store, feed, artists = seeded(pg_store)
    queue_one(store, feed, artists)
    worker = connect(store)
    # The provider accepts the message, then the worker's database connection dies
    # before the outcome commits.
    provider = BlindTransport(on_send=worker.close)
    with pytest.raises(psycopg.OperationalError):
        dispatch_due(worker, provider, feed, NOW, "w1")  # Not reported as a good batch.
    assert len(provider.keys) == 1
    with connect(store) as conn:
        (attempt,) = conn.execute("SELECT * FROM delivery_attempts").fetchall()
        (delivery,) = conn.execute("SELECT * FROM alert_deliveries").fetchall()
        # Durable evidence: the intent was committed before the send, under the same key
        # the provider received.
        assert (attempt["status"], delivery["status"]) == ("sending", "sending")
        assert str(delivery["delivery_key"]) == provider.keys[0]
        # After the lease, recovery marks the outcome unknown. This provider can neither
        # look the key up nor de-duplicate it, so the message is never sent again.
        dispatch_due(conn, provider, feed, NOW + LEASE + timedelta(seconds=1), "w2")
        (alert,) = alerts(conn)
        assert deliveries(conn)["email"]["status"] == "uncertain"
        dispatch_due(conn, provider, feed, alert["next_attempt_at"], "w2")
        (alert,) = alerts(conn)
        assert (alert["status"], alert["last_error_code"]) == ("uncertain", "outcome_unknown")
        assert len(provider.keys) == 1
        (attempt,) = conn.execute("SELECT * FROM delivery_attempts").fetchall()
        assert (attempt["status"], attempt["error_code"]) == ("uncertain", "lease_expired")


def test_an_uncertain_delivery_is_reconciled_before_any_retry(pg_store):
    store, feed, artists = seeded(pg_store)
    queue_one(store, feed, artists)
    worker = connect(store)
    provider = LookupProvider()
    deliver = provider.send

    def accept_then_lose_the_database(channel, endpoint_ref, message, key):
        result = deliver(channel, endpoint_ref, message, key)
        worker.close()
        return result

    provider.send = accept_then_lose_the_database
    with pytest.raises(psycopg.OperationalError):
        dispatch_due(worker, provider, feed, NOW, "w1")
    provider.send = deliver
    with connect(store) as conn:
        dispatch_due(conn, provider, feed, NOW + LEASE + timedelta(seconds=1), "w2")
        (alert,) = alerts(conn)
        assert dispatch_due(conn, provider, feed, alert["next_attempt_at"], "w2")["sent"] == 1
        assert len(provider.sent) == 1  # Reconciled as delivered; not sent a second time.
        (attempt,) = conn.execute("SELECT * FROM delivery_attempts").fetchall()
        assert attempt["status"] == "sent" and attempt["provider_message_id"].startswith("log-")


def test_a_lost_connection_is_never_recorded_as_a_successful_job(pg_store):
    store, feed, artists = seeded(pg_store)
    queue_one(store, feed, artists)
    worker = connect(store)
    provider = BlindTransport(on_send=worker.close)
    with pytest.raises(psycopg.OperationalError):
        run_job(worker, "dispatch_alerts", "k",
                lambda: dispatch_due(worker, provider, feed, NOW, "w1"), NOW, "w1")
    with connect(store) as conn:
        (job,) = conn.execute("SELECT * FROM job_runs").fetchall()
        assert job["status"] == "running"  # Left to lease recovery, never marked succeeded.


def test_an_expired_worker_cannot_overwrite_its_replacement(pg_store):
    store, feed, artists = seeded(pg_store)
    queue_one(store, feed, artists)
    provider = LookupProvider()
    later = NOW + LEASE + timedelta(seconds=1)
    takeover = {}

    class Stalling(Transport):
        def send(self, channel, endpoint_ref, message, key):
            message_id = provider.send(channel, endpoint_ref, message, key)
            # The first worker stalls past its lease. A replacement reusing the same worker
            # name recovers the alert, reconciles the send and finishes it.
            with connect(store) as other:
                dispatch_due(other, provider, feed, later, "w1")
                (alert,) = alerts(other)
                takeover["counts"] = dispatch_due(other, provider, feed,
                                                  alert["next_attempt_at"], "w1")
                takeover["alert"] = alerts(other)[0]
            return message_id  # The stalled worker now tries to record its outcome.

    with connect(store) as stale:
        counts = dispatch_due(stale, Stalling(), feed, NOW, "w1")
        assert counts["lease_lost"] == 1 and counts["sent"] == 0
        assert takeover["counts"]["sent"] == 1
        (alert,) = alerts(stale)
        # The replacement's result stands; nothing of the stale worker's was written.
        assert alert == takeover["alert"]
        assert (alert["status"], alert["claim_token"], alert["attempts"]) == ("sent", None, 2)
        (attempt,) = stale.execute("SELECT * FROM delivery_attempts").fetchall()
        assert attempt["status"] == "sent"
        assert len(provider.sent) == 1


@pytest.mark.parametrize("path", ["success", "failure"])
def test_a_stale_job_completion_is_rejected(pg_store, path):
    store, _ = pg_store
    with connect(store) as conn:
        replacement = {}

        def stalled_work():
            # The same worker name: only the attempt generation tells the claims apart.
            later = NOW + LEASE + timedelta(minutes=3)
            replacement["result"] = run_job(conn, "collect", "k", lambda: {"n": 2}, later, "w")
            if path == "failure":
                raise ValueError("the stale run fails late")
            return {"n": 1}

        assert run_job(conn, "collect", "k", stalled_work, NOW, "w") == {"status": "lease_lost"}
        assert replacement["result"] == {"status": "succeeded", "n": 2}
        (job,) = conn.execute("SELECT * FROM job_runs").fetchall()
        assert (job["status"], job["attempt"], job["last_error_code"]) == ("succeeded", 2, None)


def test_a_stale_generation_cannot_close_a_running_replacement(pg_store):
    # Both claims are running under the same worker name; only the attempt generation
    # separates them, so the old one must not be able to close the new one.
    store, _ = pg_store

    class Crash(BaseException):
        pass

    def crash():
        raise Crash()

    with connect(store) as conn:
        with pytest.raises(Crash):
            run_job(conn, "collect", "k", crash, NOW, "w")
        (stale,) = conn.execute("SELECT * FROM job_runs").fetchall()
        later = NOW + LEASE + timedelta(minutes=3)
        closed = {}

        def replacement_work():
            closed["success"] = alerts_module._close_job(
                conn, stale, later, status="succeeded", last_error_code=None)
            closed["failure"] = alerts_module._close_job(
                conn, stale, later, status="failed", last_error_code="ValueError",
                run_after=later)
            return {"n": 2}

        assert run_job(conn, "collect", "k", replacement_work, later, "w") == {
            "status": "succeeded", "n": 2}
        assert closed == {"success": False, "failure": False}
        (job,) = conn.execute("SELECT * FROM job_runs").fetchall()
        assert (job["status"], job["attempt"]) == ("succeeded", 2)


def test_a_repeatedly_crashing_job_is_dead_lettered(pg_store):
    store, _ = pg_store

    class Crash(BaseException):
        """The process dies mid-work: nothing is recorded."""

    def crash():
        raise Crash()

    with connect(store) as conn:
        at = NOW
        for _ in range(3):
            with pytest.raises(Crash):
                run_job(conn, "collect", "k", crash, at, "w", max_attempts=3)
            assert run_job(conn, "collect", "k", crash, at + LEASE, "w", max_attempts=3) is None
            at += LEASE + timedelta(hours=1)  # Past the lease and its backoff.
        assert run_job(conn, "collect", "k", dict, at, "w") is None
        (job,) = conn.execute("SELECT * FROM job_runs").fetchall()
        assert (job["status"], job["attempt"], job["last_error_code"]) == (
            "dead", 3, "lease_expired")


def test_display_withdrawn_after_projection_suppresses_the_send(pg_store):
    store, feed, artists = seeded(pg_store)
    queue_one(store, feed, artists)
    transport = LogTransport()
    with connect(store) as conn:
        # The tick projected the event as displayable; permission is withdrawn afterwards.
        conn.execute("UPDATE source_permissions SET display_allowed = false")
        counts = dispatch_due(conn, transport, feed, NOW, "w1", lookup=store_lookup(store))
        assert counts["suppressed"] == 1 and transport.sent == []
        assert alerts(conn)[0]["suppressed_reason"] == "not_displayable"


def test_display_withdrawn_between_subscriptions_suppresses_the_next_send(pg_store):
    conn, feed = two_channel_alert(pg_store)
    with conn:
        live = {"feed": feed}

        class Withdrawing(LogTransport):
            def send(self, channel, endpoint_ref, message, key):
                live["feed"] = {"events": []}  # The next projection no longer shows it.
                return super().send(channel, endpoint_ref, message, key)

        transport = Withdrawing()
        dispatch_due(conn, transport, feed, NOW, "w1",
                     lookup=lambda event_id, at: feed_lookup(live["feed"])(event_id, at))
        assert len(transport.sent) == 1
        reasons = sorted(str(d["suppressed_reason"]) for d in deliveries(conn).values())
        assert reasons == ["None", "not_displayable"]


def test_consent_revoked_between_subscriptions_suppresses_the_next_send(pg_store):
    conn, feed = two_channel_alert(pg_store)
    with conn:
        revoker = other_connection(conn)

        class Revoking(LogTransport):
            def send(self, channel, endpoint_ref, message, key):
                # While one subscription is being sent, the user revokes the other.
                revoker.execute("UPDATE notification_subscriptions SET revoked_at = %s "
                                "WHERE endpoint_ref <> %s", (NOW, endpoint_ref))
                return super().send(channel, endpoint_ref, message, key)

        transport = Revoking()
        assert dispatch_due(conn, transport, feed, NOW, "w1")["sent"] == 1
        assert len(transport.sent) == 1
        reasons = sorted(str(d["suppressed_reason"]) for d in deliveries(conn).values())
        assert reasons == ["None", "no_current_consent"]
        revoker.close()


def test_expiry_between_subscriptions_suppresses_the_next_send(pg_store):
    conn, feed = two_channel_alert(pg_store)
    with conn:
        # Due to expire a minute from now, well inside the worker's lease.
        (alert,) = conn.execute("UPDATE alerts SET expires_at = %s RETURNING *",
                                (NOW + timedelta(minutes=1),)).fetchall()
        clock = {"now": NOW}

        class Slow(LogTransport):
            def send(self, channel, endpoint_ref, message, key):
                clock["now"] = alert["expires_at"]  # The first send takes until expiry.
                return super().send(channel, endpoint_ref, message, key)

        transport = Slow()
        dispatch_due(conn, transport, feed, NOW, "w1", clock=lambda: clock["now"])
        assert len(transport.sent) == 1
        reasons = sorted(str(d["suppressed_reason"]) for d in deliveries(conn).values())
        assert reasons == ["None", "expired"]
