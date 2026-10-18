"""Real disposable PostgreSQL acceptance; skipped only when no explicit test DSN exists."""

import copy
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.types.json import Jsonb

from app.discovery import DiscoveryError, FixtureStore, timestamp
from app.discovery_postgres import PostgresStore, configured_store
from app.main import app, discovery_now

NOW = timestamp("2026-10-18T07:00:00Z")
DSN = os.environ.get("SWEET_SEATS_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="requires disposable local PostgreSQL DSN")


def test_unresolved_observations_persist(pg_store, tmp_path):
    store, fixture = pg_store
    fixture["batches"][0]["records"][0]["performers"][0]["vendor_artist_id"] = "unknown"
    baseline = FixtureStore(tmp_path / "events.json")
    expected = baseline.seed(fixture, NOW)

    assert store.seed(fixture, NOW) == expected
    assert store.read()["unresolved"] == expected["unresolved"]
    assert store.feed(NOW) == baseline.feed(NOW)


def test_persistence_parity_replay_restart_and_digest_report(pg_store, tmp_path):
    store, fixture = pg_store
    baseline = FixtureStore(tmp_path / "events.json")
    baseline.seed(fixture, NOW)
    first = store.seed(fixture, NOW)
    assert len(first["records"]) == 4
    assert len(first["events"]) == 3
    assert store.feed(NOW) == baseline.feed(NOW)
    assert store.seed(fixture, NOW + timedelta(hours=1)) == first
    # A fresh interpreter and fresh connections must recover exactly the same API projection.
    env = dict(os.environ, SWEET_SEATS_LOCAL_DATABASE_URL=store.dsn)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json; from app.discovery_postgres import configured_store; "
                "from app.discovery import timestamp; "
                'print(json.dumps(configured_store().feed(timestamp("2026-10-18T07:00:00Z"))))'
            ),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == baseline.feed(NOW)
    with store._connect() as conn:
        report = conn.execute("SELECT replay_digest,item_count FROM collection_runs").fetchall()
        assert len(report) == 2
        assert all(len(r["replay_digest"]) == 64 and r["item_count"] == 2 for r in report)
        assert (
            conn.execute("SELECT count(*) AS n FROM source_event_performers").fetchone()["n"] == 6
        )


def test_concurrent_duplicate_and_changed_replay(pg_store):
    store, fixture = pg_store
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: PostgresStore(store.dsn).seed(fixture, NOW), range(4)))
    assert all(r == results[0] for r in results)
    changed = copy.deepcopy(fixture)
    changed["batches"][0]["records"][0]["title"] = "Changed"
    with pytest.raises(DiscoveryError, match="changed_batch"):
        store.seed(changed, NOW)
    assert store.read() == results[0]


def test_validation_and_database_failure_rollback(pg_store, monkeypatch):
    store, fixture = pg_store
    store.seed(fixture, NOW)
    before = store.read()
    broken = copy.deepcopy(fixture)
    for b in broken["batches"]:
        b["logical_key"] += "-new"
    broken["batches"][-1]["records"][-1]["status"] = "invalid"
    with pytest.raises(DiscoveryError):
        store.seed(broken, NOW)
    assert store.read() == before
    original = PostgresStore._write

    def fail_after_writes(conn, previous, state):
        original(conn, previous, state)
        conn.execute("SELECT 1/0")

    monkeypatch.setattr(PostgresStore, "_write", staticmethod(fail_after_writes))
    retry = copy.deepcopy(fixture)
    retry["sources"][0]["permission"]["uses"]["display"] = False
    with pytest.raises(DiscoveryError, match="store_write_failed"):
        store.seed(retry, NOW)
    assert store.read() == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("display_allowed", False),
        ("raw_retention_allowed", False),
        ("derived_retention_allowed", False),
        ("revoked_at", "2026-10-18T06:00:00Z"),
        ("expires_at", "2026-10-18T07:00:00Z"),
        ("approved_at", "2026-10-19T00:00:00Z"),
    ],
)
def test_database_permission_changes_hide_events_immediately(pg_store, field, value):
    store, fixture = pg_store
    store.seed(fixture, NOW)
    with store._connect() as conn:
        conn.execute(
            sql.SQL("UPDATE source_permissions SET {}=%s").format(sql.Identifier(field)), (value,)
        )
    assert store.feed(NOW)["status"] == "blocked"
    assert store.feed(NOW)["events"] == []


@pytest.mark.parametrize("use", ["collect", "raw_retention", "derived_retention"])
def test_unknown_ingestion_rights_store_no_observations(pg_store, use):
    store, fixture = pg_store
    for source in fixture["sources"]:
        source["permission"]["uses"].pop(use)
    state = store.seed(fixture, NOW)
    assert state["records"] == {}
    assert all(r["status"] == "skipped" for r in state["runs"].values())
    assert store.feed(NOW)["status"] == "blocked"


