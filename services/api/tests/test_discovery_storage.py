"""Storage selection and validation checks that never require a running database."""

import copy
import json

import pytest
from fastapi.testclient import TestClient

from app.discovery import (
    DEFAULT_FIXTURE,
    DiscoveryError,
    FixtureStore,
    empty_state,
    ingest,
    timestamp,
)
from app.discovery_postgres import PostgresStore, configured_store
from app.main import app


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://postgres@remote.example/db",
        "postgresql://postgres@localhost/db?hostaddr=10.0.0.1",
        "service=production",
        "broken",
    ],
)
def test_remote_or_ambiguous_database_dsn_denied(dsn):
    with pytest.raises(DiscoveryError, match="local_database_required"):
        PostgresStore(dsn)


def test_explicit_configuration_does_not_fall_back_to_json(monkeypatch):
    monkeypatch.delenv("SWEET_SEATS_LOCAL_DATABASE_URL", raising=False)
    assert isinstance(configured_store(), FixtureStore)
    monkeypatch.setenv(
        "SWEET_SEATS_LOCAL_DATABASE_URL", "postgresql://secret:canary@remote.example/db"
    )
    with TestClient(app) as client:
        response = client.get("/v1/events")
    assert response.status_code == 503
    assert "canary" not in response.text


def test_fixture_date_and_typed_mapping_consistency():
    fixture = json.loads(DEFAULT_FIXTURE.read_text())
    now = timestamp("2026-10-18T07:00:00Z")
    first = ingest(empty_state(), fixture, now)
    revised = copy.deepcopy(fixture)
    revised["sources"][0]["artist_mappings"]["Violet Static"] = next(
        k
        for k in fixture["identities"]["artists"]
        if k != revised["sources"][0]["artist_mappings"]["Violet Static"]
    )
    with pytest.raises(DiscoveryError, match="identity_crosswalk_revision_requires_review"):
        ingest(first, revised, now)
    fixture["batches"][0]["records"][0]["local_date"] = "2026-11-07"
    with pytest.raises(DiscoveryError, match="local_date_timezone_mismatch"):
        ingest(empty_state(), fixture, now)


def test_inherited_hostaddr_cannot_redirect_local_database(monkeypatch):
    import app.discovery_postgres as module

    captured = {}
    monkeypatch.setenv("PGHOSTADDR", "203.0.113.1")
    monkeypatch.setattr(module.psycopg, "connect", lambda *args, **kwargs: captured.update(kwargs))
    PostgresStore("postgresql://postgres@localhost/discovery")._connect()
    assert captured["hostaddr"] == "127.0.0.1"
    PostgresStore("postgresql://postgres@[::1]/discovery")._connect()
    assert captured["hostaddr"] == "::1"


# A hosted (Supabase) database: only on explicit opt-in, only Supabase hosts, only TLS.
SUPABASE = "postgresql://postgres.ref:canary-secret@aws-0-us-east-1.pooler.supabase.com:6543/postgres"


@pytest.fixture
def hosted(monkeypatch):
    for name in ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SWEET_SEATS_ALLOW_HOSTED_DATABASE", "true")


@pytest.mark.parametrize("flag", [None, "", "1", "yes", "TRUE"])
def test_a_supabase_url_needs_the_explicit_opt_in(monkeypatch, flag):
    if flag is None:
        monkeypatch.delenv("SWEET_SEATS_ALLOW_HOSTED_DATABASE", raising=False)
    else:
        monkeypatch.setenv("SWEET_SEATS_ALLOW_HOSTED_DATABASE", flag)
    with pytest.raises(DiscoveryError, match="local_database_required"):
        PostgresStore(SUPABASE)


@pytest.mark.parametrize("dsn,code", [
    ("postgresql://postgres:canary-secret@remote.example/db", "hosted_database_not_supabase"),
    ("postgresql://postgres:canary-secret@db.ref.supabase.co.evil.example/db", "hosted_database_not_supabase"),
    ("postgresql://postgres:canary-secret@evilsupabase.co/db", "hosted_database_not_supabase"),
    (SUPABASE + "?sslmode=disable", "database_tls_required"),
    (SUPABASE + "?sslmode=prefer", "database_tls_required"),
    (SUPABASE + "?hostaddr=203.0.113.1", "local_database_required"),
    ("postgresql://postgres:canary-secret@db.ref.supabase.co,remote.example/db", "local_database_required"),
])
def test_hosted_urls_outside_the_rules_are_refused(hosted, dsn, code):
    with pytest.raises(DiscoveryError, match=code) as raised:
        PostgresStore(dsn)
    assert "canary" not in str(raised.value)


@pytest.mark.parametrize("dsn,sslmode", [(SUPABASE, "require"),
                                         (SUPABASE + "?sslmode=verify-full", "verify-full"),
                                         ("postgresql://postgres:x@db.ref.supabase.co:5432/postgres", "require")])
def test_a_supabase_connection_uses_tls_and_no_prepared_statements(hosted, monkeypatch, dsn, sslmode):
    import app.discovery_postgres as module

    captured = {}
    monkeypatch.setattr(module.psycopg, "connect", lambda *args, **kwargs: captured.update(kwargs))
    store = PostgresStore(dsn)
    assert store.hosted
    store._connect()
    assert captured["sslmode"] == sslmode
    assert captured["prepare_threshold"] is None
    assert "hostaddr" not in captured


@pytest.mark.parametrize("name", ["PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE"])
def test_an_environment_that_could_redirect_a_hosted_connection_is_refused(hosted, monkeypatch, name):
    import app.discovery_postgres as module

    monkeypatch.setattr(module.psycopg, "connect", lambda *a, **k: pytest.fail("connected"))
    store = PostgresStore(SUPABASE)
    monkeypatch.setenv(name, "203.0.113.1")
    with pytest.raises(DiscoveryError, match="store_unavailable"):
        store._connect()


def test_withdrawing_the_opt_in_stops_an_existing_store(hosted, monkeypatch):
    import app.discovery_postgres as module

    monkeypatch.setattr(module.psycopg, "connect", lambda *a, **k: pytest.fail("connected"))
    store = PostgresStore(SUPABASE)
    monkeypatch.setenv("SWEET_SEATS_ALLOW_HOSTED_DATABASE", "false")
    with pytest.raises(DiscoveryError, match="store_unavailable"):
        store._connect()


def test_the_new_variable_wins_over_the_old_name(monkeypatch):
    from app.discovery_postgres import configured_dsn

    monkeypatch.setenv("SWEET_SEATS_LOCAL_DATABASE_URL", "postgresql://postgres@localhost/old")
    assert configured_dsn() == "postgresql://postgres@localhost/old"
    monkeypatch.setenv("SWEET_SEATS_DATABASE_URL", "postgresql://postgres@localhost/new")
    assert configured_dsn() == "postgresql://postgres@localhost/new"


def test_a_hosted_url_is_refused_without_opt_in_and_never_leaks(monkeypatch):
    monkeypatch.delenv("SWEET_SEATS_ALLOW_HOSTED_DATABASE", raising=False)
    monkeypatch.setenv("SWEET_SEATS_DATABASE_URL", SUPABASE)
    with TestClient(app) as client:
        response = client.get("/v1/events")
    assert response.status_code == 503
    assert "canary" not in response.text
