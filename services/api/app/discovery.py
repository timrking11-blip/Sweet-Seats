"""Offline discovery slice (SS-DATA-0.1 / SS-ADR-002, 003, 004).

Only synthetic fixtures are accepted. The JSON store is a single-writer development
artifact, not a replacement for the canonical PostgreSQL database. No network I/O.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid5

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STORE = ROOT / ".local" / "discovery.json"
DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "discovery" / "nyc.json"
NAMESPACE = UUID("8b4205ed-5ed2-4956-980a-85191120abe1")
USES = {"collect", "display", "raw_retention", "derived_retention", "feature", "train", "test"}


class DiscoveryError(ValueError):
    """Messages are fixed codes: never echo payloads or credentials."""


def timestamp(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None:
            raise ValueError
        return result.astimezone(UTC)
    except (TypeError, ValueError, AttributeError) as exc:
        raise DiscoveryError("invalid_zoned_timestamp") from exc


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def identifier(value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise DiscoveryError("invalid_uuid") from exc


def permitted(source: dict, use: str, now: datetime) -> bool:
    """Distinct uses; unknown, expired, future or revoked grants fail closed."""
    p = source.get("permission", {})
    try:
        return bool(
            use in USES
            and source.get("access_status") == "approved"
            and p.get("uses", {}).get(use) is True
            and p.get("evidence_ref")
            and p.get("terms_version")
            and not p.get("revoked_at")
            and timestamp(p["approved_at"]) <= now < timestamp(p["expires_at"])
        )
    except (KeyError, DiscoveryError):
        return False


def _text(value: object) -> str:
    if not isinstance(value, str) or not 0 < len(value.strip()) <= 300:
        raise DiscoveryError("invalid_text")
    return value.strip()


def _demo_url(value: str) -> str:
    # Reserved .invalid domains make synthetic links unambiguously non-operational.
    from urllib.parse import urlsplit

    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not (parsed.hostname or "").endswith(".invalid")
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise DiscoveryError("invalid_synthetic_url")
    return value


def normalize(record: dict, source: dict, identities: dict) -> dict:
    fields = {"vendor_event_id", "title", "venue_vendor_id", "performers", "starts_at",
              "local_date", "timezone", "status", "observed_at", "available_at",
              "source_url", "ticket_url"}
    if set(record) != fields:
        raise DiscoveryError("unexpected_record_fields")
    if record["timezone"] != "America/New_York":
        raise DiscoveryError("unsupported_fixture_timezone")
    date.fromisoformat(record["local_date"])
    if record["starts_at"] is not None:
        timestamp(record["starts_at"])
    observed, available = timestamp(record["observed_at"]), timestamp(record["available_at"])
    if observed > available:
        raise DiscoveryError("availability_before_observation")
    if record["status"] not in {"scheduled", "postponed", "cancelled", "unknown"}:
        raise DiscoveryError("invalid_event_status")
    try:
        venue_id = source["venue_mappings"][record["venue_vendor_id"]]
        venue = identities["venues"][identifier(venue_id)]
        performers = []
        for credit in record["performers"]:
            if set(credit) != {"vendor_artist_id", "role", "billing_order"}:
                raise DiscoveryError("unexpected_credit_fields")
            artist_id = identifier(source["artist_mappings"][credit["vendor_artist_id"]])
            identities["artists"][artist_id]
            if (credit["role"] not in {"headliner", "support", "performer"}
                    or type(credit["billing_order"]) is not int or credit["billing_order"] < 0):
                raise DiscoveryError("invalid_credit")
            performers.append({"artist_id": artist_id, "role": credit["role"],
                               "billing_order": credit["billing_order"]})
    except (KeyError, TypeError) as exc:
        raise DiscoveryError("unresolved_typed_identity") from exc
    if venue["timezone"] != record["timezone"] or not performers:
        raise DiscoveryError("invalid_venue_or_credits")
    if len({(p["artist_id"], p["role"]) for p in performers}) != len(performers):
        raise DiscoveryError("duplicate_performer_credit")
    return {
        **record, "vendor_event_id": _text(record["vendor_event_id"]),
        "title": _text(record["title"]), "venue_id": venue_id, "performers": performers,
        "source_url": _demo_url(record["source_url"]),
        "ticket_url": _demo_url(record["ticket_url"]) if record["ticket_url"] else None,
        "source_id": identifier(source["source_id"]),
        "permission_id": identifier(source["permission"]["permission_id"]),
        "adapter_version": source["adapter_version"],
    }


def empty_state() -> dict:
    return {"version": "SS-DISCOVERY-DEMO-0.1", "synthetic": True, "sources": {},
            "identities": {"artists": {}, "venues": {}}, "events": {}, "mappings": {},
            "records": {}, "runs": {}}


def ingest(state: dict, fixture: dict, now: datetime) -> dict:
    """Transactional in memory: validate everything before an atomic store replacement.

    Cross-source automatic matching requires reviewed venue/artist UUID mappings,
    exact known start time and the same headliner set. Names are never identity keys.
    Date-only records stay separate until explicitly reconciled.
    """
    if fixture.get("synthetic") is not True or fixture.get("version") != "SS-DISCOVERY-DEMO-0.1":
        raise DiscoveryError("synthetic_fixture_required")
    if set(fixture) != {"version", "synthetic", "identities", "sources", "batches"}:
        raise DiscoveryError("unexpected_fixture_fields")
    result = copy.deepcopy(state)
    identities = fixture["identities"]
    for kind in ("artists", "venues"):
        for key, entity in identities[kind].items():
            identifier(key)
            fields = {"name"} if kind == "artists" else {"name", "neighborhood", "timezone"}
            if set(entity) != fields:
                raise DiscoveryError("unexpected_identity_fields")
            _text(entity["name"])
            if key in result["identities"][kind] and result["identities"][kind][key] != entity:
                raise DiscoveryError("identity_revision_requires_review")
        result["identities"][kind].update(identities[kind])
    sources = {}
    for source in fixture["sources"]:
        if set(source) != {"source_id", "name", "kind", "access_status", "adapter_version",
                           "artist_mappings", "venue_mappings", "permission"}:
            raise DiscoveryError("unexpected_source_fields")
        if set(source["permission"]) != {"permission_id", "terms_version", "evidence_ref",
                                         "approved_at", "expires_at", "revoked_at", "uses"}:
            raise DiscoveryError("unexpected_permission_fields")
        if not set(source["permission"]["uses"]).issubset(USES):
            raise DiscoveryError("unexpected_use")
        source_id = identifier(source["source_id"])
        if source_id in sources or source.get("kind") != "synthetic":
            raise DiscoveryError("synthetic_unique_source_required")
        _text(source["name"])
        _text(source["adapter_version"])
        identifier(source["permission"]["permission_id"])
        sources[source_id] = source
    result["sources"].update(sources)
    for batch in fixture["batches"]:
        if set(batch) != {"source_id", "logical_key", "outcome", "records"}:
            raise DiscoveryError("unexpected_batch_fields")
        source = sources[batch["source_id"]]
        logical_key = _text(batch["logical_key"])
        run_key = source["source_id"] + ":" + logical_key
        allowed = all(permitted(source, use, now) for use in
                      ("collect", "raw_retention", "derived_retention"))
        # A skipped run retains only its operational identity, not a payload-derived hash.
        fingerprint = digest(batch) if allowed else digest([source["source_id"], logical_key, "skipped"])
        if run_key in result["runs"]:
            if result["runs"][run_key]["digest"] != fingerprint:
                raise DiscoveryError("changed_batch_at_same_logical_key")
            continue
        outcome = batch["outcome"]
        if outcome not in {"succeeded", "empty", "failed"}:
            raise DiscoveryError("invalid_collection_outcome")
        if (outcome == "succeeded") != bool(batch["records"]):
            raise DiscoveryError("collection_outcome_record_mismatch")
        run = {"source_id": source["source_id"], "logical_key": logical_key,
               "status": outcome if allowed else "skipped", "digest": fingerprint,
               "item_count": 0, "finished_at": now.isoformat(),
               "error_code": "provider_failure" if outcome == "failed" else None}
        result["runs"][run_key] = run
        if not allowed or outcome != "succeeded":
            continue
        for raw in batch["records"]:
            record = normalize(raw, source, result["identities"])
            if timestamp(record["available_at"]) > now:
                raise DiscoveryError("future_observation")
            p = source["permission"]
            if not (timestamp(p["approved_at"]) <= timestamp(record["observed_at"])
                    < timestamp(p["expires_at"])):
                raise DiscoveryError("observation_outside_permission")
            mapping_key = source["source_id"] + ":event:" + record["vendor_event_id"]
            headliners = sorted(p["artist_id"] for p in record["performers"]
                                if p["role"] == "headliner")
            match_key = digest([record["venue_id"], timestamp(record["starts_at"]).isoformat(),
                                headliners]) if record["starts_at"] and headliners else None
            event_id = result["mappings"].get(mapping_key, {}).get("event_id")
            if event_id is None:
                matches = [e["event_id"] for e in result["events"].values()
                           if match_key and e["match_key"] == match_key]
                if len(matches) > 1:
                    raise DiscoveryError("ambiguous_event_match")
                event_id = matches[0] if matches else str(uuid5(NAMESPACE, mapping_key))
            result["events"][event_id] = {"event_id": event_id, "match_key": match_key}
            result["mappings"][mapping_key] = {
                "source_id": source["source_id"], "record_type": "event",
                "vendor_id": record["vendor_event_id"], "event_id": event_id,
                "mapping_method": "known_identity_exact_occurrence" if match_key else "source_identity",
            }
            record_id = str(uuid5(NAMESPACE, digest(record)))
            result["records"][record_id] = {
                **record, "source_record_id": record_id, "event_id": event_id,
                "payload_hash": digest(raw), "collection_run_key": run_key,
            }
            run["item_count"] += 1
    return result


class FixtureStore:
    def __init__(self, path: Path = DEFAULT_STORE):
        self.path = Path(path)

    def read(self) -> dict:
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
            if (state.get("version") != "SS-DISCOVERY-DEMO-0.1"
                    or state.get("synthetic") is not True):
                raise DiscoveryError("invalid_store")
            return state
        except FileNotFoundError:
            raise DiscoveryError("store_not_seeded") from None
        except (OSError, ValueError, AttributeError):
            raise DiscoveryError("store_unavailable") from None

    def seed(self, fixture: dict, now: datetime) -> dict:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_suffix(".lock")
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise DiscoveryError("store_writer_busy") from None
        temporary = None
        try:
            os.close(fd)
            state = self.read() if self.path.exists() else empty_state()
            state = ingest(state, fixture, now)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(state, handle, sort_keys=True, indent=2)
            os.replace(temporary, self.path)
            return state
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
            lock.unlink()

    def feed(self, now: datetime) -> dict:
        state = self.read()
        grouped: dict[str, list[dict]] = {}
        for record in state["records"].values():
            source = state["sources"][record["source_id"]]
            if (all(permitted(source, use, now) for use in ("display", "raw_retention", "derived_retention"))
                    and record["permission_id"] == source["permission"]["permission_id"]):
                grouped.setdefault(record["event_id"], []).append(record)
        events = []
        review_count = 0
        for event_id, records in grouped.items():
            records.sort(key=lambda r: (timestamp(r["available_at"]), r["source_record_id"]))
            # Historical observations remain stored, but cannot resurrect removed credits.
            newest_by_source = {(r["source_id"], r["vendor_event_id"]): r for r in records}
            records = sorted(newest_by_source.values(), key=lambda r: (
                timestamp(r["available_at"]), r["source_record_id"]))
            latest = records[-1]
            contemporaneous = [r for r in records if timestamp(r["available_at"])
                               == timestamp(latest["available_at"])]
            fact_keys = ("venue_id", "starts_at", "local_date", "status")
            if len({digest({k: r[k] for k in fact_keys}) for r in contemporaneous}) > 1:
                # Preserve conflicting observations but do not invent a source winner.
                review_count += 1
                continue
            # Only currently permitted evidence contributes to this projection.
            credits = {(p["artist_id"], p["role"]): p for r in records for p in r["performers"]}
            performers = [{**p, "name": state["identities"]["artists"][p["artist_id"]]["name"]}
                          for p in sorted(credits.values(), key=lambda p: (p["billing_order"], p["artist_id"]))]
            observed = max(timestamp(r["observed_at"]) for r in records)
            fresh_until = observed + timedelta(hours=24)  # DEMO rule, not a production SLA.
            provenance = [{key: r[key] for key in ("source_id", "source_record_id", "source_url",
                          "observed_at", "available_at", "permission_id", "adapter_version", "payload_hash")}
                          | {"name": state["sources"][r["source_id"]]["name"]} for r in records]
            events.append({"event_id": event_id, "title": latest["title"],
                           "venue": {"venue_id": latest["venue_id"], **state["identities"]["venues"][latest["venue_id"]]},
                           "performers": performers, "starts_at": latest["starts_at"],
                           "local_date": latest["local_date"], "timezone": latest["timezone"],
                           "time_tba": latest["starts_at"] is None, "status": latest["status"],
                           "first_seen_at": min(timestamp(r["observed_at"]) for r in records).isoformat(),
                           "observed_at": observed.isoformat(), "available_at": latest["available_at"],
                           "fresh_until": fresh_until.isoformat(), "stale": now >= fresh_until,
                           "ticket_url": None, "ticket_notice": "Synthetic event; no real ticket listing.",
                           "reconciliation_status": "provisional", "sources": provenance})
        events.sort(key=lambda e: (e["local_date"], e["starts_at"] or "", e["event_id"]))
        latest_runs = {}
        for run in state["runs"].values():
            prior = latest_runs.get(run["source_id"])
            if prior is None or timestamp(run["finished_at"]) >= timestamp(prior["finished_at"]):
                latest_runs[run["source_id"]] = run
        runs = [{"status": r["status"], "name": state["sources"][r["source_id"]]["name"],
                 "finished_at": r["finished_at"], "item_count": r["item_count"]}
                for r in latest_runs.values()]
        status = "ready" if events else "empty"
        if any(r["status"] == "failed" for r in runs):
            status = "partial" if events else "unavailable"
        elif not events and review_count:
            status = "review_required"
        elif not events and (state["records"] or any(r["status"] == "skipped" for r in runs)):
            status = "blocked"
        return {"mode": "synthetic", "status": status, "generated_at": now.isoformat(),
                "freshness_rule": "Demo only: stale after 24 hours; not a production SLA.",
                "events": events, "collections": runs, "review_count": review_count}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    args = parser.parse_args()
    try:
        fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
        result = FixtureStore(args.store).seed(fixture, datetime.now(UTC))
        print(json.dumps({"synthetic": True, "events": len(result["events"]),
                          "records": len(result["records"]), "network_calls": 0}))
    except (DiscoveryError, OSError, ValueError, KeyError, TypeError):
        parser.exit(1, "Synthetic ingestion failed; no provider call was made.\n")


if __name__ == "__main__":
    main()
