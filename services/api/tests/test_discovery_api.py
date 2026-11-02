"""API contract tests over a disposable persisted synthetic store."""
import copy
import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.discovery import DEFAULT_FIXTURE, FixtureStore, timestamp
from app.main import app, discovery_now, discovery_store, event_detail, events

NOW = timestamp("2026-10-18T07:00:00Z")


@pytest.fixture(params=["json", "postgres"])
def discovery_client(request):
    root = DEFAULT_FIXTURE.parents[3] / ".local" / "tests"
    root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=root) as directory:
        store = FixtureStore(Path(directory) / "events.json")
        fixture = json.loads(DEFAULT_FIXTURE.read_text(encoding="utf-8"))
        if request.param == "postgres":
            store, fixture = request.getfixturevalue("pg_store")
        app.dependency_overrides[discovery_store] = lambda: store
        app.dependency_overrides[discovery_now] = lambda: NOW
        try:
            with TestClient(app) as client:
                yield client, store, fixture
        finally:
            app.dependency_overrides.pop(discovery_store, None)
            app.dependency_overrides.pop(discovery_now, None)


def test_fixture_to_persisted_list_and_detail(discovery_client):
    client, store, fixture = discovery_client
    store.seed(fixture, NOW)
    response = client.get("/v1/events")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    feed = response.json()
    assert feed["mode"] == "synthetic"
    assert len(feed["events"]) == 3
    event = feed["events"][0]
    detail = client.get("/v1/events/" + event["event_id"])
    assert detail.status_code == 200
    assert detail.json()["event"] == event
    assert len(event["performers"]) == 2
    assert len(event["sources"]) == 2
    assert event["starts_at"] == "2026-11-07T01:00:00Z"
    assert event["available_at"] == "2026-10-18T06:50:00Z"
    assert event["stale"] is False
    assert event["ticket_url"] is None
    # Observation-based freshness and provenance timestamps survive persistence and the API.
    observed = timestamp(event["observed_at"])
    assert observed == timestamp("2026-10-18T06:50:00Z")
    assert timestamp(event["fresh_until"]) - observed == timedelta(hours=24)
    assert timestamp(event["first_seen_at"]) <= observed
    assert {s["observed_at"] for s in event["sources"]} == {"2026-10-18T06:50:00Z"}


def test_unseeded_store_is_503_with_redacted_error(discovery_client):
    client, store, _ = discovery_client
    response = client.get("/v1/events")
    assert response.status_code == 503
    assert str(getattr(store, "path", "synthetic-secret-canary")) not in response.text
    assert "events" not in response.json()


def test_nonexistent_event_is_404(discovery_client):
    client, store, fixture = discovery_client
    store.seed(fixture, NOW)
    assert client.get("/v1/events/00000000-0000-4000-8000-000000000000").status_code == 404


def test_unknown_display_rights_hide_list_and_detail(discovery_client):
    client, store, fixture = discovery_client
    store.seed(fixture, NOW)
    event_id = client.get("/v1/events").json()["events"][0]["event_id"]
    altered = copy.deepcopy(fixture)
    for source in altered["sources"]:
        source["permission"]["uses"].pop("display")
    store.seed(altered, NOW)
    assert client.get("/v1/events").json()["status"] == "blocked"
    assert client.get("/v1/events/" + event_id).status_code == 404


@pytest.mark.parametrize("transition", ["revoked", "expired"])
def test_previously_allowed_response_cannot_replace_current_permission_check(
    discovery_client, transition
):
    client, store, fixture = discovery_client
    # Exercise clock expiry without a database write at read time.
    expires = NOW + timedelta(minutes=1)
    for source in fixture["sources"]:
        source["permission"]["expires_at"] = expires.isoformat()
    store.seed(fixture, NOW)
    initial = client.get("/v1/events")
    event = initial.json()["events"][0]
    path = "/v1/events/" + event["event_id"]
    assert client.get(path).status_code == 200
    assert "no-store" in initial.headers["cache-control"]

    if transition == "revoked":
        for source in fixture["sources"]:
            source["permission"]["revoked_at"] = NOW.isoformat()
        # A permission-only revision must not replay a previously collected
        # payload as a newly skipped run under the same immutable logical key.
        fixture["batches"] = []
        store.seed(fixture, NOW)
    else:
        app.dependency_overrides[discovery_now] = lambda: expires

    # Even conditional requests must run projection again, not return 304 for
    # previously visible data. No ETag/Last-Modified validator is issued.
    conditional = {"If-None-Match": '"previously-allowed"',
                   "If-Modified-Since": "Sun, 18 Oct 2026 07:00:00 GMT"}
    blocked = client.get("/v1/events", headers=conditional)
    missing = client.get(path, headers=conditional)
    assert blocked.status_code == 200
    assert blocked.json()["status"] == "blocked"
    assert blocked.json()["events"] == []
    assert missing.status_code == 404
    assert event["title"] not in missing.text
    for response in (initial, blocked, missing):
        assert response.headers["cache-control"] == "private, no-store, max-age=0"
        assert response.headers["cdn-cache-control"] == "no-store"
        assert "etag" not in response.headers
        assert "last-modified" not in response.headers


