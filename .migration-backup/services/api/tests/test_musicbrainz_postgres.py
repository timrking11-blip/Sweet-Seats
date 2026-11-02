"""MusicBrainz run lifecycle against the real migrations on disposable PostgreSQL.

The resolver runs unchanged; PostgresCache stands in for PostgREST by calling the same SQL
functions, one transaction per call. Skipped only when no explicit test DSN exists.
"""

import os
from uuid import UUID

import httpx
import psycopg
import pytest
from psycopg.rows import dict_row

from app.musicbrainz import (
    ADAPTER_VERSION,
    ArtistCandidate,
    ArtistResolver,
    CachedArtist,
    MusicBrainzClient,
    MusicBrainzError,
    OpenRun,
    SourceNotPermitted,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("SWEET_SEATS_TEST_DATABASE_URL"),
    reason="requires disposable local PostgreSQL DSN",
)
MBID = UUID("6c7a9f0b-3c1e-4d5a-9a43-0d0b3e1f7a11")
ARTIST = {"id": str(MBID), "name": "Synthetic Artist", "disambiguation": ""}


class PostgresCache:
    def __init__(self, conn) -> None:
        self.conn = conn

    def _call(self, query, params, denied_use="derived_retention"):
        try:
            return self.conn.execute(query, params).fetchall()
        except psycopg.errors.InsufficientPrivilege:
            raise SourceNotPermitted(denied_use) from None
        except psycopg.Error as exc:
            raise MusicBrainzError(type(exc).__name__) from None

    def permitted(self, use):
        return self._call("SELECT public.musicbrainz_use_is_permitted(%s) AS ok", (use,))[0]["ok"]

    def by_mbid(self, mbid):
        rows = self._call("SELECT * FROM public.musicbrainz_artist_by_mbid(%s)", (mbid,))
        return CachedArtist(name=rows[0]["canonical_name"], **{
            k: rows[0][k] for k in ("artist_id", "mbid", "disambiguation", "mapping_method")
        }, mapping_confidence=float(rows[0]["mapping_confidence"])) if rows else None

    def by_name(self, name):
        return []

    def store(self, artist, *, confidence, method, collection_run_id):
        self._call(
            "SELECT public.cache_musicbrainz_artist(%s,%s,%s::text,%s::numeric,%s,%s)",
            (artist.mbid, artist.name, artist.disambiguation, confidence, method, collection_run_id),
        )
        return self.by_mbid(artist.mbid)

    def begin_run(self, logical_key):
        [row] = self._call(
            "SELECT * FROM public.begin_musicbrainz_run(%s,%s)", (logical_key, ADAPTER_VERSION),
            denied_use="collect",
        )
        return OpenRun.model_validate(row)

    def finish_run(self, collection_run_id, status, item_count, error_code):
        self._call(
            "SELECT public.finish_musicbrainz_run(%s,%s,%s,%s)",
            (collection_run_id, status, item_count, error_code),
        )


@pytest.fixture
def mb(pg_store):
    store, _ = pg_store
    with psycopg.connect(store.dsn, autocommit=True, row_factory=dict_row) as conn:
        yield conn


def approve(conn, *, approved_at="now() - interval '1 day'"):
    conn.execute("UPDATE public.sources SET access_status='approved' WHERE slug='musicbrainz'")
    return conn.execute(
        f"""INSERT INTO public.source_permissions (source_id, terms_url, terms_version,
            evidence_note, collect_allowed, derived_retention_allowed, approved_at, created_at)
            SELECT source_id, 'https://example.test/terms', 'synthetic', 'synthetic', true, true,
                   {approved_at}, now() - interval '2 days'
            FROM public.sources WHERE slug='musicbrainz' RETURNING permission_id"""
    ).fetchone()["permission_id"]


def runs(conn):
    return conn.execute(
        """SELECT r.* FROM public.collection_runs r JOIN public.sources s USING (source_id)
           WHERE s.slug='musicbrainz' ORDER BY r.started_at"""
    ).fetchall()


def resolver(conn, handler, requests):
    def counted(request):
        requests.append(request)
        return handler(request)

    client = MusicBrainzClient(
        "SweetSeats/0.1.0 ( test@example.invalid )",
        http=httpx.Client(transport=httpx.MockTransport(counted)), sleep=lambda s: None,
    )
    return ArtistResolver(client, PostgresCache(conn))


def ok(request):
    return httpx.Response(200, json=ARTIST)


@pytest.mark.parametrize("approved_at", [None, "now() + interval '1 hour'"])
def test_no_qualifying_permission_means_no_run_no_request_no_cache(mb, approved_at):
    if approved_at:
        approve(mb, approved_at=approved_at)  # approved after the run would start
    requests = []
    with pytest.raises(SourceNotPermitted):
        resolver(mb, ok, requests).resolve_mbid(MBID)
    assert requests == [] and runs(mb) == []
    assert mb.execute("SELECT count(*) AS n FROM public.source_entity_mappings").fetchone()["n"] == 0


def test_resolution_finalizes_the_row_opened_with_its_permission(mb):
    permission_id = approve(mb)
    requests = []
    result = resolver(mb, ok, requests).resolve_mbid(MBID)
    [run] = runs(mb)
    assert result.status == "resolved" and result.collection_run_id == run["collection_run_id"]
    assert run["permission_id"] == permission_id
    assert (run["status"], run["item_count"], run["error_code"]) == ("succeeded", 1, None)
    assert run["finished_at"] >= run["started_at"]
    assert len(requests) == 1


def test_retries_share_one_run(mb):
    approve(mb)
    responses = iter([httpx.Response(503), httpx.Response(503), httpx.Response(200, json=ARTIST)])
    requests = []
    result = resolver(mb, lambda r: next(responses), requests).resolve_mbid(MBID)
    assert result.status == "resolved" and len(requests) == 3
    assert [(r["status"], r["item_count"]) for r in runs(mb)] == [("succeeded", 1)]


def test_unfinalized_run_stays_failed_and_nothing_is_cached(mb, monkeypatch):
    approve(mb)

    def broken(self, *args):
        raise MusicBrainzError("finish failed")

    monkeypatch.setattr(PostgresCache, "finish_run", broken)
    with pytest.raises(MusicBrainzError) as exc:
        resolver(mb, ok, []).resolve_mbid(MBID)
    assert exc.value.code == "run_not_finalized"
    [run] = runs(mb)
    assert (run["status"], run["error_code"], run["finished_at"]) == ("failed", "incomplete", None)
    with pytest.raises(MusicBrainzError):
        PostgresCache(mb).store(
            ArtistCandidate(mbid=MBID, name="Synthetic Artist"), confidence=1.0,
            method="musicbrainz-lookup", collection_run_id=run["collection_run_id"],
        )
    assert mb.execute("SELECT count(*) AS n FROM public.source_entity_mappings").fetchone()["n"] == 0
