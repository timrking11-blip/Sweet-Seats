"""Regression cases for identity review, temporal validation and replay."""
import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from services.api.app.discovery import DEFAULT_FIXTURE, DiscoveryError, FixtureStore, timestamp

NOW = timestamp("2026-10-18T07:00:00Z")


class IncrementTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(DEFAULT_FIXTURE.read_text())
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = FixtureStore(Path(self.directory.name) / "events.json")

    def test_unresolved_is_persistent_idempotent_and_permission_gated(self):
        raw = self.fixture["batches"][0]["records"][0]
        raw["performers"][0]["vendor_artist_id"] = "unknown"
        first = self.store.seed(self.fixture, NOW)
        self.assertEqual(len(first["unresolved"]), 1)
        self.assertEqual(FixtureStore(self.store.path).read(), first)
        self.assertEqual(self.store.seed(self.fixture, NOW), first)
        self.assertEqual(self.store.feed(NOW)["review_count"], 1)
        self.assertEqual(self.store.feed(timestamp("2031-01-01T00:00:00Z"))["unresolved"], [])

    def test_invalid_unresolved_record_still_aborts_atomically(self):
        self.store.seed(self.fixture, NOW)
        before = self.store.path.read_bytes()
        batch = self.fixture["batches"][0]
        batch["logical_key"] += "-invalid"
        raw = batch["records"][0]
        raw["performers"][0]["vendor_artist_id"] = "unknown"
        raw["source_url"] = "https://example.com/real"
        with self.assertRaisesRegex(DiscoveryError, "invalid_synthetic_url"):
            self.store.seed(self.fixture, NOW)
        self.assertEqual(before, self.store.path.read_bytes())

    def test_same_name_artists_keep_different_typed_ids(self):
        artists = list(self.fixture["identities"]["artists"])
        for artist in artists:
            self.fixture["identities"]["artists"][artist]["name"] = "Same Name"
        self.store.seed(self.fixture, NOW)
        event = self.store.feed(NOW)["events"][0]
        self.assertEqual(len({p["artist_id"] for p in event["performers"]}), 2)
        self.assertEqual({p["name"] for p in event["performers"]}, {"Same Name"})

    def test_date_must_agree_with_timezone_and_dst_offset(self):
        raw = self.fixture["batches"][0]["records"][0]
        # UTC next day is still the prior evening in New York.
        raw["local_date"] = "2026-11-07"
        with self.assertRaisesRegex(DiscoveryError, "local_date_timezone_mismatch"):
            self.store.seed(self.fixture, NOW)
        # The fall-back hour occurs twice. Explicit instants remain separate events.
        raw.update(local_date="2026-11-01", starts_at="2026-11-01T01:30:00-04:00")
        other = self.fixture["batches"][1]["records"][0]
        other.update(local_date="2026-11-01", starts_at="2026-11-01T01:30:00-05:00")
        self.assertEqual(len(self.store.seed(self.fixture, NOW)["events"]), 4)

    def test_rescheduled_and_cancelled_use_existing_source_identity(self):
        first = self.store.seed(self.fixture, NOW)
        mapping = next(iter(first["mappings"].values()))
        original = copy.deepcopy(self.fixture["batches"][0]["records"][0])
        for status in ("rescheduled", "cancelled"):
            record = {**original, "status": status, "starts_at": "2026-11-08T01:00:00Z",
                      "local_date": "2026-11-07", "observed_at": "2026-10-18T06:59:00Z",
                      "available_at": "2026-10-18T06:59:00Z"}
            # A later cancel observation must supersede the reschedule.
            if status == "cancelled":
                record.update(observed_at="2026-10-18T07:00:00Z", available_at="2026-10-18T07:00:00Z")
            fixture = {**self.fixture, "batches": [dict(self.fixture["batches"][0],
                       logical_key=status, records=[record])]}
            state = self.store.seed(fixture, NOW)
            self.assertEqual(len(state["events"]), 3)
            event = next(e for e in self.store.feed(NOW)["events"]
                         if e["event_id"] == mapping["event_id"])
            self.assertEqual(event["status"], status)
            self.assertEqual(event["local_date"], "2026-11-07")

    def test_duplicate_observations_do_not_duplicate_records(self):
        batch = self.fixture["batches"][0]
        batch["records"].append(copy.deepcopy(batch["records"][0]))
        first = self.store.seed(self.fixture, NOW)
        self.assertEqual(len(first["records"]), 4)
        self.assertEqual(len(first["events"]), 3)

    def test_ambiguous_event_candidates_are_retained_for_review(self):
        self.store.seed(self.fixture, NOW)
        state = self.store.read()
        mapping_key = self.fixture["sources"][0]["source_id"] + ":event:artist-101"
        event = state["events"][state["mappings"][mapping_key]["event_id"]]
        state["events"]["second-candidate"] = {**event, "event_id": "second-candidate"}
        self.store.path.write_text(json.dumps(state))
        raw = copy.deepcopy(self.fixture["batches"][0]["records"][0])
        raw["vendor_event_id"] = "unknown-occurrence"
        fixture = {**self.fixture, "batches": [dict(self.fixture["batches"][0],
                   logical_key="ambiguous", records=[raw])]}
        self.store.seed(fixture, NOW)
        self.assertEqual(self.store.feed(NOW)["unresolved"][0]["reason"], "ambiguous_event_match")

    def test_crosswalk_reassignment_requires_review(self):
        self.store.seed(self.fixture, NOW)
        mapping = self.fixture["sources"][0]["artist_mappings"]
        mapping["Violet Static"] = mapping["June Arcade"]
        with self.assertRaisesRegex(DiscoveryError, "identity_crosswalk_revision_requires_review"):
            self.store.seed(self.fixture, NOW)

    def test_representative_edge_fixture_replays_exactly(self):
        fixture = json.loads((DEFAULT_FIXTURE.parent / "edge-cases.json").read_text())
        first = self.store.seed(fixture, NOW)
        self.assertEqual(self.store.seed(fixture, NOW), first)
        self.assertEqual((len(first["events"]), len(first["records"]), len(first["unresolved"])),
                         (3, 5, 1))