def test_success_and_handled_error_responses_are_not_cacheable(discovery_client):
    client, store, fixture = discovery_client
    unseeded = client.get("/v1/events")
    assert unseeded.status_code == 503
    store.seed(fixture, NOW)
    feed = client.get("/v1/events")
    detail = client.get("/v1/events/" + feed.json()["events"][0]["event_id"])
    missing = client.get("/v1/events/00000000-0000-4000-8000-000000000000")
    invalid = client.get("/v1/events/not-a-uuid")
    disallowed = client.post("/v1/events", json={})
    assert [r.status_code for r in (feed, detail, missing, invalid, disallowed)] == [
        200, 200, 404, 422, 405
    ]
    for response in (unseeded, feed, detail, missing, invalid, disallowed):
        assert response.headers["cache-control"] == "private, no-store, max-age=0"
        assert response.headers["cdn-cache-control"] == "no-store"
        assert response.headers["pragma"] == "no-cache"
        assert response.headers["expires"] == "0"
    # The policy is scoped to discovery content, not unrelated service routes.
    assert "cache-control" not in client.get("/health").headers


@pytest.mark.parametrize("outcome,status", [("empty", "empty"), ("failed", "unavailable")])
def test_empty_and_failed_remain_distinct_through_api(discovery_client, outcome, status):
    client, store, fixture = discovery_client
    for batch in fixture["batches"]:
        batch.update(outcome=outcome, records=[])
    store.seed(fixture, NOW)
    response = client.get("/v1/events")
    assert response.status_code == 200
    assert response.json()["status"] == status
    assert response.json()["events"] == []


def test_no_ingestion_or_research_write_route_is_mounted(discovery_client):
    client, _, _ = discovery_client
    assert client.post("/v1/events", json={}).status_code == 405
    assert client.post("/linear/webhook", json={}).status_code == 404
    assert client.post("/v1/research", json={}).status_code == 404


def test_direct_read_handlers_use_persistence(tmp_path):
    store = FixtureStore(tmp_path / "events.json")
    fixture = json.loads(DEFAULT_FIXTURE.read_text(encoding="utf-8"))
    store.seed(fixture, NOW)
    feed = events(store=store, now=NOW)
    assert len(feed["events"]) == 3
    expected = feed["events"][0]
    actual = event_detail(UUID(expected["event_id"]), store=store, now=NOW)
    assert actual["event"] == expected
    assert len(expected["sources"]) == 2
    assert len(expected["performers"]) == 2


def test_direct_read_handler_does_not_turn_missing_store_into_empty(tmp_path):
    with pytest.raises(HTTPException) as caught:
        events(store=FixtureStore(tmp_path / "missing.json"), now=NOW)
    assert caught.value.status_code == 503

def test_pagination_orders_persisted_events_without_duplicates(discovery_client):
    client, store, fixture = discovery_client
    store.seed(fixture, NOW)
    first = client.get("/v1/events?limit=2").json()
    second = client.get("/v1/events?limit=2&offset=2").json()
    assert first["pagination"] == {"limit": 2, "offset": 0, "total": 3, "next_offset": 2}
    assert second["pagination"]["next_offset"] is None
    combined = first["events"] + second["events"]
    assert len({e["event_id"] for e in combined}) == 3
    assert [e["local_date"] for e in combined] == sorted(e["local_date"] for e in combined)
    for query in ("limit=0", "limit=101", "offset=-1", "limit=bad"):
        assert client.get("/v1/events?" + query).status_code == 422


def test_unresolved_records_visible_without_unverified_canonical_artist(discovery_client):
    client, store, fixture = discovery_client
    fixture["batches"][0]["records"][0]["performers"][0]["vendor_artist_id"] = "unknown"
    store.seed(fixture, NOW)
    feed = client.get("/v1/events").json()
    assert feed["review_count"] == 1
    assert feed["unresolved"][0]["reason"] == "unresolved_typed_identity"
    assert len(feed["events"]) == 3
