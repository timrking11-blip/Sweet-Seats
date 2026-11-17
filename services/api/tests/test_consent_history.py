"""Consent history through the API (G-15): the server chooses the copy, every grant and
withdrawal becomes an event bound to the registered hash, and a user sees only theirs."""
import os

import pytest
from test_me_api import bearer, world  # noqa: F401  (shared fixture)

from app.consent import OUTCOMES

pytestmark = pytest.mark.skipif(not os.environ.get("SWEET_SEATS_TEST_DATABASE_URL"),
                                reason="requires disposable local PostgreSQL DSN")


def test_the_registered_copy_matches_the_api_copy(world):  # noqa: F811
    row = world["conn"].execute(
        "SELECT copy_sha256, retired_at FROM consent_copies WHERE kind = 'outcomes' AND version = %s",
        (OUTCOMES.version,)).fetchone()
    assert row == {"copy_sha256": OUTCOMES.sha256, "retired_at": None}


def test_grant_and_withdraw_are_recorded_under_the_server_copy(world):  # noqa: F811
    client, a, b = world["client"], world["a"], world["b"]
    shown = client.get("/v1/me/consent", headers=bearer(a)).json()
    assert shown["copies"]["outcomes"] == {"version": OUTCOMES.version, "text": OUTCOMES.text,
                                           "sha256": OUTCOMES.sha256}
    assert shown["current"] == {"outcomes": None}

    assert client.put("/v1/me/consent/outcomes", json={"grant": True}, headers=bearer(a)).json() == {
        "outcomes": OUTCOMES.version}
    # Repeating a grant is not a new consent.
    client.put("/v1/me/consent/outcomes", json={"grant": True}, headers=bearer(a))
    assert client.put("/v1/me/consent/outcomes", json={"grant": False}, headers=bearer(a)).json() == {
        "outcomes": None}
    client.put("/v1/me/consent/outcomes", json={"grant": False}, headers=bearer(a))

    history = client.get("/v1/me/consent", headers=bearer(a)).json()["history"]
    outcomes = [(h["action"], h["copy_version"], h["copy_sha256"], h["source"])
                for h in history if h["kind"] == "outcomes"]
    assert outcomes == [("grant", OUTCOMES.version, OUTCOMES.sha256, "user"),
                        ("withdraw", OUTCOMES.version, OUTCOMES.sha256, "user")]
    # B sees only B's own history (the server-created subscription grant).
    other = client.get("/v1/me/consent", headers=bearer(b)).json()["history"]
    assert [(h["kind"], h["action"]) for h in other] == [("alerts_email", "grant")]


def test_revoking_a_subscription_appends_a_withdrawal(world):  # noqa: F811
    client, conn, a = world["client"], world["conn"], world["a"]
    sub = conn.execute("SELECT subscription_id FROM notification_subscriptions WHERE user_id = %s",
                       (a,)).fetchone()["subscription_id"]
    client.post(f"/v1/me/subscriptions/{sub}/revoke", headers=bearer(a))
    history = client.get("/v1/me/consent", headers=bearer(a)).json()["history"]
    assert [(h["kind"], h["action"], h["source"]) for h in history] == [
        ("alerts_email", "grant", "system"), ("alerts_email", "withdraw", "user")]


@pytest.mark.parametrize("body", [{"grant": True, "version": "mine"}, {"version": "mine"}, {}])
def test_the_client_cannot_name_a_version(world, body):  # noqa: F811
    response = world["client"].put("/v1/me/consent/outcomes", json=body, headers=bearer(world["a"]))
    assert response.status_code == 422


def test_consent_after_a_deletion_request_is_refused(world):  # noqa: F811
    client, a = world["client"], world["a"]
    assert client.post("/v1/me/deletion-request", headers=bearer(a)).status_code == 202
    assert client.put("/v1/me/consent/outcomes", json={"grant": True},
                      headers=bearer(a)).status_code == 409
