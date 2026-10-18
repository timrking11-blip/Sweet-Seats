"""Shared disposable local database fixture (explicit opt-in DSN)."""

import json
import os
from uuid import uuid4

import pytest
from psycopg import sql

from app.discovery import DEFAULT_FIXTURE
from app.discovery_postgres import PostgresStore

DSN = os.environ.get("SWEET_SEATS_TEST_DATABASE_URL")


@pytest.fixture
def pg_store():
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
    root = DEFAULT_FIXTURE.parents[3]
    try:
        with store._connect() as conn:
            conn.execute((root / "supabase/ci/emulate_supabase_roles.sql").read_text())
            conn.execute((root / "supabase/ci/emulate_supabase_auth.sql").read_text())
            for path in sorted((root / "supabase/migrations").glob("*.sql")):
                conn.execute(path.read_text())
        yield store, json.loads(DEFAULT_FIXTURE.read_text())
    finally:
        with admin._connect() as conn:
            conn.autocommit = True
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
