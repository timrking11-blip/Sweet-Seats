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
