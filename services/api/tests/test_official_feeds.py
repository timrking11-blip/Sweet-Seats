"""Official calendar adapter, the provider ingestion path and a cross-source lead-time run."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid5

import pytest

from app.discovery import (
    NAMESPACE,
    USES,
    DiscoveryError,
    empty_state,
    ingest_collection,
    lead_time_report,
    project_feed,
)
from app.official_feeds import fetch_feed, map_feed, parse_ics, vendor_key
from app.source_registry import planned_official_calendar, planned_source
from app.ticketmaster import map_event_search

ROOT = Path(__file__).resolve().parents[3]
VENUE_ICS = (ROOT / "tests" / "fixtures" / "official" / "venue.ics").read_text(encoding="utf-8")
TM_EVENTS = json.loads((ROOT / "tests" / "fixtures" / "ticketmaster" / "events.json").read_text())
FEED = {"kind": "venue", "vendor_venue_id": "venue:example-hall",
        "url": "https://hall.example.invalid/calendar.ics"}
OFFICIAL_SEEN = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)
TM_SEEN = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)

ARTIST = str(uuid5(NAMESPACE, "test-artist:glass-harbor"))
SUPPORT_1 = str(uuid5(NAMESPACE, "test-artist:mira-vale"))
SUPPORT_2 = str(uuid5(NAMESPACE, "test-artist:quiet-ferries"))
VENUE = str(uuid5(NAMESPACE, "test-venue:example-hall"))


def approve(source: dict) -> dict:
    """Test-only grant. Real grants are owner-approved records, never test fixtures."""
    source["access_status"] = "approved"
    source["permission"].update(
        terms_version="test-terms-1", evidence_ref="unit test grant",
        approved_at="2026-01-01T00:00:00+00:00", expires_at="2027-01-01T00:00:00+00:00",
        uses={use: use in {"collect", "display", "derived_retention"} for use in USES})
    return source


def identities_state() -> dict:
    state = empty_state()
    state["identities"]["artists"] = {ARTIST: {"name": "Glass Harbor"},
                                      SUPPORT_1: {"name": "Mira Vale"},
                                      SUPPORT_2: {"name": "The Quiet Ferries"}}
    state["identities"]["venues"] = {VENUE: {"name": "Example Hall", "neighborhood": "Test",
                                             "timezone": "America/New_York"}}
    return state


def sources() -> tuple[dict, dict]:
    tm = approve(planned_source("ticketmaster-discovery"))
    tm["artist_mappings"] = {"SYNTH-AT-0001": ARTIST, "SYNTH-AT-0002": SUPPORT_1,
                             "SYNTH-AT-0003": SUPPORT_2}
    tm["venue_mappings"] = {"SYNTH-VN-0001": VENUE}
    hall = approve(planned_official_calendar(
        "official-example-hall", "Example Hall calendar", FEED["url"]))
    hall["artist_mappings"] = {vendor_key("name", "Glass Harbor"): ARTIST,
                               vendor_key("name", "Mira Vale"): SUPPORT_1,
                               vendor_key("name", "The Quiet Ferries"): SUPPORT_2}
    hall["venue_mappings"] = {FEED["vendor_venue_id"]: VENUE}
    return tm, hall


def test_parse_ics_unfolds_lines_and_ignores_nested_components():
    events = parse_ics(VENUE_ICS)
    assert len(events) == 5
    assert events[1]["SUMMARY"][1] == "Paper Lanterns Collective"
    assert "ACTION" not in events[0]  # VALARM properties stay inside the alarm.


def test_map_feed_converts_zones_and_skips_malformed_events():
    mapped = map_feed(VENUE_ICS, FEED, OFFICIAL_SEEN)
    by_uid = {r["vendor_event_id"]: r for r in mapped["records"]}
    shared = by_uid["hall-2026-11-13-glass-harbor@hall.example.invalid"]
    # 19:30 in New York on 13 Nov is 00:30 UTC on 14 Nov: the same instant Ticketmaster gives.
    assert shared["starts_at"] == "2026-11-14T00:30:00Z"
    assert shared["local_date"] == "2026-11-13"
    assert [p["vendor_artist_id"] for p in shared["performers"]] == [
        "name:glass-harbor", "name:mira-vale", "name:the-quiet-ferries"]
    assert by_uid["hall-2026-11-20-paper-lanterns@hall.example.invalid"]["status"] == "cancelled"
    nye = by_uid["hall-2026-12-31-nye@hall.example.invalid"]
    assert (nye["starts_at"], nye["local_date"]) == (None, "2026-12-31")
    assert mapped["skipped"] == [{"vendor_event_id": "hall-broken@hall.example.invalid",
                                  "error_code": "missing_start"}]
    assert set(mapped["display"]["hall-2026-11-13-glass-harbor@hall.example.invalid"]) == {
        "claimed_published_at", "last_modified"}


def test_fetch_feed_makes_no_request_without_permission_or_enable_flag():
    calls = []

    def transport(*args):
        calls.append(args)
        return 200, {}, VENUE_ICS.encode()

    planned = planned_official_calendar("official-x", "X", FEED["url"])
    assert fetch_feed(planned, FEED, NOW, transport=transport,
                      env={"SWEET_SEATS_OFFICIAL_FEEDS_ENABLED": "true"})["error_code"] == "permission_denied"
    _, hall = sources()
    assert fetch_feed(hall, FEED, NOW, transport=transport, env={})["error_code"] == "provider_disabled"
    assert calls == []


def test_fetch_feed_sends_validators_and_reports_not_modified():
    _, hall = sources()
    seen = {}

    def transport(url, headers, timeout):
        seen.update(headers)
        return 304, {"ETag": '"v2"'}, b""

    result = fetch_feed(hall, FEED, NOW, validators={"etag": '"v1"', "last_modified": "Wed, 19 Aug 2026"},
                        transport=transport, env={"SWEET_SEATS_OFFICIAL_FEEDS_ENABLED": "true"})
    assert seen == {"If-None-Match": '"v1"', "If-Modified-Since": "Wed, 19 Aug 2026"}
    assert (result["status"], result["validators"]["etag"], result["records"]) == ("not_modified", '"v2"', [])


def test_fetch_feed_rejects_oversized_and_non_https():
    _, hall = sources()
    env = {"SWEET_SEATS_OFFICIAL_FEEDS_ENABLED": "true"}
    big = fetch_feed(hall, FEED, NOW, env=env,
                     transport=lambda *a: (200, {}, b"x" * 2_000_001))
    assert big["error_code"] == "response_too_large"
    with pytest.raises(DiscoveryError, match="invalid_provider_url"):
        fetch_feed(hall, {**FEED, "url": "http://hall.example.invalid/c.ics"}, NOW, env=env,
                   transport=lambda *a: (200, {}, b""))


def test_provider_path_takes_permissions_from_the_registry_not_the_payload():
    tm, _ = sources()
    with pytest.raises(DiscoveryError, match="provider_source_required"):
        ingest_collection(identities_state(), {**tm, "kind": "synthetic"}, "k", {"status": "empty"}, NOW)
    planned = planned_source("ticketmaster-discovery")  # Every use false.
    collection = {"status": "succeeded",
                  "records": map_event_search(TM_EVENTS, TM_SEEN)["records"]}
    state = ingest_collection(identities_state(), planned, "tm:1", collection, NOW)
    assert state["records"] == {} and state["unresolved"] == {}
    assert [r["status"] for r in state["runs"].values()] == ["skipped"]


def test_official_calendar_beats_ticketmaster_in_the_lead_time_report():
    tm, hall = sources()
    official = {"status": "succeeded", "records": map_feed(VENUE_ICS, FEED, OFFICIAL_SEEN)["records"]}
    listing = {"status": "succeeded", "records": map_event_search(TM_EVENTS, TM_SEEN)["records"]}

    state = ingest_collection(identities_state(), hall, "hall:2026-08-20T15", official, NOW)
    state = ingest_collection(state, tm, "tm:2026-08-22T12", listing, NOW)

    feed = project_feed(state, NOW)
    shared = [e for e in feed["events"] if len(e["sources"]) == 2]
    assert len(shared) == 1 and shared[0]["starts_at"] == "2026-11-14T00:30:00Z"
    # Unmapped acts and venues wait in review; nothing was matched by name.
    assert feed["review_count"] > 0

    report = {s["name"]: s for s in lead_time_report(state, NOW)["sources"]}
    calendar, listing_api = report["Example Hall calendar"], report["Ticketmaster Discovery API v2"]
    assert (calendar["shared_events"], calendar["median_lag_minutes"]) == (1, 0)
    # Seen 2 days 21 hours later through the listing API.
    assert listing_api["median_lag_minutes"] == (TM_SEEN - OFFICIAL_SEEN).total_seconds() / 60
    # The latest observation (Ticketmaster) carries the public on-sale time.
    assert shared[0]["onsale_at"] == "2026-09-01T14:00:00Z"
