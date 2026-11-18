"""Step 6 pilot instrumentation against disposable PostgreSQL: first-seen evidence is
recorded from every stored observation and never moves later, the weekly metrics agree
with the in-memory lead-time report, a week is appended once, and only allow-listed
owners can read the report."""
import os
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import TEST_ISSUER, mint_token
from fastapi.testclient import TestClient

from app.discovery import lead_time_report, timestamp
from app.main import app
from app.me import auth_now, user_store
from app.pilot_metrics import METRICS_VERSION, compute, last_full_week, record_week, week_bounds

NOW = timestamp("2026-10-18T07:00:00Z")
WEEK = date(2026, 10, 12)  # Monday; the fixture's observations fall in this ET week.
BASELINE, TREATMENT = "Synthetic artist calendar", "Synthetic venue calendar"
pytestmark = pytest.mark.skipif(not os.environ.get("SWEET_SEATS_TEST_DATABASE_URL"),
                                reason="requires disposable local PostgreSQL DSN")


@pytest.fixture
def pilot(pg_store):
    """The fixture with the shared show made available 10 minutes earlier by the venue
    calendar (treatment) than by the artist calendar (baseline)."""
    store, fixture = pg_store
    venue = next(b for b in fixture["batches"] if b["logical_key"].startswith("demo-venue"))
    shared = next(r for r in venue["records"] if r["vendor_event_id"] == "venue-202")
    shared["observed_at"] = shared["available_at"] = "2026-10-18T06:40:00Z"
    store.seed(fixture, NOW)
    conn = store._connect()
    conn.autocommit = True
    conn.execute("UPDATE sources SET source_type = 'event_listing_api' WHERE name = %s", (BASELINE,))
    conn.execute("UPDATE sources SET source_type = 'official_calendar' WHERE name = %s", (TREATMENT,))
    try:
        yield store, conn
    finally:
        conn.close()


def first_seen_rows(conn) -> int:
    return conn.execute("SELECT count(*) AS n FROM event_first_seen").fetchone()["n"]


def test_every_stored_observation_records_first_seen_once(pilot):
    _, conn = pilot
    pairs = conn.execute("SELECT count(DISTINCT (event_id, source_id)) AS n FROM source_event_records"
                         ).fetchone()["n"]
    assert first_seen_rows(conn) == pairs == 4

    record = conn.execute("SELECT * FROM source_event_records ORDER BY source_record_id LIMIT 1"
                          ).fetchone()

    def copy_with(available):
        columns = [c for c in record if c != "source_record_id"]
        values = [available if c in ("available_at", "observed_at") else record[c] for c in columns]
        conn.execute(f"INSERT INTO source_event_records(source_record_id, {', '.join(columns)}) "
                     f"VALUES (%s, {', '.join(['%s'] * len(columns))})", (uuid4(), *values))

    later = (timestamp(record["available_at"]) + timedelta(hours=1)).isoformat()
    copy_with(later)  # A later sighting is not new evidence.
    assert first_seen_rows(conn) == 4
    earlier = (timestamp(record["available_at"]) - timedelta(hours=1)).isoformat()
    copy_with(earlier)  # An earlier one is appended; nothing is rewritten.
    assert first_seen_rows(conn) == 5
    first = conn.execute(
        "SELECT min(first_available_at) AS at FROM event_first_seen WHERE event_id = %s AND source_id = %s",
        (record["event_id"], record["source_id"])).fetchone()["at"]
    assert first == timestamp(earlier)


def test_weekly_metrics_agree_with_the_lead_time_report(pilot):
    store, conn = pilot
    metrics = compute(conn, WEEK, NOW)
    expected = {s["name"]: s for s in lead_time_report(store.read(), NOW)["sources"]}
    got = {s["name"]: s for s in metrics["lead_time_by_source"]}
    for name in (BASELINE, TREATMENT):
        for key in ("events_seen", "events_first", "shared_events", "median_lag_minutes"):
            assert got[name][key] == expected[name][key], (name, key)
    assert (got[BASELINE]["role"], got[TREATMENT]["role"]) == ("baseline", "treatment")
    assert metrics["lead_time"]["shows_found_by_both"] == 1
    assert metrics["lead_time"]["median_lead_minutes"] == 10
    assert metrics["lead_time"]["treatment_earlier"] == 1
    assert metrics["incremental_coverage"] == {"panel_shows": 3, "treatment_only": 1, "rate": 0.3333}
    assert metrics["review_rate"]["collected"] == 4
    assert metrics["cost_per_useful_alert"]["value"] is None
    assert metrics["purchases"]["confirmed"] == 0
    # A week with no first sightings reports empty measures, not errors.
    empty = compute(conn, WEEK + timedelta(days=7), NOW)
    assert empty["incremental_coverage"]["rate"] is None and empty["lead_time"]["median_lead_minutes"] is None


