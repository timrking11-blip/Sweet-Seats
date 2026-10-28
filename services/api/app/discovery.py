"""Offline discovery slice (SS-DATA-0.1 / SS-ADR-002, 003, 004).

Only synthetic fixtures are accepted. Reconciliation and feed projection are shared
by the transactional PostgreSQL adapter and the legacy single-writer JSON adapter.
No provider I/O is performed.
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
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STORE = ROOT / ".local" / "discovery.json"
DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "discovery" / "nyc.json"
NAMESPACE = UUID("8b4205ed-5ed2-4956-980a-85191120abe1")
USES = {"collect", "display", "raw_retention", "derived_retention", "feature", "train", "test"}
# Stored observations are normalized records plus a payload hash; no raw provider
# payload is kept, so storage and display gate on derived retention. raw_retention
# stays a separate use for any future path that keeps the payload itself.
STORE_USES = ("collect", "derived_retention")
DISPLAY_USES = ("display", "derived_retention")
# A valid observation whose venue or artist has no reviewed crosswalk is kept for
# review, never rejected and never matched by name (contract: retained in unresolved).
UNRESOLVED_IDENTITY = {"unresolved_venue_identity", "unresolved_typed_identity"}


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
    """Distinct uses; unknown, expired, future or revoked grants fail closed.

    Mirrors public.source_use_is_permitted; tests/test_permission_parity.py holds the
    two to the same cases. A grant applies within [approved_at, revoked_at/expires_at).
    """
    p = source.get("permission", {})

    def present(value: object) -> bool:
        return isinstance(value, str) and bool(value.strip())

    try:
        return bool(
            use in USES
            and source.get("access_status") in {"approved", "active"}
            and p.get("uses", {}).get(use) is True
            and present(p.get("evidence_ref"))
            and present(p.get("terms_version"))
            and (not p.get("revoked_at") or now < timestamp(p["revoked_at"]))
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


def provider_url(value: object) -> str:
    """A real provider link: https, a host, no embedded credentials."""
    from urllib.parse import urlsplit

    parsed = urlsplit(value) if isinstance(value, str) and len(value) <= 2048 else None
    if (parsed is None or parsed.scheme != "https" or not parsed.hostname
            or parsed.username or parsed.password):
        raise DiscoveryError("invalid_provider_url")
    return value


RECORD_FIELDS = {"vendor_event_id", "title", "venue_vendor_id", "performers", "starts_at",
                 "local_date", "timezone", "status", "observed_at", "available_at",
                 "source_url", "ticket_url"}
# Optional: when public on-sale opens, as the source states it (SourceEventRecord).
OPTIONAL_RECORD_FIELDS = {"onsale_at"}


def normalize(record: dict, source: dict, identities: dict, url=_demo_url) -> dict:
    if not RECORD_FIELDS <= set(record) <= RECORD_FIELDS | OPTIONAL_RECORD_FIELDS:
        raise DiscoveryError("unexpected_record_fields")
    if record.get("onsale_at") is not None:
        timestamp(record["onsale_at"])
    if record["timezone"] != "America/New_York":
        raise DiscoveryError("unsupported_fixture_timezone")
    try:
        local_day = date.fromisoformat(record["local_date"])
    except (ValueError, TypeError) as exc:
        raise DiscoveryError("invalid_local_date") from exc
    if (record["starts_at"] is not None
            and timestamp(record["starts_at"]).astimezone(ZoneInfo(record["timezone"])).date()
            != local_day):
        raise DiscoveryError("local_date_timezone_mismatch")
    observed, available = timestamp(record["observed_at"]), timestamp(record["available_at"])
    if observed > available:
        raise DiscoveryError("availability_before_observation")
    if record["status"] not in {"scheduled", "rescheduled", "postponed", "cancelled", "unknown"}:
        raise DiscoveryError("invalid_event_status")
    # Validate the entire observation before deciding whether identities are unresolved.
    _text(record["vendor_event_id"])
    _text(record["title"])
    _text(record["venue_vendor_id"])
    url(record["source_url"])
    if record["ticket_url"] is not None:
        url(record["ticket_url"])
    if not isinstance(record["performers"], list) or not record["performers"]:
        raise DiscoveryError("invalid_venue_or_credits")
    credit_keys = set()
    for credit in record["performers"]:
        if not isinstance(credit, dict) or set(credit) != {"vendor_artist_id", "role", "billing_order"}:
            raise DiscoveryError("unexpected_credit_fields")
        vendor_artist_id = _text(credit["vendor_artist_id"])
        if (credit["role"] not in {"headliner", "support", "performer"}
                or type(credit["billing_order"]) is not int or credit["billing_order"] < 0):
            raise DiscoveryError("invalid_credit")
        if vendor_artist_id in source["artist_mappings"]:
            artist_key = ("mapped", identifier(source["artist_mappings"][vendor_artist_id]))
        else:
            artist_key = ("vendor", vendor_artist_id)
        credit_key = (*artist_key, credit["role"])
        if credit_key in credit_keys:
            raise DiscoveryError("duplicate_performer_credit")
        credit_keys.add(credit_key)
    try:
        venue_id = source["venue_mappings"][record["venue_vendor_id"]]
        venue = identities["venues"][identifier(venue_id)]
    except (KeyError, TypeError) as exc:
        raise DiscoveryError("unresolved_venue_identity") from exc
    try:
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
    # A null on-sale time is dropped so record IDs and store parity match records without one.
    record = {k: v for k, v in record.items() if k != "onsale_at" or v is not None}
    return {
        **record, "vendor_event_id": _text(record["vendor_event_id"]),
        "title": _text(record["title"]), "venue_id": venue_id, "performers": performers,
        "source_url": url(record["source_url"]),
        "ticket_url": url(record["ticket_url"]) if record["ticket_url"] else None,
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
    result.setdefault("unresolved", {})
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
    permission_ids = set()
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
        permission_id = identifier(source["permission"]["permission_id"])
        if permission_id in permission_ids:
            raise DiscoveryError("duplicate_source_permission")
        permission_ids.add(permission_id)
        previous = result["sources"].get(source_id, {})
        for kind, mapping_field in (("artists", "artist_mappings"), ("venues", "venue_mappings")):
            for vendor, target in source[mapping_field].items():
                _text(vendor)
                if identifier(target) not in result["identities"][kind]:
                    raise DiscoveryError("unresolved_typed_identity")
                if vendor in previous.get(mapping_field, {}) and previous[mapping_field][vendor] != target:
                    raise DiscoveryError("identity_crosswalk_revision_requires_review")
        sources[source_id] = source
        prior_source = result["sources"].get(source_id)
        if prior_source:
            for kind in ("artist_mappings", "venue_mappings"):
                if any(source[kind].get(key) != target for key, target in prior_source[kind].items()):
                    raise DiscoveryError("identity_crosswalk_revision_requires_review")
    result["sources"].update(sources)
    for batch in fixture["batches"]:
        _ingest_batch(result, sources, batch, now, _demo_url)
    return result


def _ingest_batch(result: dict, sources: dict, batch: dict, now: datetime, url) -> None:
    """Reconcile one collection batch into result in place (shared by every source kind)."""
    if set(batch) != {"source_id", "logical_key", "outcome", "records"}:
        raise DiscoveryError("unexpected_batch_fields")
    source = sources[batch["source_id"]]
    logical_key = _text(batch["logical_key"])
    run_key = source["source_id"] + ":" + logical_key
    allowed = all(permitted(source, use, now) for use in STORE_USES)
    # A skipped run retains only its operational identity, not a payload-derived hash.
    fingerprint = digest(batch) if allowed else digest([source["source_id"], logical_key, "skipped"])
    if run_key in result["runs"]:
        if result["runs"][run_key]["digest"] != fingerprint:
            raise DiscoveryError("changed_batch_at_same_logical_key")
        return
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
        return
    for raw in batch["records"]:
        unresolved_reason = None
        try:
            record = normalize(raw, source, result["identities"], url)
        except DiscoveryError as exc:
            if str(exc) not in UNRESOLVED_IDENTITY:
                raise
            unresolved_reason = str(exc)
            # Known schema and valid facts, but no reviewed typed crosswalk.
            # Retain only the declared observation, never an arbitrary payload.
            record = {**raw, "source_id": source["source_id"],
                      "permission_id": source["permission"]["permission_id"]}
        if timestamp(record["available_at"]) > now:
            raise DiscoveryError("future_observation")
        p = source["permission"]
        if not (timestamp(p["approved_at"]) <= timestamp(record["observed_at"])
                < timestamp(p["expires_at"])):
            raise DiscoveryError("observation_outside_permission")
        unresolved_id = str(uuid5(NAMESPACE, digest([source["source_id"], raw])))
        if "venue_id" not in record:
            result["unresolved"][unresolved_id] = {
                **record, "source_record_id": unresolved_id,
                "reason": unresolved_reason, "collection_run_key": run_key,
                "payload_hash": digest(raw), "adapter_version": source["adapter_version"],
            }
            run["item_count"] += 1
            continue
        # Replaying observations under a new reviewed crosswalk can resolve a prior item.
        result["unresolved"].pop(unresolved_id, None)
        mapping_key = source["source_id"] + ":event:" + record["vendor_event_id"]
        headliners = sorted(p["artist_id"] for p in record["performers"]
                            if p["role"] == "headliner")
        match_key = digest([record["venue_id"], timestamp(record["starts_at"]).isoformat(),
                            headliners]) if record["starts_at"] and headliners else None
        event_id = result["mappings"].get(mapping_key, {}).get("event_id")
        mapping_method = "source_identity" if event_id else None
        if event_id is None:
            matches = [e["event_id"] for e in result["events"].values()
                       if match_key and e["match_key"] == match_key]
            if len(matches) > 1:
                result["unresolved"][unresolved_id] = {
                    **record, "source_record_id": unresolved_id,
                    "reason": "ambiguous_event_match", "collection_run_key": run_key,
                    "payload_hash": digest(raw),
                }
                run["item_count"] += 1
                continue
            event_id = matches[0] if matches else str(uuid5(NAMESPACE, mapping_key))
            mapping_method = "known_identity_exact_occurrence" if matches else "source_identity"
        result["events"][event_id] = {"event_id": event_id, "match_key": match_key}
        result["mappings"][mapping_key] = {
            "source_id": source["source_id"], "record_type": "event",
            "vendor_id": record["vendor_event_id"], "event_id": event_id,
            "mapping_method": mapping_method,
        }
        record_id = str(uuid5(NAMESPACE, digest(record)))
        result["records"][record_id] = {
            **record, "source_record_id": record_id, "event_id": event_id,
            "payload_hash": digest(raw), "collection_run_key": run_key,
        }
        run["item_count"] += 1


def ingest_collection(state: dict, source: dict, logical_key: str, collection: dict,
                      now: datetime) -> dict:
    """Reconcile a live adapter's mapped records through the same path as fixtures.

    source is the owner-approved registry entry (source_registry), never the payload:
    the incoming collection carries records only, so it cannot grant itself rights.
    Canonical artists and venues must already exist; unmapped identities go to review.
    A skipped or not-modified collection made no observation and changes nothing.
    """
    if source.get("kind") != "provider":
        raise DiscoveryError("provider_source_required")
    status = collection.get("status")
    if status in {"skipped", "not_modified"}:
        return copy.deepcopy(state)
    if status not in {"succeeded", "empty", "failed"}:
        raise DiscoveryError("invalid_collection_outcome")
    result = copy.deepcopy(state)
    result.setdefault("unresolved", {})
    source_id = identifier(source["source_id"])
    prior = result["sources"].get(source_id)
    for kind, field in (("artists", "artist_mappings"), ("venues", "venue_mappings")):
        for vendor, target in source[field].items():
            if identifier(target) not in result["identities"][kind]:
                raise DiscoveryError("unresolved_typed_identity")
            if prior and vendor in prior[field] and prior[field][vendor] != target:
                raise DiscoveryError("identity_crosswalk_revision_requires_review")
    result["sources"][source_id] = copy.deepcopy(source)
    batch = {"source_id": source_id, "logical_key": logical_key, "outcome": status,
             "records": list(collection.get("records", [])) if status == "succeeded" else []}
    _ingest_batch(result, {source_id: result["sources"][source_id]}, batch, now, provider_url)
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
        return project_feed(self.read(), now)


def project_feed(state: dict, now: datetime) -> dict:
    """Storage-independent, permission-filtered discovery projection."""
    grouped: dict[str, list[dict]] = {}
    for record in state["records"].values():
        source = state["sources"][record["source_id"]]
        if (all(permitted(source, use, now) for use in DISPLAY_USES)
                and record["permission_id"] == source["permission"]["permission_id"]):
            grouped.setdefault(record["event_id"], []).append(record)
    events = []
    review_count = 0
    unresolved = []
    for record in state.get("unresolved", {}).values():
        source = state["sources"][record["source_id"]]
        if (all(permitted(source, use, now) for use in DISPLAY_USES)
                and record["permission_id"] == source["permission"]["permission_id"]):
            unresolved.append({k: record[k] for k in (
                "source_record_id", "source_id", "vendor_event_id", "title", "reason")})
    review_count += len(unresolved)
    for event_id, records in grouped.items():
        records.sort(key=lambda r: (timestamp(r["available_at"]), r["source_record_id"]))
        first_seen = min(timestamp(r["observed_at"]) for r in records)
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
                       "onsale_at": latest.get("onsale_at"),
                       "first_seen_at": first_seen.isoformat(),
                       "observed_at": observed.isoformat(), "available_at": latest["available_at"],
                       "fresh_until": fresh_until.isoformat(), "stale": now >= fresh_until,
                       "ticket_url": None, "ticket_notice": "Synthetic event; no real ticket listing.",
                       "reconciliation_status": "provisional", "sources": provenance})
    events.sort(key=lambda e: (e["local_date"], e["starts_at"] or "", e["event_id"]))
    latest_runs = {}
    for run in sorted(state["runs"].values(), key=lambda r: (timestamp(r["finished_at"]), r["logical_key"])):
        prior = latest_runs.get(run["source_id"])
        if prior is None or timestamp(run["finished_at"]) >= timestamp(prior["finished_at"]):
            latest_runs[run["source_id"]] = run
    runs = [{"status": r["status"], "name": state["sources"][r["source_id"]]["name"],
             "finished_at": r["finished_at"], "item_count": r["item_count"]}
            for _, r in sorted(latest_runs.items())]
    status = "ready" if events else "empty"
    if any(r["status"] == "failed" for r in runs):
        status = "partial" if events else "unavailable"
    elif not events and review_count:
        status = "review_required"
    elif not events and (state["records"] or state.get("unresolved")
                         or any(r["status"] == "skipped" for r in runs)):
        status = "blocked"
    return {"mode": "synthetic", "status": status, "generated_at": now.isoformat(),
            "freshness_rule": "Demo only: stale after 24 hours; not a production SLA.",
            "events": events, "collections": runs, "review_count": review_count,
            "unresolved": sorted(unresolved, key=lambda r: r["source_record_id"])}


def lead_time_report(state: dict, now: datetime) -> dict:
    """Which source makes each event knowable first (SS-DATA-0.1 available_at).

    Internal measurement for the Phase 3 question "do official monitors beat the
    listing APIs?". Only stored, reconciled observations whose source still permits
    derived retention count; unresolved records have no canonical event to compare.
    """
    first_by_event: dict[str, dict[str, datetime]] = {}
    for record in state["records"].values():
        source = state["sources"][record["source_id"]]
        if (not permitted(source, "derived_retention", now)
                or record["permission_id"] != source["permission"]["permission_id"]):
            continue
        seen = first_by_event.setdefault(record["event_id"], {})
        available = timestamp(record["available_at"])
        if record["source_id"] not in seen or available < seen[record["source_id"]]:
            seen[record["source_id"]] = available
    totals = {}
    for seen in first_by_event.values():
        earliest = min(seen.values())
        for source_id, available in seen.items():
            row = totals.setdefault(source_id, {"events_seen": 0, "events_first": 0, "lags": []})
            row["events_seen"] += 1
            row["events_first"] += available == earliest  # Ties count as first for each.
            if len(seen) > 1:
                row["lags"].append((available - earliest).total_seconds() / 60)
    sources = []
    for source_id, row in sorted(totals.items()):
        lags = sorted(row["lags"])
        middle = len(lags) // 2
        median = None if not lags else (
            lags[middle] if len(lags) % 2 else (lags[middle - 1] + lags[middle]) / 2)
        sources.append({"source_id": source_id, "name": state["sources"][source_id]["name"],
                        "events_seen": row["events_seen"], "events_first": row["events_first"],
                        "shared_events": len(lags), "median_lag_minutes": median})
    return {"basis": "available_at", "events": len(first_by_event), "sources": sources}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--store", type=Path, default=None,
                        help="Explicit JSON-only legacy store; otherwise use configured adapter")
    args = parser.parse_args()
    try:
        fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
        from .discovery_postgres import configured_store

        store = FixtureStore(args.store) if args.store else configured_store()
        result = store.seed(fixture, datetime.now(UTC))
        print(json.dumps({"synthetic": True, "events": len(result["events"]),
                          "records": len(result["records"]),
                          "unresolved": len(result.get("unresolved", {})),
                          "provider_network_calls": 0,
                          "lead_times": lead_time_report(result, datetime.now(UTC)),
                          "runs": [{k: r[k] for k in ("source_id", "logical_key", "digest",
                                   "status", "item_count")} for _, r in sorted(result["runs"].items())]}))
    except (DiscoveryError, OSError, ValueError, KeyError, TypeError) as exc:
        code = str(exc) if isinstance(exc, DiscoveryError) else "invalid_fixture_or_store"
        parser.exit(1, f"Synthetic ingestion failed: {code}; no provider call was made.\n")


if __name__ == "__main__":
    main()
