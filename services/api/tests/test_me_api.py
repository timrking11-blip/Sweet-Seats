"""Signed-in user workflows against disposable PostgreSQL: the verified token subject is
the only identity, row-level security is the only ownership filter, and consent
withdrawal, unfollowing and deletion requests reach work already queued."""
import os
from datetime import timedelta
from uuid import uuid4

import pytest
from conftest import TEST_ISSUER, mint_token
from fastapi.testclient import TestClient

from app import me as me_module
from app.alerts import LogTransport, dispatch_due, enqueue_alerts, plan_alerts, tick
from app.discovery import timestamp
from app.main import app
from app.me import auth_now, user_store

NOW = timestamp("2026-10-18T07:00:00Z")
pytestmark = pytest.mark.skipif(not os.environ.get("SWEET_SEATS_TEST_DATABASE_URL"),
                                reason="requires disposable local PostgreSQL DSN")


def bearer(user: str, *, signed_in: timedelta | None = timedelta(minutes=1)) -> dict:
    """A user token; signed_in is how long ago the user last signed in (None: unstated)."""
    claims = {"sub": user, "role": "authenticated", "aud": "authenticated",
              "iss": TEST_ISSUER, "exp": int((NOW + timedelta(hours=1)).timestamp())}
    if signed_in is not None:
        claims["amr"] = [{"method": "otp", "timestamp": int((NOW - signed_in).timestamp())}]
    return {"Authorization": "Bearer " + mint_token(claims)}


def admin(store):
    conn = store._connect()
    conn.autocommit = True
    return conn


def account(conn, *, profile=True) -> str:
    """A Supabase Auth user, optionally with a profile and a server-created email
    subscription (subscriptions are never created by the user API)."""
    user = str(uuid4())
    conn.execute("INSERT INTO auth.users(id) VALUES (%s)", (user,))
    if profile:
        conn.execute("INSERT INTO user_profiles(user_id, consent_version) VALUES (%s, 'c1')", (user,))
        conn.execute(
            """INSERT INTO notification_subscriptions(user_id, channel, endpoint_ref,
                   consent_version, consent_at) VALUES (%s, 'email', %s, 'c1', %s)""",
            (user, "secret://email/" + user, NOW - timedelta(days=1)))
    return user


@pytest.fixture
def world(pg_store, auth_env):
    store, fixture = pg_store
    store.seed(fixture, NOW)
    feed = store.feed(NOW)
    artists = sorted({p["artist_id"] for e in feed["events"] for p in e["performers"]
                      if p["role"] == "headliner"})
    app.dependency_overrides[user_store] = lambda: store
    app.dependency_overrides[auth_now] = lambda: NOW
    try:
        with admin(store) as conn, TestClient(app) as client:
            yield {"client": client, "conn": conn, "store": store, "feed": feed,
                   "artists": artists, "a": account(conn), "b": account(conn)}
    finally:
        app.dependency_overrides.pop(user_store, None)
        app.dependency_overrides.pop(auth_now, None)


def subscription(conn, user) -> str:
    return str(conn.execute("SELECT subscription_id FROM notification_subscriptions "
                            "WHERE user_id = %s", (user,)).fetchone()["subscription_id"])


def test_each_account_sees_only_its_own_rows(world):
    client, a, b, artists = world["client"], world["a"], world["b"], world["artists"]
    assert client.put(f"/v1/me/follows/{artists[0]}", headers=bearer(a)).status_code == 200
    assert client.put(f"/v1/me/follows/{artists[1]}", headers=bearer(b)).status_code == 200
    mine = client.get("/v1/me", headers=bearer(a))
    assert mine.status_code == 200
    assert mine.headers["cache-control"].startswith("private, no-store")
    body = mine.json()
    assert body["user_id"] == a
    assert [f["artist_id"] for f in body["follows"]] == [artists[0]]
    assert [s["subscription_id"] for s in body["subscriptions"]] == [subscription(world["conn"], a)]
    assert "endpoint_ref" not in body["subscriptions"][0]  # A secret-store pointer.
    theirs = client.get("/v1/me", headers=bearer(b)).json()
    assert [f["artist_id"] for f in theirs["follows"]] == [artists[1]]


