"""The Python and SQL rights checks must agree, case by case.

discovery.permitted mirrors public.source_use_is_permitted. Each case runs through
both. The one deliberate difference is listed in KNOWN_DIVERGENCE so that changing
either side, in either direction, fails here until the owner records a decision.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.discovery import permitted

NOW = datetime(2026, 10, 18, 12, tzinfo=UTC)
PAST, FUTURE = NOW - timedelta(days=30), NOW + timedelta(days=30)

BASE = {"status": "approved", "approved": PAST, "revoked": None, "expires": FUTURE,
        "evidence": "evidence", "terms": "v1", "collect": True}

CASES = {
    "valid approved": {},
    "valid active": {"status": "active"},
    "planned source": {"status": "planned"},
    "suspended source": {"status": "suspended"},
    "revoked source": {"status": "revoked"},
    "use not granted": {"collect": False},
    "missing approval": {"approved": None},
    "future approval": {"approved": FUTURE},
    "approval exactly now": {"approved": NOW},
    "past revocation": {"revoked": PAST + timedelta(days=1)},
    "future revocation": {"revoked": FUTURE},
    "revocation exactly now": {"revoked": NOW},
    "past expiry": {"expires": PAST + timedelta(days=1)},
    "expiry exactly now": {"expires": NOW},
    "empty evidence": {"evidence": "  "},
    "empty terms version": {"terms": ""},
    "no expiry": {"expires": None},
}

# Python treats a missing expiry as unknown and denies; SQL permits it, and
# supabase/tests/source_permissions_test.sql pins that. Owner decision pending.
KNOWN_DIVERGENCE = {"no expiry": {"python": False, "sql": True}}


def python_result(case: dict) -> bool:
    def iso(value):
        return value.isoformat() if value else None

    source = {"access_status": case["status"], "permission": {
        "uses": {"collect": case["collect"]}, "evidence_ref": case["evidence"],
        "terms_version": case["terms"], "approved_at": iso(case["approved"]),
        "expires_at": iso(case["expires"]), "revoked_at": iso(case["revoked"])}}
    return permitted(source, "collect", NOW)


def sql_result(conn, case: dict) -> bool:
    source_id = uuid4()
    conn.execute(
        """INSERT INTO sources(source_id, slug, name, official_url, source_type, access_status)
           VALUES (%s, %s, 'parity', 'https://parity.invalid', 'synthetic', %s)""",
        (source_id, "parity-" + source_id.hex[:12], case["status"]))
    conn.execute(
        """INSERT INTO source_permissions(source_id, terms_url, terms_version, evidence_note,
               collect_allowed, approved_at, revoked_at, expires_at, created_at)
           VALUES (%s, 'https://terms.invalid', %s, %s, %s, %s, %s, %s, %s)""",
        (source_id, case["terms"], case["evidence"], case["collect"], case["approved"],
         case["revoked"], case["expires"], PAST - timedelta(days=1)))
    return conn.execute("SELECT source_use_is_permitted(%s, 'collect', %s) AS ok",
                        (source_id, NOW)).fetchone()["ok"]


@pytest.mark.parametrize("name", sorted(CASES))
def test_python_and_sql_rights_checks_agree(pg_store, name):
    store, _ = pg_store
    case = {**BASE, **CASES[name]}
    with store._connect() as conn:
        result = {"python": python_result(case), "sql": sql_result(conn, case)}
        conn.rollback()
    assert result == KNOWN_DIVERGENCE.get(name, {"python": result["sql"], "sql": result["sql"]})
