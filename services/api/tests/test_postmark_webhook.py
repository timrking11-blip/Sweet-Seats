"""Postmark webhooks against disposable PostgreSQL: only an authenticated Postmark call
acts; a permanent bounce, complaint or unsubscribe revokes consent with its cause; an
open is an outcome only with outcome consent, once per alert."""
import base64
import os

import httpx
import pytest
from test_me_api import NOW, bearer, queue, subscription, world  # noqa: F401

from app.alerts import dispatch_due
from app.main import app
from app.transports.postmark import PostmarkTransport
from app.webhooks import webhook_now, webhook_store

pytestmark = pytest.mark.skipif(not os.environ.get("SWEET_SEATS_TEST_DATABASE_URL"),
                                reason="requires disposable local PostgreSQL DSN")
USER, PASSWORD = "postmark-hook", "a-long-webhook-password-0123"


def auth(user=USER, password=PASSWORD) -> dict:
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}


@pytest.fixture
def sent(world, monkeypatch):  # noqa: F811
    """User A has one alert delivered through a fake Postmark; yields its dedupe key."""
    monkeypatch.setenv("SWEET_SEATS_POSTMARK_WEBHOOK_USER", USER)
    monkeypatch.setenv("SWEET_SEATS_POSTMARK_WEBHOOK_PASSWORD", PASSWORD)
    app.dependency_overrides[webhook_store] = lambda: world["store"]
    app.dependency_overrides[webhook_now] = lambda: NOW
    bodies = []

    def fake_postmark(request):
        bodies.append(__import__("json").loads(request.content))
        return httpx.Response(200, json={"ErrorCode": 0, "MessageID": f"pm-{len(bodies)}"})

    client = httpx.Client(base_url="https://api.postmarkapp.com",
                          transport=httpx.MockTransport(fake_postmark))
    postmark = PostmarkTransport("token", "alerts@sweetseats.example",
                                 lambda ref: "fan@example.test", client=client)
    queue(world, world["a"])
    assert dispatch_due(world["conn"], postmark, world["feed"], NOW, "w1")["sent"] == 1
    try:
        yield bodies[0]["Metadata"]["dedupe_key"], bodies[0]
    finally:
        app.dependency_overrides.pop(webhook_store, None)
        app.dependency_overrides.pop(webhook_now, None)


def hook(world, body, headers=None):  # noqa: F811
    return world["client"].post("/v1/webhooks/postmark", json=body,
                                headers=auth() if headers is None else headers)


def events(world, user):  # noqa: F811
    return [(r["kind"], r["action"], r["source"]) for r in world["conn"].execute(
        "SELECT kind, action, source FROM consent_events WHERE user_id = %s ORDER BY created_at",
        (user,)).fetchall()]


def test_a_delivered_alert_names_its_source(world, sent):  # noqa: F811
    assert "Where this came from:" in sent[1]["TextBody"]


@pytest.mark.parametrize("headers,status", [({}, 401), (auth(password="wrong-password-0123456789"), 401),
                                            ({"Authorization": "Bearer x"}, 401)])
def test_only_postmark_can_call(world, sent, headers, status):  # noqa: F811
    body = {"RecordType": "SpamComplaint", "Metadata": {"dedupe_key": sent[0]}}
    assert hook(world, body, headers).status_code == status
    assert events(world, world["a"]) == [("alerts_email", "grant", "system")]


def test_an_unconfigured_webhook_refuses(world, sent, monkeypatch):  # noqa: F811
    monkeypatch.delenv("SWEET_SEATS_POSTMARK_WEBHOOK_PASSWORD")
    assert hook(world, {"RecordType": "SpamComplaint"}).status_code == 503


@pytest.mark.parametrize("body,source", [
    ({"RecordType": "Bounce", "Type": "HardBounce"}, "bounce"),
    ({"RecordType": "SpamComplaint"}, "complaint"),
    ({"RecordType": "SubscriptionChange", "SuppressSending": True}, "user"),
])
def test_permanent_failures_revoke_consent_with_their_cause(world, sent, body, source):  # noqa: F811
    assert hook(world, {**body, "Metadata": {"dedupe_key": sent[0]}}).json() == {"status": "ok"}
    sub = subscription(world["conn"], world["a"])
    assert world["conn"].execute("SELECT revoked_at FROM notification_subscriptions "
                                 "WHERE subscription_id = %s", (sub,)).fetchone()["revoked_at"]
    assert events(world, world["a"]) == [("alerts_email", "grant", "system"),
                                         ("alerts_email", "withdraw", source)]


@pytest.mark.parametrize("body", [
    {"RecordType": "Bounce", "Type": "SoftBounce"},
    {"RecordType": "Delivery"},
    {"RecordType": "SpamComplaint", "Metadata": {"dedupe_key": "00000000-0000-4000-8000-000000000000"}},
    {"RecordType": "SpamComplaint", "Metadata": {"dedupe_key": "not-a-key"}},
    {"RecordType": "SpamComplaint", "Metadata": None},
    {"RecordType": "SpamComplaint", "Metadata": {"recipient": "fan@example.test"}},
])
def test_other_records_change_nothing(world, sent, body):  # noqa: F811
    body = {"Metadata": {"dedupe_key": sent[0]}, **body}
    assert hook(world, body).status_code == 200
    assert events(world, world["a"]) == [("alerts_email", "grant", "system")]


def opens(world):  # noqa: F811
    return world["conn"].execute("SELECT count(*) AS n FROM outcome_events WHERE kind = 'alert_opened'"
                                 ).fetchone()["n"]


def test_an_open_is_recorded_only_with_outcome_consent_and_once(world, sent):  # noqa: F811
    body = {"RecordType": "Open", "Metadata": {"dedupe_key": sent[0]},
            "ReceivedAt": "2026-10-18T06:59:00Z"}
    hook(world, body)
    assert opens(world) == 0
    client, a = world["client"], world["a"]
    assert client.put("/v1/me/consent/outcomes", json={"grant": True}, headers=bearer(a)).status_code == 200
    hook(world, body)
    hook(world, body)
    assert opens(world) == 1
