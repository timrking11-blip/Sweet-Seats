"""Waitlist sign-up: server-chosen consent evidence, first-touch attribution, and answers
that never reveal whether an email is already on the list."""
import hashlib

import pytest
from fastapi.testclient import TestClient

from app import waitlist
from app.main import app
from app.waitlist import CONSENT_COPY, CONSENT_VERSION, RateLimiter, waitlist_store


def signup(**overrides) -> dict:
    body = {"email": " Fan@Example.TEST ", "consent": True, "consent_version": CONSENT_VERSION,
            "source": "Instagram", "artists": ["Synthetic Band", " synthetic  band ", "Synthetic Band"]}
    body.update(overrides)
    return body


@pytest.fixture
def client(pg_store, monkeypatch):
    store, _ = pg_store
    monkeypatch.setattr(waitlist, "limiter", RateLimiter(limit=100))
    app.dependency_overrides[waitlist_store] = lambda: store
    try:
        yield TestClient(app), store
    finally:
        app.dependency_overrides.pop(waitlist_store, None)


def rows(store) -> list[dict]:
    with store._connect() as conn:
        return conn.execute("SELECT * FROM waitlist_signups ORDER BY created_at").fetchall()


def test_consent_copy_is_served_with_its_version():
    body = TestClient(app).get("/v1/waitlist/consent").json()
    assert body == {"version": CONSENT_VERSION, "copy": CONSENT_COPY}


def test_a_signup_records_server_consent_evidence_and_attribution(client):
    http, store = client
    response = http.post("/v1/waitlist", json=signup())
    assert (response.status_code, response.json()) == (202, {"status": "received"})
    assert response.headers["Cache-Control"].startswith("private, no-store")
    (row,) = rows(store)
    assert row["email"] == "fan@example.test"
    assert row["consent_version"] == CONSENT_VERSION
    assert row["consent_copy_sha256"] == hashlib.sha256(CONSENT_COPY.encode()).hexdigest()
    assert row["source"] == "instagram"
    assert row["artists"] == ["Synthetic Band", "synthetic band"]
    assert row["invited_at"] is None


def test_a_repeat_signup_keeps_the_first_record_and_answers_the_same(client):
    http, store = client
    first = http.post("/v1/waitlist", json=signup())
    again = http.post("/v1/waitlist", json=signup(source="newsletter", artists=["Other"]))
    assert first.json() == again.json() and again.status_code == 202
    (row,) = rows(store)
    assert (row["source"], row["artists"]) == ("instagram", ["Synthetic Band", "synthetic band"])


def test_the_honeypot_answers_like_success_and_stores_nothing(client):
    http, store = client
    response = http.post("/v1/waitlist", json=signup(website="http://spam.example"))
    assert (response.status_code, response.json()) == (202, {"status": "received"})
    assert rows(store) == []


@pytest.mark.parametrize("override,status", [
    ({"consent": False}, 422),
    ({"consent_version": "waitlist-2020-01-01"}, 409),
    ({"email": "not-an-email"}, 422),
    ({"artists": ["x"] * 11}, 422),
    ({"user_id": "someone"}, 422),
])
def test_invalid_or_unconsented_signups_store_nothing(client, override, status):
    http, store = client
    assert http.post("/v1/waitlist", json=signup(**override)).status_code == status
    assert rows(store) == []


def test_an_unknown_source_is_recorded_as_direct(client):
    http, store = client
    http.post("/v1/waitlist", json=signup(source="<script>"))
    assert rows(store)[0]["source"] == "direct"


def test_the_rate_limit_applies_per_client_address(client, monkeypatch):
    http, _ = client
    monkeypatch.setattr(waitlist, "limiter", RateLimiter(limit=2))
    forwarded = {"X-Forwarded-For": "spoofed, 203.0.113.9"}
    codes = [http.post("/v1/waitlist", json=signup(email=f"f{i}@example.test"), headers=forwarded).status_code
             for i in range(3)]
    assert codes == [202, 202, 429]
    other = {"X-Forwarded-For": "203.0.113.10"}
    assert http.post("/v1/waitlist", json=signup(email="g@example.test"), headers=other).status_code == 202


def test_the_rate_limiter_window_slides():
    clock = iter([0, 1, 2, 700]).__next__
    limiter = RateLimiter(limit=2, window=600, clock=clock)
    assert [limiter.allow("a") for _ in range(4)] == [True, True, False, True]


def test_without_a_database_the_signup_is_unavailable(monkeypatch):
    monkeypatch.delenv("SWEET_SEATS_LOCAL_DATABASE_URL", raising=False)
    response = TestClient(app).post("/v1/waitlist", json=signup())
    assert response.status_code == 503
