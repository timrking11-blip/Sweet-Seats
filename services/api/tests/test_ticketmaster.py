import json
import logging
import traceback
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest

from app.discovery import USES, normalize, permitted
from app.source_registry import TICKETMASTER_DISCOVERY, planned_source
from app.ticketmaster import (
    ENABLE_FLAG,
    KEY_VARIABLE,
    TicketmasterClient,
    TicketmasterError,
    collect_events,
    map_attraction,
    map_attraction_search,
    map_event,
    map_event_search,
    map_venue,
    map_venue_search,
    redact,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests" / "fixtures" / "ticketmaster"
NOW = datetime(2026, 10, 18, 7, 0, tzinfo=UTC)
FAKE_KEY = "fake-test-key-0123456789"  # Not a credential: never sent anywhere.
ENABLED = {ENABLE_FLAG: "true", KEY_VARIABLE: FAKE_KEY}
RECORD_FIELDS = {"vendor_event_id", "title", "venue_vendor_id", "performers", "starts_at",
                 "local_date", "timezone", "status", "observed_at", "available_at",
                 "source_url", "ticket_url"}


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def approved_source() -> dict:
    source = planned_source(TICKETMASTER_DISCOVERY)
    source["access_status"] = "approved"
    source["permission"].update(terms_version="unit-test-only", evidence_ref="unit test",
                                approved_at="2026-01-01T00:00:00Z",
                                expires_at="2030-01-01T00:00:00Z")
    source["permission"]["uses"]["collect"] = True
    return source


class FakeClock:
    def __init__(self) -> None:
        self.tick = 0.0
        self.wall = NOW
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.tick

    def now(self) -> datetime:
        return self.wall

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.tick += seconds
        self.wall += timedelta(seconds=seconds)


class FakeTransport:
    def __init__(self, *responses: tuple[int, dict, bytes]) -> None:
        self.responses = list(responses)
        self.urls: list[str] = []

    def __call__(self, url: str, timeout: float) -> tuple[int, dict, bytes]:
        self.urls.append(url)
        if len(self.responses) > 1:
            return self.responses.pop(0)
        return self.responses[0]


def ok(payload: dict | None = None, headers: dict | None = None) -> tuple[int, dict, bytes]:
    return 200, headers or {}, json.dumps(payload if payload is not None else {}).encode()


def client(transport: FakeTransport, clock: FakeClock | None = None, **kwargs) -> TicketmasterClient:
    clock = clock or FakeClock()
    return TicketmasterClient(FAKE_KEY, transport=transport, clock=clock.monotonic,
                              wall_clock=clock.now, sleep=clock.sleep, **kwargs)


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args, **kwargs):
        raise AssertionError("network call attempted")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)


# Mapping


def test_multi_act_event_maps_to_source_event_record() -> None:
    mapped = map_event(load("event.json"), NOW)
    record, display = mapped["record"], mapped["display"]

    assert set(record) == RECORD_FIELDS | {"onsale_at"}
    assert record["onsale_at"] == "2026-09-01T14:00:00Z"
    assert record["performers"] == [
        {"vendor_artist_id": "SYNTH-AT-0001", "role": "headliner", "billing_order": 0},
        {"vendor_artist_id": "SYNTH-AT-0002", "role": "support", "billing_order": 1},
        {"vendor_artist_id": "SYNTH-AT-0003", "role": "support", "billing_order": 2},
    ]
    assert record["venue_vendor_id"] == "SYNTH-VN-0001"
    assert record["starts_at"] == "2026-11-14T00:30:00Z"
    assert record["local_date"] == "2026-11-13"
    assert record["timezone"] == "America/New_York"
    assert record["status"] == "scheduled"
    assert record["observed_at"] == record["available_at"] == "2026-10-18T07:00:00Z"
    assert record["ticket_url"] == record["source_url"] == (
        "https://tickets.example.invalid/event/SYNTH-EV-0001")
    assert display["status_code"] == "onsale"
    assert display["local_time"] == "19:30:00"
    assert [a["name"] for a in display["attractions"]] == [
        "Glass Harbor", "Mira Vale", "The Quiet Ferries"]
    assert display["venue"]["name"] == "Ironworks Hall"


