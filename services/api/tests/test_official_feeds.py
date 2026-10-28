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
from app.official_feeds import (
    MAX_REDIRECTS,
    fetch_feed,
    map_feed,
    parse_ics,
    public_address,
    vendor_key,
)
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
ENABLED = {"SWEET_SEATS_OFFICIAL_FEEDS_ENABLED": "true"}
PUBLIC_IP = "93.184.215.14"  # A public address; tests never connect to it.


def public_dns(host, port):
    return [PUBLIC_IP]

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

    def transport(url, address, headers, timeout):
        seen.update(headers)
        return 304, {"ETag": '"v2"'}, b""

    result = fetch_feed(hall, FEED, NOW, validators={"etag": '"v1"', "last_modified": "Wed, 19 Aug 2026"},
                        transport=transport, resolver=public_dns, env=ENABLED)
    assert seen == {"If-None-Match": '"v1"', "If-Modified-Since": "Wed, 19 Aug 2026"}
    assert (result["status"], result["validators"]["etag"], result["records"]) == ("not_modified", '"v2"', [])


def test_fetch_feed_rejects_oversized_and_non_https():
    _, hall = sources()
    big = fetch_feed(hall, FEED, NOW, env=ENABLED, resolver=public_dns,
                     transport=lambda *a: (200, {}, b"x" * 2_000_001))
    assert big["error_code"] == "response_too_large"
    plain = fetch_feed(hall, {**FEED, "url": "http://hall.example.invalid/c.ics"}, NOW,
                       env=ENABLED, resolver=public_dns, transport=lambda *a: (200, {}, b""))
    assert (plain["status"], plain["error_code"], plain["network_calls"]) == (
        "skipped", "invalid_provider_url", 0)