def test_a_source_without_derived_retention_drops_out(pilot):
    _, conn = pilot
    conn.execute("""UPDATE source_permissions SET revoked_at = %s
                    WHERE source_id = (SELECT source_id FROM sources WHERE name = %s)""",
                 (NOW - timedelta(minutes=1), TREATMENT))
    metrics = compute(conn, WEEK, NOW)
    assert [s["name"] for s in metrics["lead_time_by_source"]] == [BASELINE]
    assert metrics["lead_time"]["shows_found_by_both"] == 0
    assert first_seen_rows(conn) == 4  # Hidden from the report, kept until a rights purge.


def test_a_finished_week_is_appended_once(pilot):
    store, conn = pilot
    _, end = week_bounds(WEEK)
    after = end + timedelta(hours=1)
    assert record_week(store, WEEK, after, "w1") == {"status": "succeeded", "week": "2026-10-12",
                                                     "inserted": 1}
    assert record_week(store, WEEK, after, "w2") is None
    row = conn.execute("SELECT * FROM pilot_metrics").fetchone()
    assert (row["period_start"], row["period_end"], row["metrics_version"]) == (
        WEEK, WEEK + timedelta(days=7), METRICS_VERSION)
    assert row["metrics"]["lead_time"]["median_lead_minutes"] == 10
    with pytest.raises(ValueError, match="week_not_finished"):
        record_week(store, WEEK + timedelta(days=7), after, "w3")
    with pytest.raises(ValueError, match="week_must_start_on_monday"):
        record_week(store, WEEK + timedelta(days=1), after, "w3")


def test_the_last_full_week_is_in_new_york_time():
    # 04:30 UTC on Monday 23 Nov is still Sunday evening in New York (EST, UTC-5).
    assert last_full_week(datetime(2026, 11, 23, 4, 30, tzinfo=UTC)) == date(2026, 11, 9)
    assert last_full_week(datetime(2026, 11, 23, 5, 30, tzinfo=UTC)) == date(2026, 11, 16)


def bearer(user: str) -> dict:
    token = mint_token({"sub": user, "role": "authenticated", "aud": "authenticated",
                        "iss": TEST_ISSUER, "exp": int((NOW + timedelta(hours=1)).timestamp())})
    return {"Authorization": "Bearer " + token}


def test_only_listed_owners_can_read_the_pilot_report(pilot, auth_env, monkeypatch):
    store, _ = pilot
    record_week(store, WEEK, week_bounds(WEEK)[1] + timedelta(hours=1), "w1")
    owner, other = str(uuid4()), str(uuid4())
    app.dependency_overrides[user_store] = lambda: store
    app.dependency_overrides[auth_now] = lambda: NOW
    try:
        client = TestClient(app)
        monkeypatch.delenv("SWEET_SEATS_ADMIN_USER_IDS", raising=False)
        assert client.get("/v1/admin/pilot", headers=bearer(owner)).status_code == 404
        monkeypatch.setenv("SWEET_SEATS_ADMIN_USER_IDS", f"not-a-uuid, {owner}")
        assert client.get("/v1/admin/pilot", headers=bearer(other)).status_code == 404
        assert client.get("/v1/admin/pilot").status_code == 401
        response = client.get("/v1/admin/pilot", headers=bearer(owner))
        assert response.status_code == 200
        assert response.headers["cache-control"].startswith("private, no-store")
        weeks = response.json()["weeks"]
        assert [w["period_start"] for w in weeks] == ["2026-10-12"]
        assert weeks[0]["metrics"]["lead_time"]["median_lead_minutes"] == 10
    finally:
        app.dependency_overrides.pop(user_store, None)
        app.dependency_overrides.pop(auth_now, None)