def test_price_ranges_are_display_metadata_never_record_fields() -> None:
    mapped = map_event(load("event.json"), NOW)

    assert "price" not in json.dumps(mapped["record"]).lower()
    assert mapped["display"]["price_ranges"] == [
        {"type": "standard", "currency": "USD", "min": 35.0, "max": 65.0}]
    assert mapped["display"]["price_policy"] == "display_only_not_price_history"
    assert "images" not in json.dumps(mapped)


def test_search_maps_tba_cancelled_postponed_and_rescheduled() -> None:
    result = map_event_search(load("events.json"), NOW)
    records = {r["vendor_event_id"]: r for r in result["records"]}
    display = result["display"]

    tba = records["SYNTH-EV-0002"]
    assert tba["starts_at"] is None and tba["local_date"] == "2026-11-20"
    assert tba["timezone"] == "America/New_York"  # Falls back to the venue timezone.
    assert display["SYNTH-EV-0002"]["time_tba"] is True
    assert display["SYNTH-EV-0002"]["start_time_known"] is False

    assert records["SYNTH-EV-0003"]["status"] == "cancelled"
    assert records["SYNTH-EV-0003"]["starts_at"] == "2026-11-21T01:00:00Z"

    postponed = records["SYNTH-EV-0004"]
    assert postponed["status"] == "postponed" and postponed["starts_at"] is None
    assert display["SYNTH-EV-0004"]["date_tba"] is True

    rescheduled = records["SYNTH-EV-0005"]
    assert rescheduled["status"] == "scheduled"
    assert rescheduled["starts_at"] == "2026-12-05T01:00:00Z"
    assert display["SYNTH-EV-0005"]["status_code"] == "rescheduled"
    # An inverted range is dropped rather than repaired.
    assert display["SYNTH-EV-0005"]["price_ranges"] == [
        {"type": "standard", "currency": "USD", "min": 28.5, "max": 28.5}]

    no_time = records["SYNTH-EV-0006"]
    assert no_time["status"] == "scheduled" and no_time["starts_at"] is None
    assert display["SYNTH-EV-0006"]["no_specific_time"] is True

    assert result["skipped"] == [
        {"vendor_event_id": "SYNTH-EV-0007", "error_code": "test_event"},
        {"vendor_event_id": "SYNTH-EV-0008", "error_code": "missing_attraction_credits"},
    ]
    assert result["page"] == {"size": 20, "totalElements": 8, "totalPages": 1, "number": 0}


def test_mapped_records_are_accepted_by_discovery_normalize() -> None:
    result = map_event_search(load("events.json"), NOW)
    artist_ids = {p["vendor_artist_id"] for r in result["records"] for p in r["performers"]}
    venue_ids = {r["venue_vendor_id"] for r in result["records"]}
    source = approved_source()
    source["artist_mappings"] = {a: str(uuid5(NAMESPACE_URL, a)) for a in artist_ids}
    source["venue_mappings"] = {v: str(uuid5(NAMESPACE_URL, v)) for v in venue_ids}
    identities = {
        "artists": {u: {"name": a} for a, u in source["artist_mappings"].items()},
        "venues": {u: {"name": v, "neighborhood": "Test", "timezone": "America/New_York"}
                   for v, u in source["venue_mappings"].items()},
    }

    normalized = [normalize(r, source, identities) for r in result["records"]]

    assert len(normalized) == 6
    assert {n["status"] for n in normalized} == {"scheduled", "cancelled", "postponed"}


def test_venue_and_attraction_responses_map_to_unreviewed_identity_candidates() -> None:
    venues = map_venue_search(load("venues.json"))
    attractions = map_attraction_search(load("attractions.json"))

    assert [v["vendor_venue_id"] for v in venues["venues"]] == ["SYNTH-VN-0001", "SYNTH-VN-0002"]
    assert venues["skipped"] == [{"vendor_venue_id": "SYNTH-VN-0003", "error_code": "test_venue"}]
    assert map_venue(load("venue.json")) == venues["venues"][0]
    assert venues["venues"][0]["postal_code"] == "11211"
    assert {v["review_status"] for v in venues["venues"]} == {"unreviewed"}

    assert [a["name"] for a in attractions["attractions"]] == [
        "Glass Harbor", "Mira Vale", "The Quiet Ferries"]
    assert map_attraction(load("attraction.json")) == attractions["attractions"][0]
    assert attractions["attractions"][0]["genre"] == "Rock"
    assert "image" not in json.dumps(attractions) and "externalLinks" not in json.dumps(attractions)


