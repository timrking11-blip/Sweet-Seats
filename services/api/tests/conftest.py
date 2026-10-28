"""Shared disposable local database fixture (explicit opt-in DSN)."""

import json
import os
from contextlib import contextmanager
from uuid import uuid4

import pytest
from psycopg import sql

from app.discovery import DEFAULT_FIXTURE
from app.discovery_postgres import PostgresStore

DSN = os.environ.get("SWEET_SEATS_TEST_DATABASE_URL")
ROOT = DEFAULT_FIXTURE.parents[3]
MIGRATIONS = sorted((ROOT / "supabase/migrations").glob("*.sql"))


def apply_migrations(store, paths) -> None:
    with store._connect() as conn:
        for path in paths:
            conn.execute(path.read_text())


@contextmanager
def disposable_store(migrations):
    if not DSN:
        pytest.skip("requires disposable local PostgreSQL DSN")
    # Separate database per test: no shared-schema truncation or remote migrations.
    admin = PostgresStore(DSN)
    name = "discovery_test_" + uuid4().hex
    with admin._connect() as conn:
        conn.autocommit = True
        conn.execute(
            sql.SQL("CREATE DATABASE {} ENCODING 'UTF8' TEMPLATE template0").format(
                sql.Identifier(name)
            )
        )
    from psycopg.conninfo import make_conninfo

    store = PostgresStore(make_conninfo(DSN, dbname=name))
    try:
        with store._connect() as conn:
            conn.execute((ROOT / "supabase/ci/emulate_supabase_roles.sql").read_text())
            conn.execute((ROOT / "supabase/ci/emulate_supabase_auth.sql").read_text())
        apply_migrations(store, migrations)
        yield store
    finally:
        with admin._connect() as conn:
            conn.autocommit = True
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def pg_store():
    with disposable_store(MIGRATIONS) as store:
        yield store, json.loads(DEFAULT_FIXTURE.read_text())


# The newest migration on main before the Phase 2 runtime schema. A database already at
# this point is upgraded by applying every migration that sorts after it.
UPGRADE_BASE = "20261026120000_discovery_unresolved_records.sql"


@pytest.fixture
def pg_upgrade():
    """A store at the upgrade base schema, and a callable applying the later migrations."""
    before = [p for p in MIGRATIONS if p.name <= UPGRADE_BASE]
    after = [p for p in MIGRATIONS if p.name > UPGRADE_BASE]
    assert before[-1].name == UPGRADE_BASE and after
    with disposable_store(before) as store:
        yield store, json.loads(DEFAULT_FIXTURE.read_text()), lambda: apply_migrations(store, after)
