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


def test_unmapped_venue_is_rejected_without_partial_write(tmp_path: Path) -> None:
    store = FixtureStore(tmp_path / "discovery.json")
    store.seed(fixture(), NOW)
    before = store.read()
    broken = fixture()
    for batch in broken["batches"]:
        batch["logical_key"] += "-new"
    broken["batches"][-1]["records"][-1]["venue_vendor_id"] = "missing"

    with pytest.raises(DiscoveryError, match="unresolved_venue_identity"):
        store.seed(broken, NOW)

    assert store.read() == before


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