def test_search_without_embedded_results_is_empty() -> None:
    empty = {"page": {"size": 20, "totalElements": 0, "totalPages": 0, "number": 0}}

    assert map_event_search(empty, NOW)["records"] == []
    assert map_venue_search(empty)["venues"] == []
    assert map_attraction_search(empty)["attractions"] == []


# Registry and permission gate


def test_registry_entry_is_planned_with_every_use_unapproved() -> None:
    source = planned_source(TICKETMASTER_DISCOVERY)

    assert source["access_status"] == "planned"
    assert source["candidate_uses"] == ["collect", "display"]
    assert set(source["permission"]["uses"]) == USES
    assert not any(source["permission"]["uses"].values())
    assert source["permission"]["approved_at"] is None
    assert not any(permitted(source, use, NOW) for use in USES)

    source["permission"]["uses"]["collect"] = True
    assert planned_source(TICKETMASTER_DISCOVERY)["permission"]["uses"]["collect"] is False


def test_permission_denied_makes_no_request(no_network: None) -> None:
    transport = FakeTransport(ok(load("events.json")))

    result = collect_events(planned_source(TICKETMASTER_DISCOVERY), NOW,
                            client=client(transport), env=ENABLED)

    assert result["status"] == "skipped"
    assert result["error_code"] == "permission_denied"
    assert result["records"] == [] and result["network_calls"] == 0
    assert transport.urls == []


def test_expired_or_revoked_permission_is_denied() -> None:
    expired = approved_source()
    expired["permission"]["expires_at"] = "2026-10-01T00:00:00Z"
    revoked = approved_source()
    revoked["permission"]["revoked_at"] = "2026-10-02T00:00:00Z"
    transport = FakeTransport(ok(load("events.json")))

    for source in (expired, revoked):
        result = collect_events(source, NOW, client=client(transport), env=ENABLED)
        assert result["error_code"] == "permission_denied"
    assert transport.urls == []


# Enable flag


@pytest.mark.parametrize("env", [
    {},
    {KEY_VARIABLE: FAKE_KEY},
    {ENABLE_FLAG: "false", KEY_VARIABLE: FAKE_KEY},
    {ENABLE_FLAG: "1", KEY_VARIABLE: FAKE_KEY},
    {ENABLE_FLAG: "true"},
    {ENABLE_FLAG: "true", KEY_VARIABLE: "   "},
])
def test_disabled_flag_makes_no_network_call(env: dict, no_network: None) -> None:
    transport = FakeTransport(ok(load("events.json")))

    assert TicketmasterClient.from_env(env) is None
    result = collect_events(approved_source(), NOW, client=client(transport), env=env)

    assert result["status"] == "skipped"
    assert result["error_code"] == "provider_disabled"
    assert result["network_calls"] == 0 and transport.urls == []


def test_process_environment_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch,
                                                    no_network: None) -> None:
    monkeypatch.delenv(ENABLE_FLAG, raising=False)
    monkeypatch.setenv(KEY_VARIABLE, FAKE_KEY)

    assert TicketmasterClient.from_env() is None
    assert collect_events(approved_source(), NOW)["error_code"] == "provider_disabled"


def test_enabled_and_permitted_collection_maps_a_page(no_network: None) -> None:
    transport = FakeTransport(ok(load("events.json")))

    result = collect_events(approved_source(), NOW, {"classificationName": "music",
                            "city": "New York"}, client=client(transport), env=ENABLED)

    assert result["status"] == "succeeded"
    assert result["network_calls"] == 1 and len(result["records"]) == 6
    assert transport.urls[0].startswith("https://app.ticketmaster.com/discovery/v2/events.json?")
    assert "classificationName=music" in transport.urls[0]
    assert "raw" not in result and "_embedded" not in json.dumps(result)


