"""Offline tests: synthetic inputs only; no network or application credentials."""
import copy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import UUID

from services.api.app.discovery import (
    DEFAULT_FIXTURE, DiscoveryError, FixtureStore, empty_state, ingest, permitted, timestamp,
)

NOW = timestamp("2026-10-18T07:00:00Z")


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(DEFAULT_FIXTURE.read_text(encoding="utf-8"))
        test_root = DEFAULT_FIXTURE.parents[3] / ".local" / "tests"
        test_root.mkdir(parents=True, exist_ok=True)
        self.directory = TemporaryDirectory(dir=test_root)
        self.addCleanup(self.directory.cleanup)
        self.store = FixtureStore(Path(self.directory.name) / "events.json")

    def seed(self):
        return self.store.seed(self.fixture, NOW)

    def test_multiple_sources_reconcile_to_one_event_and_multi_act_credits_survive(self):
        state = self.seed()
        self.assertEqual(len(state["events"]), 3)
        self.assertEqual(len(state["mappings"]), 4)
        event = self.store.feed(NOW)["events"][0]
        self.assertEqual(len(event["sources"]), 2)
        self.assertEqual([p["name"] for p in event["performers"]], ["Violet Static", "June Arcade"])
        self.assertEqual([p["role"] for p in event["performers"]], ["headliner", "support"])
        UUID(event["event_id"])

    def test_replay_and_reopen_preserve_exact_state_and_identity(self):
        first = self.seed()
        second = self.store.seed(self.fixture, timestamp("2026-10-18T08:00:00Z"))
        self.assertEqual(first, second)
        self.assertEqual(FixtureStore(self.store.path).read(), first)

    def test_changed_batch_under_same_logical_key_is_rejected_atomically(self):
        self.seed()
        before = self.store.path.read_bytes()
        self.fixture["batches"][0]["records"][0]["title"] = "Changed"
        with self.assertRaisesRegex(DiscoveryError, "changed_batch"):
            self.seed()
        self.assertEqual(before, self.store.path.read_bytes())

    def test_unknown_collection_and_retention_rights_block_ingestion(self):
        for use in ("collect", "derived_retention"):
            fixture = copy.deepcopy(self.fixture)
            for source in fixture["sources"]:
                source["permission"]["uses"].pop(use)
            state = ingest(empty_state(), fixture, NOW)
            self.assertEqual(state["events"], {})
            self.assertEqual(state["records"], {})
            self.assertTrue(all(r["status"] == "skipped" for r in state["runs"].values()))

    def test_raw_retention_is_not_required_for_stored_normalized_records(self):
        for source in self.fixture["sources"]:
            source["permission"]["uses"]["raw_retention"] = False
        state = ingest(empty_state(), self.fixture, NOW)
        self.assertEqual(len(state["records"]), 4)
        self.assertTrue(all(r["status"] == "succeeded" for r in state["runs"].values()))

    def test_display_is_separate_and_unknown_denies_read_after_persistence(self):
        for source in self.fixture["sources"]:
            source["permission"]["uses"].pop("display")
        self.seed()
        self.assertEqual(len(self.store.read()["events"]), 3)
        feed = self.store.feed(NOW)
        self.assertEqual(feed["events"], [])
        self.assertEqual(feed["status"], "blocked")

    def test_expiry_revocation_and_future_approval_are_denied(self):
        source = self.fixture["sources"][0]
        self.assertFalse(permitted(source, "train", NOW))
        self.assertFalse(permitted(source, "unknown_operation", NOW))
        for field, value in [("expires_at", "2026-10-17T00:00:00Z"),
                             ("revoked_at", "2026-10-18T06:00:00Z"),
                             ("approved_at", "2026-10-19T00:00:00Z")]:
            altered = copy.deepcopy(source)
            altered["permission"][field] = value
            self.assertFalse(permitted(altered, "display", NOW))

    def test_permission_expiry_is_rechecked_on_read(self):
        self.seed()
        feed = self.store.feed(timestamp("2031-01-01T00:00:00Z"))
        self.assertEqual(feed["events"], [])
        self.assertEqual(feed["status"], "blocked")

    def test_empty_is_distinct_from_failure(self):
        for outcome in ("empty", "failed"):
            fixture = copy.deepcopy(self.fixture)
            for batch in fixture["batches"]:
                batch.update(outcome=outcome, records=[])
            store = FixtureStore(Path(self.directory.name) / (outcome + ".json"))
            store.seed(fixture, NOW)
            feed = store.feed(NOW)
            self.assertEqual(feed["status"], "empty" if outcome == "empty" else "unavailable")
            self.assertEqual(feed["events"], [])
            self.assertTrue(all(r["status"] == outcome for r in feed["collections"]))

    def test_failure_preserves_events_and_does_not_refresh_observation(self):
        self.seed()
        before = self.store.feed(NOW)["events"]
        for batch in self.fixture["batches"]:
            batch.update(logical_key=batch["logical_key"] + "-retry", outcome="failed", records=[])
        self.seed()
        after = self.store.feed(NOW)
        self.assertEqual(after["status"], "partial")
        self.assertEqual(before, after["events"])

    def test_timestamps_freshness_and_tba_survive_reopen(self):
        self.seed()
        events = FixtureStore(self.store.path).feed(NOW)["events"]
        self.assertEqual(timestamp(events[0]["observed_at"]), timestamp("2026-10-18T06:50:00Z"))
        self.assertEqual(events[0]["available_at"], "2026-10-18T06:50:00Z")
        self.assertEqual(events[0]["starts_at"], "2026-11-07T01:00:00Z")
        self.assertFalse(events[0]["stale"])
        self.assertTrue(events[1]["stale"])
        self.assertTrue(events[1]["time_tba"])
        self.assertIsNone(events[1]["starts_at"])
        self.assertEqual(events[2]["status"], "cancelled")

    def test_unresolved_identity_is_not_matched_by_name(self):
        self.fixture["batches"][0]["records"][0]["performers"][0]["vendor_artist_id"] = "unmapped"
        first = self.seed()
        self.assertEqual(len(first["unresolved"]), 1)
        self.assertEqual(len(first["records"]), 3)
        feed = self.store.feed(NOW)
        self.assertEqual(feed["unresolved"][0]["reason"], "unresolved_typed_identity")
        self.assertEqual(feed["review_count"], 1)
        self.assertEqual(self.seed(), first)

    def test_different_known_venue_or_start_does_not_merge(self):
        self.fixture["batches"][1]["records"][0]["starts_at"] = "2026-11-07T02:00:00Z"
        self.assertEqual(len(self.seed()["events"]), 4)

    def test_conflicting_contemporaneous_facts_are_preserved_but_withheld(self):
        self.fixture["batches"][1]["records"][0]["status"] = "cancelled"
        state = self.seed()
        feed = self.store.feed(NOW)
        self.assertEqual(len(state["records"]), 4)
        self.assertEqual(feed["review_count"], 1)
        self.assertEqual(len(feed["events"]), 2)

    def test_postponement_preserves_source_identity(self):
        first = self.seed()
        mapping = next(iter(first["mappings"].values()))
        record = self.fixture["batches"][0]["records"][0]
        record.update(status="postponed", starts_at=None, observed_at="2026-10-18T06:59:00Z", available_at="2026-10-18T06:59:00Z")
        self.fixture["batches"] = [dict(self.fixture["batches"][0], logical_key="postponement", records=[record])]
        self.seed()
        event = next(e for e in self.store.feed(NOW)["events"] if e["event_id"] == mapping["event_id"])
        self.assertEqual(event["status"], "postponed")
        self.assertIsNone(event["starts_at"])

    def test_live_inputs_and_unexpected_secret_fields_are_rejected(self):
        self.fixture["synthetic"] = False
        with self.assertRaises(DiscoveryError):
            self.seed()
        self.fixture["synthetic"] = True
        self.fixture["sources"][0]["api_key"] = "synthetic-secret-canary"
        with self.assertRaises(DiscoveryError) as caught:
            self.seed()
        self.assertNotIn("synthetic-secret-canary", str(caught.exception))

    def test_secrets_are_not_read_and_do_not_enter_store_or_projection(self):
        with patch.dict(os.environ, {"PERPLEXITY_API_KEY": "synthetic-secret-canary",
                                     "TICKETMASTER_API_KEY": "synthetic-secret-canary"}):
            self.seed()
            payload = json.dumps(self.store.feed(NOW)) + self.store.path.read_text()
        self.assertNotIn("synthetic-secret-canary", payload)
        web = DEFAULT_FIXTURE.parents[3] / "apps" / "web" / "app"
        for path in web.rglob("*.tsx"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("PERPLEXITY_API_KEY", text)
            self.assertNotIn("TICKETMASTER_API_KEY", text)

    def test_naive_times_are_rejected(self):
        with self.assertRaises(DiscoveryError):
            timestamp("2026-10-18T07:00:00")

    def test_missing_or_corrupt_store_is_not_empty(self):
        with self.assertRaises(DiscoveryError):
            self.store.feed(NOW)
        self.store.path.write_text("broken")
        with self.assertRaises(DiscoveryError):
            self.store.feed(NOW)


if __name__ == "__main__":
    unittest.main()