def test_lineage_constraints_and_rls_dml_denial(pg_store):
    store, fixture = pg_store
    store.seed(fixture, NOW)
    with store._connect() as conn:
        rows = conn.execute(
            "SELECT source_record_id,source_id FROM source_event_records"
        ).fetchall()
        with pytest.raises(psycopg.errors.ForeignKeyViolation), conn.transaction():
            conn.execute(
                "UPDATE source_event_records SET source_id=%s WHERE source_record_id=%s",
                (fixture["sources"][1]["source_id"], rows[0]["source_record_id"]),
            )
        for table in ("discovery_state", "source_event_records", "source_event_performers"):
            query = sql.SQL("SELECT row_to_json(t) AS data FROM {} t LIMIT 1").format(
                sql.Identifier(table)
            )
            data = conn.execute(query).fetchone()["data"]
            for role in ("anon", "authenticated"):
                with conn.transaction():
                    conn.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
                    assert (
                        conn.execute(
                            sql.SQL("SELECT * FROM {}").format(sql.Identifier(table))
                        ).fetchall()
                        == []
                    )
                    assert (
                        conn.execute(
                            sql.SQL("DELETE FROM {}").format(sql.Identifier(table))
                        ).rowcount
                        == 0
                    )
                    column = next(iter(data))
                    assert (
                        conn.execute(
                            sql.SQL("UPDATE {} SET {}={}").format(
                                sql.Identifier(table),
                                sql.Identifier(column),
                                sql.Identifier(column),
                            )
                        ).rowcount
                        == 0
                    )
                    with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                        conn.execute(
                            sql.SQL(
                                "INSERT INTO {} SELECT * FROM jsonb_populate_record(NULL::{},%s)"
                            ).format(sql.Identifier(table), sql.Identifier(table)),
                            (Jsonb(data),),
                        )
                conn.execute("RESET ROLE")


def test_api_contract_and_configured_adapter(pg_store, monkeypatch):
    store, fixture = pg_store
    monkeypatch.setenv("SWEET_SEATS_LOCAL_DATABASE_URL", store.dsn)
    assert isinstance(configured_store(), PostgresStore)
    app.dependency_overrides[discovery_now] = lambda: NOW
    try:
        with TestClient(app) as client:
            assert client.get("/v1/events").status_code == 503
            store.seed(fixture, NOW)
            feed = client.get("/v1/events").json()
            event = feed["events"][0]
            assert client.get("/v1/events/" + event["event_id"]).json()["event"] == event
            assert client.get("/v1/events/" + str(uuid4())).status_code == 404
            with store._connect() as conn:
                conn.execute("UPDATE source_permissions SET display_allowed=false")
            assert client.get("/v1/events").json()["status"] == "blocked"
            assert client.get("/v1/events/" + event["event_id"]).status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("outcome,status", [("empty", "empty"), ("failed", "unavailable")])
def test_empty_failure_states(pg_store, outcome, status):
    store, fixture = pg_store
    for b in fixture["batches"]:
        b.update(records=[], outcome=outcome)
    store.seed(fixture, NOW)
    assert store.feed(NOW)["status"] == status


def test_conflict_tba_postponement_and_freshness(pg_store):
    store, fixture = pg_store
    store.seed(fixture, NOW)
    events = store.feed(NOW)["events"]
    assert events[1]["time_tba"] and events[1]["stale"]
    assert events[2]["status"] == "cancelled"
    event_id = events[0]["event_id"]
    b = fixture["batches"][0]
    b["logical_key"] = "postponement"
    b["records"] = [b["records"][0]]
    b["records"][0].update(
        starts_at=None,
        status="postponed",
        observed_at="2026-10-18T06:59:00Z",
        available_at="2026-10-18T06:59:00Z",
    )
    fixture["batches"] = [b]
    store.seed(fixture, NOW)
    projected = next(e for e in store.feed(NOW)["events"] if e["event_id"] == event_id)
    assert projected["status"] == "postponed" and projected["time_tba"]
    assert projected["first_seen_at"] == events[0]["first_seen_at"]


def test_contemporaneous_conflict_and_failure_semantics(pg_store):
    store, fixture = pg_store
    fixture["batches"][1]["records"][0]["status"] = "cancelled"
    state = store.seed(fixture, NOW)
    feed = store.feed(NOW)
    assert len(state["records"]) == 4
    assert feed["review_count"] == 1 and len(feed["events"]) == 2
    before = feed["events"]
    for b in fixture["batches"]:
        b.update(logical_key=b["logical_key"] + "-failure", outcome="failed", records=[])
    store.seed(fixture, NOW + timedelta(hours=1))
    assert store.feed(NOW)["events"] == before
    assert store.feed(NOW)["status"] == "partial"