# Key redaction


def test_transport_errors_never_carry_the_key(caplog: pytest.LogCaptureFixture) -> None:
    def leaky(url: str, timeout: float):
        raise RuntimeError(f"connection reset while fetching {url}")

    tm = client(FakeTransport(ok()))
    tm._transport = leaky
    caplog.set_level(logging.DEBUG, logger="app.ticketmaster")

    with pytest.raises(TicketmasterError) as caught:
        tm.search_events(keyword="glass")

    rendered = "".join(traceback.format_exception(caught.value))
    assert str(caught.value) == "transport_error"
    assert FAKE_KEY not in rendered and FAKE_KEY not in repr(caught.value)
    assert FAKE_KEY not in repr(tm)
    assert FAKE_KEY not in caplog.text and "apikey=[REDACTED]" in caplog.text


def test_http_errors_use_fixed_codes_without_the_key() -> None:
    tm = client(FakeTransport((401, {}, b'{"fault": "invalid key"}')))

    with pytest.raises(TicketmasterError) as caught:
        tm.get_event("SYNTH-EV-0001")

    assert str(caught.value) == "unauthorized"
    assert FAKE_KEY not in "".join(traceback.format_exception(caught.value))


def test_redact_scrubs_key_and_apikey_parameter() -> None:
    text = f"GET /events.json?apikey={FAKE_KEY}&city=NYC and key {FAKE_KEY}; apikey=other"

    scrubbed = redact(text, FAKE_KEY)

    assert FAKE_KEY not in scrubbed and "other" not in scrubbed
    assert "city=NYC" in scrubbed


def test_caller_cannot_inject_parameters_or_endpoints() -> None:
    transport = FakeTransport(ok())
    tm = client(transport)

    with pytest.raises(TicketmasterError, match="unsupported_parameter"):
        tm.search_events(apikey="another")
    with pytest.raises(TicketmasterError, match="unsupported_endpoint"):
        tm.get_event("../../commerce/v2/checkout")
    assert transport.urls == []


# Rate limits


def test_requests_are_throttled_to_five_per_second() -> None:
    clock = FakeClock()
    tm = client(FakeTransport(ok()), clock)

    for _ in range(6):
        tm.search_events()

    assert clock.sleeps == [1.0]
    assert tm.request_count == 6


def test_daily_quota_stops_before_the_request() -> None:
    transport = FakeTransport(ok())
    tm = client(transport, daily_limit=2)

    tm.search_events()
    tm.search_events()
    with pytest.raises(TicketmasterError, match="daily_quota_exhausted"):
        tm.search_events()
    assert len(transport.urls) == 2


def test_429_backs_off_and_honours_retry_after() -> None:
    clock = FakeClock()
    transport = FakeTransport((429, {}, b""), (429, {"Retry-After": "5"}, b""),
                              ok({"page": {"size": 0}}))

    assert client(transport, clock).search_events() == {"page": {"size": 0}}
    assert clock.sleeps == [1.0, 5.0]
    assert len(transport.urls) == 3


def test_persistent_429_fails_with_a_fixed_code() -> None:
    clock = FakeClock()
    transport = FakeTransport((429, {}, b""))

    with pytest.raises(TicketmasterError, match="rate_limited"):
        client(transport, clock, max_retries=2).search_events()
    assert clock.sleeps == [1.0, 2.0]


def test_exhausted_rate_limit_headers_block_until_reset() -> None:
    clock = FakeClock()
    reset_ms = int((NOW + timedelta(hours=3)).timestamp() * 1000)
    headers = {"Rate-Limit": "5000", "Rate-Limit-Available": "0",
               "Rate-Limit-Over": "0", "Rate-Limit-Reset": str(reset_ms)}
    transport = FakeTransport(ok({}, headers))
    tm = client(transport, clock)

    tm.search_events()
    with pytest.raises(TicketmasterError, match="quota_exhausted"):
        tm.search_events()
    assert len(transport.urls) == 1

    clock.wall = NOW + timedelta(hours=3, seconds=1)
    transport.responses = [ok({})]
    tm.search_events()
    assert len(transport.urls) == 2
