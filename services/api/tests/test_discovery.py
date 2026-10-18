import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.discovery import DiscoveryError, FixtureStore

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "discovery" / "nyc.json"
NOW = datetime(2026, 10, 18, 7, 0, tzinfo=UTC)


def fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_synthetic_sources_reconcile_to_a_provenanced_feed(tmp_path: Path) -> None:
    store = FixtureStore(tmp_path / "discovery.json")

    seeded = store.seed(fixture(), NOW)
    feed = store.feed(NOW)

    assert seeded["synthetic"] is True
    assert len(seeded["records"]) == 4
    assert len(feed["events"]) == 3
    shared_event = next(event for event in feed["events"] if event["title"] == "Violet Static + June Arcade")
    assert len(shared_event["sources"]) == 2
    assert shared_event["ticket_url"] is None
    assert feed["mode"] == "synthetic"


def test_display_permission_fails_closed_without_removing_audit_history(tmp_path: Path) -> None:
    blocked = copy.deepcopy(fixture())
    for source in blocked["sources"]:
        source["permission"]["uses"]["display"] = False
    store = FixtureStore(tmp_path / "discovery.json")

    store.seed(blocked, NOW)
    feed = store.feed(NOW)

    assert len(store.read()["records"]) == 4
    assert feed["events"] == []
    assert feed["status"] == "blocked"


def test_duplicate_mapped_credit_is_rejected_before_unresolved_identity(tmp_path: Path) -> None:
    data = fixture()
    source = data["sources"][0]
    source["artist_mappings"]["Violet Static alias"] = source["artist_mappings"]["Violet Static"]
    record = data["batches"][0]["records"][0]
    headliner = record["performers"][0]
    record["performers"] = [
        headliner,
        {**headliner, "vendor_artist_id": "Violet Static alias", "billing_order": 1},
        {"vendor_artist_id": "unmapped-support", "role": "support", "billing_order": 2},
    ]
    store = FixtureStore(tmp_path / "discovery.json")

    with pytest.raises(DiscoveryError, match="duplicate_performer_credit"):
        store.seed(data, NOW)


def test_unmapped_venue_is_sent_to_review_not_rejected(tmp_path: Path) -> None:
    data = fixture()
    data["batches"][-1]["records"][-1]["venue_vendor_id"] = "missing"
    store = FixtureStore(tmp_path / "discovery.json")

    state = store.seed(data, NOW)
    feed = store.feed(NOW)

    assert len(state["records"]) == 3
    assert [u["reason"] for u in feed["unresolved"]] == ["unresolved_venue_identity"]
    assert feed["review_count"] == 1
    # No canonical event is created for it, and no venue is guessed by name.
    assert len(feed["events"]) == 2


def test_permission_withheld_unresolved_only_feed_is_blocked(tmp_path: Path) -> None:
    data = fixture()
    for source in data["sources"]:
        source["artist_mappings"] = {}
        source["permission"]["uses"]["display"] = False
    store = FixtureStore(tmp_path / "discovery.json")

    store.seed(data, NOW)
    feed = store.feed(NOW)

    assert feed["events"] == []
    assert feed["unresolved"] == []
    assert feed["status"] == "blocked"


def test_lead_time_report_credits_the_first_source_and_measures_lag(tmp_path: Path) -> None:
    from app.discovery import lead_time_report

    data = fixture()
    venue_batch = next(b for b in data["batches"] if b["logical_key"].startswith("demo-venue"))
    shared = next(r for r in venue_batch["records"] if r["vendor_event_id"] == "venue-202")
    shared["observed_at"] = shared["available_at"] = "2026-10-18T06:55:00Z"
    later = datetime(2026, 10, 18, 7, 30, tzinfo=UTC)
    state = FixtureStore(tmp_path / "discovery.json").seed(data, later)

    report = lead_time_report(state, later)
    by_name = {s["name"]: s for s in report["sources"]}
    assert report["events"] == 3
    artist, venue = by_name["Synthetic artist calendar"], by_name["Synthetic venue calendar"]
    assert (artist["events_seen"], artist["events_first"], artist["shared_events"]) == (2, 2, 1)
    assert artist["median_lag_minutes"] == 0
    assert (venue["events_seen"], venue["events_first"]) == (2, 1)
    assert venue["median_lag_minutes"] == 5


def test_lead_time_report_ties_and_revoked_sources(tmp_path: Path) -> None:
    from app.discovery import lead_time_report

    state = FixtureStore(tmp_path / "discovery.json").seed(fixture(), NOW)
    report = lead_time_report(state, NOW)
    assert all(s["events_first"] == s["events_seen"] for s in report["sources"])

    venue = next(s for s in state["sources"].values() if s["name"] == "Synthetic venue calendar")
    venue["permission"]["revoked_at"] = "2026-10-18T06:59:00Z"
    names = {s["name"] for s in lead_time_report(state, NOW)["sources"]}
    assert names == {"Synthetic artist calendar"}