class Recorder:
    """A fake transport answering from a list of responses and recording each request."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, url, address, headers, timeout):
        self.requests.append((url, address))
        return self.responses.pop(0)


def redirect(location, status=302):
    return status, {"Location": location}, b""


@pytest.mark.parametrize("address", [
    "10.0.0.5", "172.16.0.1", "192.168.1.1",  # private
    "127.0.0.1", "::1",  # loopback
    "169.254.169.254", "fe80::1",  # link-local, including cloud metadata
    "224.0.0.1", "ff02::1",  # multicast
    "0.0.0.0", "::",  # unspecified
    "240.0.0.1", "255.255.255.255",  # reserved, broadcast
    "100.64.0.1", "192.0.2.10", "fc00::1", "fec0::1",  # shared, documentation, ULA, site-local
    "::ffff:127.0.0.1", "::ffff:93.184.215.14",  # IPv4-mapped, even of a public address
    "2002:a00:1::1", "2001::a00:1", "64:ff9b::a00:1",  # 6to4, Teredo, NAT64
    "fe80::1%1", "::10.0.0.5", "::8.8.8.8", "not-an-address",  # scoped, IPv4-compatible
])
def test_public_address_rejects_every_non_public_form(address):
    assert not public_address(address)


@pytest.mark.parametrize("address", [PUBLIC_IP, "2606:4700:4700::1111"])
def test_public_address_accepts_global_unicast(address):
    assert public_address(address)


@pytest.mark.parametrize("answers", [
    ["10.0.0.5"], ["169.254.169.254"], ["::ffff:127.0.0.1"],
    [PUBLIC_IP, "127.0.0.1"],  # One private answer is enough to refuse.
])
def test_fetch_feed_refuses_an_approved_host_that_resolves_privately(answers):
    _, hall = sources()
    transport = Recorder((200, {}, VENUE_ICS.encode()))
    result = fetch_feed(hall, FEED, NOW, env=ENABLED, transport=transport,
                        resolver=lambda host, port: answers)
    assert (result["status"], result["error_code"]) == ("failed", "non_public_address")
    assert transport.requests == [] and result["network_calls"] == 0


@pytest.mark.parametrize("url", ["https://127.0.0.1/calendar.ics", "https://169.254.169.254/latest",
                                 "https://[::1]/calendar.ics", "https://localhost/calendar.ics"])
def test_fetch_feed_refuses_a_private_registry_host(url):
    # Even an owner-approved URL is refused when its host is not public. The real
    # resolver is used; IP literals and localhost resolve without leaving the machine.
    hall = approve(planned_official_calendar("official-private", "Private", url))
    transport = Recorder((200, {}, VENUE_ICS.encode()))
    result = fetch_feed(hall, {**FEED, "url": url}, NOW, env=ENABLED, transport=transport)
    assert result["error_code"] in {"non_public_address", "dns_error"}
    assert transport.requests == []


@pytest.mark.parametrize("url,code", [
    ("https://other.example.invalid/calendar.ics", "host_not_approved"),
    ("https://10.0.0.5/calendar.ics", "host_not_approved"),
    ("https://hall.example.invalid:8443/calendar.ics", "port_not_allowed"),
])
def test_fetch_feed_requests_only_the_approved_host(url, code):
    _, hall = sources()
    transport = Recorder((200, {}, VENUE_ICS.encode()))
    result = fetch_feed(hall, {**FEED, "url": url}, NOW, env=ENABLED, transport=transport,
                        resolver=public_dns)
    assert (result["status"], result["error_code"]) == ("skipped", code)
    assert transport.requests == []


@pytest.mark.parametrize("location,code", [
    ("https://other.example.invalid/calendar.ics", "host_not_approved"),
    ("https://127.0.0.1/calendar.ics", "host_not_approved"),
    ("https://169.254.169.254/latest/meta-data/", "host_not_approved"),
    ("https://[::ffff:10.0.0.5]/calendar.ics", "host_not_approved"),
    ("http://hall.example.invalid/calendar.ics", "invalid_provider_url"),
    ("https://user:pw@hall.example.invalid/calendar.ics", "invalid_provider_url"),
    ("https://hall.example.invalid:8443/calendar.ics", "port_not_allowed"),
])
def test_fetch_feed_refuses_redirects_off_the_approved_host(location, code):
    _, hall = sources()
    transport = Recorder(redirect(location), (200, {}, VENUE_ICS.encode()))
    result = fetch_feed(hall, FEED, NOW, env=ENABLED, transport=transport, resolver=public_dns)
    assert (result["status"], result["error_code"]) == ("failed", code)
    assert len(transport.requests) == 1 and result["network_calls"] == 1


def test_fetch_feed_rechecks_the_address_on_every_redirect():
    # The approved host re-resolves to a private address between hops (DNS rebinding).
    _, hall = sources()
    answers = [[PUBLIC_IP], ["10.0.0.5"]]
    transport = Recorder(redirect("/moved.ics"), (200, {}, VENUE_ICS.encode()))
    result = fetch_feed(hall, FEED, NOW, env=ENABLED, transport=transport,
                        resolver=lambda host, port: answers.pop(0))
    assert (result["error_code"], result["network_calls"]) == ("non_public_address", 1)
    assert len(transport.requests) == 1


def test_fetch_feed_follows_a_few_same_host_redirects_then_stops():
    _, hall = sources()
    transport = Recorder(redirect("/v2/calendar.ics", 301), (200, {}, VENUE_ICS.encode()))
    result = fetch_feed(hall, FEED, NOW, env=ENABLED, transport=transport, resolver=public_dns)
    assert (result["status"], result["network_calls"]) == ("succeeded", 2)
    assert transport.requests == [(FEED["url"], PUBLIC_IP),
                                  ("https://hall.example.invalid/v2/calendar.ics", PUBLIC_IP)]

    loop = Recorder(*[redirect("/again.ics")] * (MAX_REDIRECTS + 2))
    result = fetch_feed(hall, FEED, NOW, env=ENABLED, transport=loop, resolver=public_dns)
    assert (result["error_code"], result["network_calls"]) == ("too_many_redirects", MAX_REDIRECTS + 1)
    missing = fetch_feed(hall, FEED, NOW, env=ENABLED, transport=Recorder((302, {}, b"")),
                         resolver=public_dns)
    assert missing["error_code"] == "redirect_without_location"


def test_default_transport_connects_only_to_the_checked_address(monkeypatch):
    # The connection is pinned to the address that passed the check, so a second DNS
    # lookup cannot send it elsewhere. No real connection is made.
    from app import official_feeds

    dialed = []

    def create_connection(address, timeout=None, *args, **kwargs):
        dialed.append(address)
        raise OSError("refused")

    def no_lookup(*args, **kwargs):
        raise AssertionError("the connection must not resolve the host again")

    monkeypatch.setattr(official_feeds.socket, "create_connection", create_connection)
    monkeypatch.setattr(official_feeds.socket, "getaddrinfo", no_lookup)
    _, hall = sources()
    result = fetch_feed(hall, FEED, NOW, env=ENABLED, resolver=public_dns)
    assert (result["error_code"], result["network_calls"]) == ("network_error", 1)
    assert dialed == [(PUBLIC_IP, 443)]


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
