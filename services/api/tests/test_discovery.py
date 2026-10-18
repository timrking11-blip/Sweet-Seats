import copy
import json
from datetime import UTC, datetime
from pathlib import Path

from app.discovery import FixtureStore

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

