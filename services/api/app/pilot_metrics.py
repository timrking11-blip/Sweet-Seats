"""Weekly pilot metrics (Build Plan S3, Step 6; proposed).

Computes the eight pilot measures in docs/phase-assessment.md for one week, from the
database only, and appends them to public.pilot_metrics. Weeks run Monday to Monday in
America/New_York, the pilot's market. A week is computed only once it has ended, and
once per metrics version: run_job makes a repeat a no-op, and the table refuses edits.

Baseline and treatment come from sources.source_type: 'event_listing_api' (Ticketmaster
Discovery, once approved) is the baseline; 'official_calendar' is the treatment. First
seen is the earliest available_at per (event, source) in public.event_first_seen, kept
only while the source still permits derived retention. A collection run belongs to
the week it finished in (or started in, if it never finished). The thresholds that decide the
pilot are the owner's; this module reports numbers, never a verdict.

    python -m services.api.app.pilot_metrics [--week YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from .alerts import run_job
from .discovery import median, summarize_first_seen

METRICS_VERSION = "pilot-metrics-v1"
MARKET = ZoneInfo("America/New_York")
BASELINE_TYPES = ("event_listing_api",)
TREATMENT_TYPES = ("official_calendar",)


def week_bounds(week_start: date) -> tuple[datetime, datetime]:
    if week_start.weekday() != 0:
        raise ValueError("week_must_start_on_monday")
    start = datetime.combine(week_start, time(), MARKET)
    return start, datetime.combine(week_start + timedelta(days=7), time(), MARKET)


def last_full_week(now: datetime) -> date:
    today = now.astimezone(MARKET).date()
    return today - timedelta(days=today.weekday() + 7)


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _first_seen(conn, start: datetime, end: datetime, now: datetime) -> dict:
    rows = conn.execute(
        """SELECT f.event_id, f.source_id, s.name, s.source_type,
                  min(f.first_available_at) AS first_at
           FROM event_first_seen f JOIN sources s USING (source_id)
           WHERE public.source_use_is_permitted(f.source_id, 'derived_retention', %s)
           GROUP BY f.event_id, f.source_id, s.name, s.source_type""", (now,)).fetchall()
    by_event: dict[str, dict[str, datetime]] = {}
    sources = {}
    for row in rows:
        by_event.setdefault(str(row["event_id"]), {})[str(row["source_id"])] = row["first_at"]
        sources[str(row["source_id"])] = row
    # An event belongs to the week in which any source first made it available.
    in_week = {event: seen for event, seen in by_event.items()
               if start <= min(seen.values()) < end}
    return {"by_event": in_week, "sources": sources}


def _lead_and_coverage(first: dict) -> tuple[dict, dict, list]:
    sources, by_event = first["sources"], first["by_event"]
    role = {sid: ("baseline" if row["source_type"] in BASELINE_TYPES else
                  "treatment" if row["source_type"] in TREATMENT_TYPES else None)
            for sid, row in sources.items()}
    leads, treatment_only, panel = [], 0, 0
    for seen in by_event.values():
        baseline = [at for sid, at in seen.items() if role[sid] == "baseline"]
        treatment = [at for sid, at in seen.items() if role[sid] == "treatment"]
        if not baseline and not treatment:
            continue
        panel += 1
        if treatment and not baseline:
            treatment_only += 1
        if baseline and treatment:
            # Positive: the official calendar had the show that many minutes earlier.
            leads.append((min(baseline) - min(treatment)).total_seconds() / 60)
    lead = {"shows_found_by_both": len(leads), "median_lead_minutes": median(leads),
            "treatment_earlier": sum(1 for x in leads if x > 0),
            "basis": "available_at; positive means the official calendar was earlier"}
    coverage = {"panel_shows": panel, "treatment_only": treatment_only,
                "rate": _ratio(treatment_only, panel)}
    per_source = summarize_first_seen(by_event, {sid: row["name"] for sid, row in sources.items()})
    for row in per_source:
        row["role"] = role[row["source_id"]]
    return lead, coverage, per_source


def compute(conn, week_start: date, now: datetime) -> dict:
    start, end = week_bounds(week_start)
    lead, coverage, per_source = _lead_and_coverage(_first_seen(conn, start, end, now))
    health = conn.execute(
        """SELECT s.name, count(*) AS runs,
                  count(*) FILTER (WHERE r.status IN ('failed', 'stale')) AS failed_or_stale
           FROM collection_runs r JOIN sources s USING (source_id)
           WHERE coalesce(r.finished_at, r.started_at) >= %s
             AND coalesce(r.finished_at, r.started_at) < %s
           GROUP BY s.name ORDER BY s.name""", (start, end)).fetchall()
    review = conn.execute(
        """SELECT (SELECT count(*) FROM source_event_records e JOIN collection_runs r
                     USING (collection_run_id) WHERE coalesce(r.finished_at, r.started_at) >= %(s)s
                       AND coalesce(r.finished_at, r.started_at) < %(e)s)
                    AS resolved,
                  (SELECT count(*) FROM source_unresolved_records u JOIN collection_runs r
                     USING (collection_run_id) WHERE coalesce(r.finished_at, r.started_at) >= %(s)s
                       AND coalesce(r.finished_at, r.started_at) < %(e)s)
                    AS unresolved""", {"s": start, "e": end}).fetchone()
    alerts = conn.execute(
        """SELECT count(*) FILTER (WHERE status = 'sent') AS sent,
                  count(*) FILTER (WHERE suppressed_reason = 'trigger_obsolete') AS obsolete,
                  count(*) FILTER (WHERE status = 'failed') AS failed,
                  count(*) FILTER (WHERE status = 'suppressed') AS suppressed
           FROM alerts WHERE created_at >= %s AND created_at < %s""", (start, end)).fetchone()
    engagement = conn.execute(
        """WITH delivered AS (
             SELECT DISTINCT alert_id FROM alert_deliveries
             WHERE status = 'sent' AND sent_at >= %(s)s AND sent_at < %(e)s)
           SELECT (SELECT count(*) FROM delivered) AS delivered,
                  (SELECT count(DISTINCT o.alert_id) FROM outcome_events o JOIN delivered d
                     USING (alert_id) WHERE o.kind IN ('alert_opened', 'link_clicked')) AS engaged,
                  (SELECT count(*) FROM outcome_events WHERE kind = 'purchase_confirmed'
                     AND occurred_at >= %(s)s AND occurred_at < %(e)s) AS purchases""",
        {"s": start, "e": end}).fetchone()
    collected = review["resolved"] + review["unresolved"]
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat(), "timezone": MARKET.key},
        "incremental_coverage": coverage,
        "lead_time": lead,
        "lead_time_by_source": [{k: v for k, v in row.items() if k != "source_id"}
                                for row in per_source],
        "source_health": [{"source": r["name"], "runs": r["runs"],
                           "failed_or_stale": r["failed_or_stale"],
                           "rate": _ratio(r["failed_or_stale"], r["runs"])} for r in health],
        "review_rate": {"unresolved": review["unresolved"], "collected": collected,
                        "rate": _ratio(review["unresolved"], collected)},
        "alert_quality": {"sent": alerts["sent"], "obsolete": alerts["obsolete"],
                          "failed": alerts["failed"], "suppressed": alerts["suppressed"],
                          "obsolete_rate": _ratio(alerts["obsolete"], alerts["sent"] + alerts["obsolete"]),
                          "duplicates": "prevented by alerts.dedupe_key",
                          "missed": "needs the manual audit of a sample"},
        "engagement": {"delivered_alerts": engagement["delivered"],
                       "opened_or_clicked": engagement["engaged"],
                       "rate": _ratio(engagement["engaged"], engagement["delivered"]),
                       "basis": "outcome_events exist only for users with outcome consent"},
        "purchases": {"confirmed": engagement["purchases"],
                      "basis": "purchase_confirmed only; a click is never a purchase"},
        "cost_per_useful_alert": {"value": None, "reason": "cost inputs are not recorded yet"},
    }


def record_week(store, week_start: date, now: datetime, worker: str) -> dict | None:
    """Compute one finished week and append it. None if this week and version already ran."""
    _, end = week_bounds(week_start)
    if end > now:
        raise ValueError("week_not_finished")
    with store._connect() as conn:
        conn.autocommit = True

        def work() -> dict:
            metrics = compute(conn, week_start, now)
            with conn.transaction():
                inserted = conn.execute(
                    """INSERT INTO pilot_metrics(period_start, period_end, metrics_version, metrics)
                       VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                    (week_start, week_start + timedelta(days=7), METRICS_VERSION,
                     Jsonb(metrics))).rowcount
            return {"week": week_start.isoformat(), "inserted": inserted}

        return run_job(conn, "pilot_metrics", f"{week_start.isoformat()}:{METRICS_VERSION}",
                       work, now, worker)


def main() -> None:
    parser = argparse.ArgumentParser(description="Append one week of pilot metrics.")
    parser.add_argument("--week", type=date.fromisoformat, default=None,
                        help="Monday that starts the week (default: the last full week)")
    args = parser.parse_args()
    from .discovery_postgres import PostgresStore, configured_dsn

    dsn = configured_dsn()
    if not dsn:
        parser.exit(1, "SWEET_SEATS_DATABASE_URL is required.\n")
    now = datetime.now(UTC)
    week = args.week or last_full_week(now)
    result = record_week(PostgresStore(dsn), week, now, "metrics-" + uuid4().hex[:8])
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