def test_cross_account_writes_answer_404_and_change_nothing(world):
    client, conn, a, b, artists = (world[k] for k in ("client", "conn", "a", "b", "artists"))
    client.put(f"/v1/me/follows/{artists[1]}", headers=bearer(b))
    theirs = subscription(conn, b)
    assert client.post(f"/v1/me/subscriptions/{theirs}/revoke", headers=bearer(a)).status_code == 404
    assert client.delete(f"/v1/me/follows/{artists[1]}", headers=bearer(a)).status_code == 404
    row = conn.execute("SELECT revoked_at FROM notification_subscriptions "
                       "WHERE subscription_id = %s", (theirs,)).fetchone()
    assert row["revoked_at"] is None
    assert conn.execute("SELECT enabled FROM artist_follows WHERE user_id = %s",
                        (b,)).fetchone()["enabled"] is True


def test_a_client_cannot_name_a_user_id(world):
    client, conn, a, b, artists = (world[k] for k in ("client", "conn", "a", "b", "artists"))
    body = {"user_id": b, "timezone": "America/New_York"}
    assert client.put("/v1/me/profile", json=body, headers=bearer(a)).status_code == 422
    # A stray query parameter is ignored; the follow is the token subject's.
    client.put(f"/v1/me/follows/{artists[0]}?user_id={b}", headers=bearer(a))
    owners = [str(r["user_id"]) for r in conn.execute("SELECT user_id FROM artist_follows")]
    assert owners == [a]


def test_isolation_comes_from_row_level_security_not_api_filters(world, monkeypatch):
    # Control: without the role switch the same API code runs as the administrative
    # connection and sees every account. The isolation tests above would then fail, so
    # they prove RLS enforcement rather than a user_id filter in the API.
    client, a, b, artists = (world[k] for k in ("client", "a", "b", "artists"))
    client.put(f"/v1/me/follows/{artists[0]}", headers=bearer(a))
    client.put(f"/v1/me/follows/{artists[1]}", headers=bearer(b))
    monkeypatch.setattr(me_module, "ACT_AS_USER", "SELECT 1")
    leaked = client.get("/v1/me", headers=bearer(a)).json()
    assert len(leaked["follows"]) == 2 and len(leaked["subscriptions"]) == 2


def test_profile_creation_and_validation(world):
    client, conn = world["client"], world["conn"]
    fresh = account(conn, profile=False)
    created = client.put("/v1/me/profile", json={"timezone": "Europe/London"}, headers=bearer(fresh))
    assert created.status_code == 200 and created.json()["timezone"] == "Europe/London"
    for zone in ("Not/A_Zone", "../../etc/passwd", "UTC "):
        assert client.put("/v1/me/profile", json={"timezone": zone},
                          headers=bearer(fresh)).status_code == 422
    # A token for a subject Supabase Auth does not know cannot create a profile.
    assert client.put("/v1/me/profile", json={}, headers=bearer(str(uuid4()))).status_code == 409


def test_follow_errors(world):
    client, conn = world["client"], world["conn"]
    assert client.put(f"/v1/me/follows/{uuid4()}", headers=bearer(world["a"])).status_code == 404
    no_profile = account(conn, profile=False)
    response = client.put(f"/v1/me/follows/{world['artists'][0]}", headers=bearer(no_profile))
    assert response.status_code == 409
    assert client.delete(f"/v1/me/follows/{uuid4()}", headers=bearer(world["a"])).status_code == 404


def queue(world, user):
    """The user follows the first headliner through the API, and one alert is queued."""
    world["client"].put(f"/v1/me/follows/{world['artists'][0]}", headers=bearer(user))
    intents = plan_alerts(world["feed"], [(user, world["artists"][0])], NOW)[:1]
    assert enqueue_alerts(world["conn"], intents, NOW) == 1


def outbox(conn, user) -> list[dict]:
    return conn.execute("SELECT * FROM alerts WHERE user_id = %s", (user,)).fetchall()


def test_withdrawing_consent_suppresses_queued_alerts(world):
    client, conn, a = world["client"], world["conn"], world["a"]
    queue(world, a)
    mine = subscription(conn, a)
    first = client.post(f"/v1/me/subscriptions/{mine}/revoke", headers=bearer(a))
    assert first.status_code == 200 and first.json()["revoked_at"]
    again = client.post(f"/v1/me/subscriptions/{mine}/revoke", headers=bearer(a))
    assert again.json()["revoked_at"] == first.json()["revoked_at"]  # One way, idempotent.
    transport = LogTransport()
    assert dispatch_due(conn, transport, world["feed"], NOW, "w1")["suppressed"] == 1
    assert outbox(conn, a)[0]["suppressed_reason"] == "no_current_consent"
    assert transport.sent == []


