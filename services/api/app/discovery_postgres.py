"""Transactional local synthetic persistence; no migrations or network providers at startup."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid5

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .discovery import (
    NAMESPACE,
    USES,
    DiscoveryError,
    FixtureStore,
    empty_state,
    ingest,
    project_feed,
    timestamp,
)


class DiscoveryStore(Protocol):
    def seed(self, fixture: dict, now: datetime) -> dict: ...

    def feed(self, now: datetime) -> dict: ...


def local_dsn(dsn: str) -> str:
    """This increment is local only; never silently connect to a hosted project."""
    try:
        options = conninfo_to_dict(dsn)
        if options.get("host") not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError
        if options.get("hostaddr") or options.get("service"):
            raise ValueError
    except (psycopg.Error, ValueError):
        raise DiscoveryError("local_database_required") from None
    return dsn


def configured_store() -> DiscoveryStore:
    dsn = os.environ.get("SWEET_SEATS_LOCAL_DATABASE_URL")
    return PostgresStore(dsn) if dsn else FixtureStore()


class PostgresStore:
    def __init__(self, dsn: str):
        self.dsn = local_dsn(dsn)

    def _connect(self):
        # Explicit hostaddr prevents an inherited PGHOSTADDR from redirecting a
        # loopback DSN to a hosted database.
        host = conninfo_to_dict(self.dsn)["host"]
        return psycopg.connect(
            self.dsn, hostaddr="::1" if host == "::1" else "127.0.0.1",
            row_factory=dict_row, connect_timeout=3,
        )

    def read(self) -> dict:
        try:
            with self._connect() as conn:
                # Multiple table reads must see one committed ingestion/permission revision.
                conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                return self._read(conn)
        except psycopg.Error:
            raise DiscoveryError("store_unavailable") from None

    def feed(self, now: datetime) -> dict:
        return project_feed(self.read(), now)

    @staticmethod
    def _read(conn, *, unseeded=False) -> dict:
        marker = conn.execute("SELECT * FROM discovery_state").fetchone()
        if marker is None and not unseeded:
            raise DiscoveryError("store_not_seeded")
        state = empty_state()
        for row in conn.execute("SELECT * FROM sources WHERE discovery_metadata IS NOT NULL"):
            source = row["discovery_metadata"]
            sid = str(row["source_id"])
            source["access_status"] = row["access_status"]
            p = conn.execute(
                "SELECT * FROM source_permissions WHERE permission_id=%s",
                (source["permission"]["permission_id"],),
            ).fetchone()
            source["permission"].update(
                {
                    "uses": {use: p[use + "_allowed"] for use in USES},
                    "approved_at": p["approved_at"].isoformat() if p["approved_at"] else None,
                    "expires_at": p["expires_at"].isoformat() if p["expires_at"] else None,
                    "revoked_at": p["revoked_at"].isoformat() if p["revoked_at"] else None,
                    "terms_version": p["terms_version"],
                    "evidence_ref": p["evidence_note"],
                }
            )
            state["sources"][sid] = source
        for row in conn.execute("SELECT * FROM artists"):
            state["identities"]["artists"][str(row["artist_id"])] = {"name": row["canonical_name"]}
        for row in conn.execute("SELECT * FROM venues"):
            state["identities"]["venues"][str(row["venue_id"])] = {
                k: row[k] for k in ("name", "neighborhood", "timezone")
            }
        for row in conn.execute("SELECT * FROM events"):
            eid = str(row["event_id"])
            state["events"][eid] = {"event_id": eid, "match_key": row["discovery_match_key"]}
        for row in conn.execute("SELECT * FROM source_entity_mappings WHERE record_type='event'"):
            sid = str(row["source_id"])
            state["mappings"][sid + ":event:" + row["vendor_id"]] = {
                "source_id": sid,
                "record_type": "event",
                "vendor_id": row["vendor_id"],
                "event_id": str(row["event_id"]),
                "mapping_method": row["mapping_method"],
            }
        run_keys = {}
        for row in conn.execute(
            "SELECT * FROM collection_runs WHERE replay_digest IS NOT NULL ORDER BY finished_at, collection_run_id"
        ):
            sid = str(row["source_id"])
            key = sid + ":" + row["logical_key"]
            run_keys[row["collection_run_id"]] = key
            state["runs"][key] = {
                "source_id": sid,
                "logical_key": row["logical_key"],
                "status": row["status"],
                "digest": row["replay_digest"],
                "item_count": row["item_count"],
                "finished_at": row["finished_at"].astimezone(UTC).isoformat(),
                "error_code": row["error_code"],
            }
        credits = {}
        for row in conn.execute(
            "SELECT * FROM source_event_performers ORDER BY billing_order, artist_id"
        ):
            credits.setdefault(str(row["source_record_id"]), []).append(
                {
                    "artist_id": str(row["artist_id"]),
                    "role": row["role"],
                    "billing_order": row["billing_order"],
                }
            )
        for row in conn.execute("SELECT * FROM source_event_records"):
            rid = str(row["source_record_id"])
            record = {
                k: row[k]
                for k in (
                    "title",
                    "starts_at",
                    "timezone",
                    "status",
                    "observed_at",
                    "available_at",
                    "source_url",
                    "ticket_url",
                    "adapter_version",
                    "payload_hash",
                    "vendor_event_id",
                )
            }
            record.update(
                {k: str(row[k]) for k in ("source_id", "permission_id", "event_id", "venue_id")}
            )
            record.update(
                source_record_id=rid,
                local_date=row["local_date"].isoformat(),
                venue_vendor_id=row["vendor_venue_id"],
                performers=credits[rid],
                collection_run_key=run_keys[row["collection_run_id"]],
            )
            if row["onsale_at"] is not None:
                record["onsale_at"] = row["onsale_at"]
            state["records"][rid] = record
        # Review items keep the declared observation exactly as ingest retained it.
        state["unresolved"] = {
            str(row["source_record_id"]): row["observation"]
            for row in conn.execute("SELECT * FROM source_unresolved_records")
        }
        return state

    def seed(self, fixture: dict, now: datetime) -> dict:
        try:
            with self._connect() as conn:
                # One writer across all processes; lock released on commit, rollback or disconnect.
                conn.execute("SET LOCAL lock_timeout = '10s'")
                conn.execute("SELECT pg_advisory_xact_lock(1936942181)")
                before = self._read(conn, unseeded=True)
                state = ingest(before, fixture, now)
                self._write(conn, before, state)
            return self.read()
        except psycopg.Error:
            raise DiscoveryError("store_write_failed") from None

    @staticmethod
    def _write(conn, before, state):
        for sid, source in state["sources"].items():
            conn.execute(
                """INSERT INTO sources(source_id, slug, name, official_url, source_type,
                            access_status, adapter_version, discovery_metadata)
                            VALUES (%s,%s,%s,%s,'synthetic',%s,%s,%s)
                            ON CONFLICT(source_id) DO UPDATE SET access_status=excluded.access_status,
                            adapter_version=excluded.adapter_version, discovery_metadata=excluded.discovery_metadata""",
                (
                    sid,
                    "synthetic-" + sid,
                    source["name"],
                    "https://discovery.invalid",
                    source["access_status"],
                    source["adapter_version"],
                    Jsonb(source),
                ),
            )
            p = source["permission"]
            cols = sorted(USES)
            # Column identifiers are constants, never fixture text.
            names = ",".join(use + "_allowed" for use in cols)
            updates = ",".join(use + "_allowed=excluded." + use + "_allowed" for use in cols)
            conn.execute(
                f"""INSERT INTO source_permissions(permission_id,source_id,terms_url,
                         terms_version,evidence_note,approved_at,expires_at,revoked_at,created_at,{names})
                         VALUES (%s,%s,'https://terms.invalid',%s,%s,%s,%s,%s,%s,{",".join(["%s"] * len(cols))})
                         ON CONFLICT(permission_id) DO UPDATE SET {updates},
                         terms_version=excluded.terms_version,evidence_note=excluded.evidence_note,
                         approved_at=excluded.approved_at,expires_at=excluded.expires_at,
                         revoked_at=excluded.revoked_at""",
                (
                    p["permission_id"],
                    sid,
                    p["terms_version"],
                    p["evidence_ref"],
                    p["approved_at"],
                    p["expires_at"],
                    p["revoked_at"],
                    (p["approved_at"] or "1970-01-01T00:00:00Z"),
                    *(p["uses"].get(use) is True for use in cols),
                ),
            )
        for aid, artist in state["identities"]["artists"].items():
            conn.execute(
                "INSERT INTO artists(artist_id,canonical_name) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (aid, artist["name"]),
            )
        for vid, venue in state["identities"]["venues"].items():
            conn.execute(
                "INSERT INTO venues(venue_id,name,neighborhood,timezone) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (vid, venue["name"], venue["neighborhood"], venue["timezone"]),
            )
        for eid, event in state["events"].items():
            records = [r for r in state["records"].values() if r["event_id"] == eid]
            first = min(timestamp(r["observed_at"]) for r in records)
            latest = max(
                records, key=lambda r: (timestamp(r["available_at"]), r["source_record_id"])
            )
            conn.execute(
                """INSERT INTO events(event_id,venue_id,starts_at,local_date,timezone,time_tba,status,
                         first_seen_at,discovery_match_key,reconciliation_status)
                         VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'provisional') ON CONFLICT(event_id) DO UPDATE
                         SET discovery_match_key=excluded.discovery_match_key,venue_id=excluded.venue_id,
                         starts_at=excluded.starts_at,local_date=excluded.local_date,
                         time_tba=excluded.time_tba,status=excluded.status""",
                (
                    eid,
                    latest["venue_id"],
                    latest["starts_at"],
                    latest["local_date"],
                    latest["timezone"],
                    latest["starts_at"] is None,
                    latest["status"],
                    first,
                    event["match_key"],
                ),
            )
        for source in state["sources"].values():
            for kind, field in (("artist", "artist_mappings"), ("venue", "venue_mappings")):
                for vendor, target in source[field].items():
                    conn.execute(
                        f"""INSERT INTO source_entity_mappings(source_id,record_type,vendor_id,{kind}_id,mapping_method)
                                 VALUES (%s,%s,%s,%s,'reviewed_fixture_identity') ON CONFLICT DO NOTHING""",
                        (source["source_id"], kind, vendor, target),
                    )
        for m in state["mappings"].values():
            conn.execute(
                """INSERT INTO source_entity_mappings(source_id,record_type,vendor_id,event_id,mapping_method)
                         VALUES (%s,'event',%s,%s,%s) ON CONFLICT(source_id,record_type,vendor_id) DO NOTHING""",
                (m["source_id"], m["vendor_id"], m["event_id"], m["mapping_method"]),
            )
        for key, run in state["runs"].items():
            if key in before["runs"]:
                continue
            source = state["sources"][run["source_id"]]
            conn.execute(
                """INSERT INTO collection_runs(collection_run_id,source_id,logical_key,status,
                         finished_at,adapter_version,permission_id,item_count,error_code,replay_digest)
                         VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    uuid5(NAMESPACE, key),
                    run["source_id"],
                    run["logical_key"],
                    run["status"],
                    run["finished_at"],
                    source["adapter_version"],
                    source["permission"]["permission_id"],
                    run["item_count"],
                    run["error_code"],
                    run["digest"],
                ),
            )
        for rid, r in state["records"].items():
            if rid in before["records"]:
                continue
            fields = (
                "source_record_id",
                "source_id",
                "permission_id",
                "event_id",
                "vendor_event_id",
                "venue_id",
                "title",
                "starts_at",
                "local_date",
                "timezone",
                "status",
                "observed_at",
                "available_at",
                "source_url",
                "ticket_url",
                "adapter_version",
                "payload_hash",
            )
            conn.execute(
                f"""INSERT INTO source_event_records({",".join(fields)},vendor_venue_id,collection_run_id,
                         onsale_at) VALUES ({",".join(["%s"] * (len(fields) + 3))})""",
                (
                    *(r[k] for k in fields),
                    r["venue_vendor_id"],
                    uuid5(NAMESPACE, r["collection_run_key"]),
                    r.get("onsale_at"),
                ),
            )
            for p in r["performers"]:
                conn.execute(
                    """INSERT INTO source_event_performers(source_record_id,artist_id,role,billing_order)
                             VALUES (%s,%s,%s,%s)""",
                    (rid, p["artist_id"], p["role"], p["billing_order"]),
                )
        for rid, r in state["unresolved"].items():
            if rid in before["unresolved"]:
                continue
            conn.execute(
                """INSERT INTO source_unresolved_records(source_record_id,source_id,permission_id,
                         collection_run_id,reason,payload_hash,observation) VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (
                    rid,
                    r["source_id"],
                    r["permission_id"],
                    uuid5(NAMESPACE, r["collection_run_key"]),
                    r["reason"],
                    r["payload_hash"],
                    Jsonb(r),
                ),
            )
        # A replay under a newly reviewed crosswalk resolves the item into source_event_records.
        for rid in before["unresolved"].keys() - state["unresolved"].keys():
            conn.execute("DELETE FROM source_unresolved_records WHERE source_record_id=%s", (rid,))
        conn.execute(
            "INSERT INTO discovery_state VALUES (true,'SS-DISCOVERY-DEMO-0.1',true) ON CONFLICT DO NOTHING"
        )