def test_unfollowing_suppresses_queued_alerts(world):
    client, conn, a = world["client"], world["conn"], world["a"]
    queue(world, a)
    unfollowed = client.delete(f"/v1/me/follows/{world['artists'][0]}", headers=bearer(a))
    assert unfollowed.status_code == 204
    transport = LogTransport()
    assert dispatch_due(conn, transport, world["feed"], NOW, "w1")["suppressed"] == 1
    assert outbox(conn, a)[0]["suppressed_reason"] == "not_following"
    assert transport.sent == []


def test_a_deletion_request_stops_planning_and_sending(world):
    client, conn, store, a = world["client"], world["conn"], world["store"], world["a"]
    queue(world, a)
    first = client.post("/v1/me/deletion-request", headers=bearer(a))
    assert first.status_code == 202
    again = client.post("/v1/me/deletion-request", headers=bearer(a))
    assert again.json()["deletion_requested_at"] == first.json()["deletion_requested_at"]
    transport = LogTransport()
    tick(store, transport, NOW, "w1")
    assert transport.sent == []
    # Queued work is suppressed and nothing new is planned for the account.
    assert [(r["status"], r["suppressed_reason"]) for r in outbox(conn, a)] == [
        ("suppressed", "no_current_consent")]


def test_after_a_deletion_request_the_account_cannot_change(world):
    client, conn, a, artists = world["client"], world["conn"], world["a"], world["artists"]
    client.put(f"/v1/me/follows/{artists[0]}", headers=bearer(a))
    assert client.post("/v1/me/deletion-request", headers=bearer(a)).status_code == 202
    assert client.put(f"/v1/me/follows/{artists[1]}", headers=bearer(a)).status_code == 409
    assert client.delete(f"/v1/me/follows/{artists[0]}", headers=bearer(a)).status_code == 409
    assert client.put("/v1/me/profile", json={}, headers=bearer(a)).status_code == 409
    assert conn.execute("SELECT count(*) AS n FROM artist_follows WHERE user_id = %s",
                        (a,)).fetchone()["n"] == 1


def test_an_account_without_a_profile_can_request_deletion(world):
    client, conn = world["client"], world["conn"]
    fresh = account(conn, profile=False)
    response = client.post("/v1/me/deletion-request", headers=bearer(fresh))
    assert response.status_code == 202 and response.json()["deletion_requested_at"]
    assert client.post("/v1/me/deletion-request",
                       headers=bearer(str(uuid4()))).status_code == 409  # Unknown to Auth.


@pytest.mark.parametrize("signed_in", [timedelta(minutes=11), None])
def test_deletion_needs_a_recent_sign_in(world, signed_in):
    client, conn, a = world["client"], world["conn"], world["a"]
    response = client.post("/v1/me/deletion-request", headers=bearer(a, signed_in=signed_in))
    assert response.status_code == 401
    assert "insufficient_user_authentication" in response.headers["www-authenticate"]
    assert conn.execute("SELECT deletion_requested_at FROM user_profiles WHERE user_id = %s",
                        (a,)).fetchone()["deletion_requested_at"] is None
    # An old session still reads and edits; only the irreversible action needs a fresh sign-in.
    assert client.get("/v1/me", headers=bearer(a, signed_in=signed_in)).status_code == 200
    assert client.post("/v1/me/deletion-request",
                       headers=bearer(a, signed_in=timedelta(minutes=9))).status_code == 202


def test_other_privilege_errors_are_server_faults_not_deletion(world, monkeypatch):
    # A login that may not switch to the user role must not tell users their account is
    # being deleted.
    monkeypatch.setattr(me_module, "ACT_AS_USER", "DO $$ BEGIN RAISE EXCEPTION 'role_denied' "
                        "USING ERRCODE = '42501'; END $$")
    response = world["client"].get("/v1/me", headers=bearer(world["a"]))
    assert response.status_code == 503
