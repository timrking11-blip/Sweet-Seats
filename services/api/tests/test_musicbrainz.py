import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest

from app.musicbrainz import (
    ADAPTER_VERSION,
    MAX_RETRY_AFTER_SECONDS,
    ArtistCandidate,
    ArtistResolver,
    CachedArtist,
    MusicBrainzClient,
    MusicBrainzError,
    OpenRun,
    SourceNotPermitted,
    SupabaseArtistCache,
    run_key,
    user_agent,
)

MBID = UUID("6c7a9f0b-3c1e-4d5a-9a43-0d0b3e1f7a11")
OTHER_MBID = UUID("0f3e2a1b-7c6d-4e5f-8a9b-1c2d3e4f5a6b")
PERMISSION_ID = UUID("5d1f0c2e-8b3a-4f6d-9e7c-2a1b3c4d5e6f")
UA = "SweetSeats/0.1.0 ( test@example.invalid )"


def artist_json(mbid=MBID, name="Test Artist", score=100, disambiguation=""):
    return {"id": str(mbid), "name": name, "sort-name": name, "score": score,
            "disambiguation": disambiguation}


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def mb_client(handler, clock: FakeClock | None = None) -> MusicBrainzClient:
    clock = clock or FakeClock()
    return MusicBrainzClient(
        UA, http=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=clock.clock, sleep=clock.sleep,
    )


def no_network(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"unexpected request to {request.url}")


class MemoryCache:
    """Mirrors the database contract in 202610180001/202610180002: begin_run checks collect and
    captures a permission, finish_run finalizes an open run once, and store needs that run
    finalized as succeeded. events records the order of run and network activity."""

    def __init__(self, uses: set[str] = frozenset({"collect", "derived_retention"})) -> None:
        self.uses = set(uses)
        self.rows: dict[UUID, CachedArtist] = {}
        self.runs: dict[UUID, dict] = {}
        self.events: list[tuple[str, object]] = []
        self.begin_error: Exception | None = None
        self.finish_error: Exception | None = None

    def permitted(self, use):
        return use in self.uses

    def by_mbid(self, mbid):
        return self.rows.get(mbid)

    def by_name(self, name):
        return [r for r in self.rows.values() if r.name.casefold() == name.strip().casefold()]

    def seed(self, artist: ArtistCandidate) -> CachedArtist:
        """A row cached by an earlier run."""
        row = CachedArtist(
            artist_id=uuid4(), mbid=artist.mbid, name=artist.name,
            disambiguation=artist.disambiguation, mapping_confidence=0.9, mapping_method="m",
        )
        self.rows[artist.mbid] = row
        return row

    def store(self, artist: ArtistCandidate, *, confidence, method, collection_run_id):
        run = self.runs.get(collection_run_id)
        if not run or run["status"] != "succeeded" or not run["finished"]:
            raise MusicBrainzError("no succeeded run", code="musicbrainz_run_required")
        self.events.append(("store", collection_run_id))
        row = self.rows.get(artist.mbid) or CachedArtist(
            artist_id=uuid4(), mbid=artist.mbid, name=artist.name,
            disambiguation=artist.disambiguation, mapping_confidence=confidence,
            mapping_method=method,
        )
        self.rows[artist.mbid] = row
        return row

    def begin_run(self, logical_key):
        if self.begin_error:
            raise self.begin_error
        if "collect" not in self.uses:
            raise SourceNotPermitted("collect")
        run = OpenRun(
            collection_run_id=uuid4(), permission_id=PERMISSION_ID, started_at=datetime.now(UTC)
        )
        self.runs[run.collection_run_id] = {
            "logical_key": logical_key, "permission_id": run.permission_id,
            "status": "failed", "item_count": 0, "error_code": "incomplete", "finished": False,
        }
        self.events.append(("begin", run.collection_run_id))
        return run

    def finish_run(self, collection_run_id, status, item_count, error_code):
        if self.finish_error:
            raise self.finish_error
        run = self.runs[collection_run_id]
        assert not run["finished"], "a run is finalized once"
        run.update(status=status, item_count=item_count, error_code=error_code, finished=True)
        self.events.append(("finish", collection_run_id))

    def finished(self):
        return [r for r in self.runs.values() if r["finished"]]


def tracked(cache: MemoryCache, handler):
    """Wraps a handler so each HTTP attempt is logged in cache.events."""

    def wrapper(request):
        cache.events.append(("request", request.url.path))
        return handler(request)

    return wrapper


def test_user_agent_requires_contact():
    with pytest.raises(MusicBrainzError, match="MUSICBRAINZ_CONTACT"):
        user_agent("  ")
    assert user_agent("ops@example.invalid") == "SweetSeats/0.1.0 ( ops@example.invalid )"


def test_search_sends_escaped_phrase_query_json_and_user_agent():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"artists": [artist_json(name='Say "Hi"')]})

    results = mb_client(handler).search_artists(' Say "Hi" ')

    request = seen[0]
    assert request.url.path == "/ws/2/artist"
    assert request.url.params["query"] == 'artist:"Say \\"Hi\\""'
    assert request.url.params["fmt"] == "json"
    assert request.headers["user-agent"] == UA
    assert "authorization" not in request.headers
    assert results == [ArtistCandidate(mbid=MBID, name='Say "Hi"', score=100)]


def test_requests_are_spaced_one_second_apart():
    clock = FakeClock()
    client = mb_client(lambda r: httpx.Response(200, json={"artists": []}), clock)
    client.search_artists("A")
    client.search_artists("B")
    assert clock.sleeps == [1.0]


def test_rate_limit_503_is_retried_after_retry_after():
    clock = FakeClock()
    responses = iter([httpx.Response(503, headers={"Retry-After": "3"}),
                      httpx.Response(200, json=artist_json())])
    artist = mb_client(lambda r: next(responses), clock).get_artist(MBID)
    assert artist.mbid == MBID
    assert 3.0 in clock.sleeps


def test_persistent_server_error_raises_without_payload():
    client = mb_client(lambda r: httpx.Response(502, text="secret upstream detail"))
    with pytest.raises(MusicBrainzError) as exc:
        client.get_artist(MBID)
    assert "secret" not in str(exc.value)


def test_unknown_mbid_is_none():
    assert mb_client(lambda r: httpx.Response(404)).get_artist(MBID) is None


def test_cached_name_skips_network_and_permission_check():
    cache = MemoryCache()
    cache.seed(ArtistCandidate(mbid=MBID, name="Test Artist"))
    cache.uses = set()
    result = ArtistResolver(mb_client(no_network), cache).resolve_name("test artist")
    assert result.status == "cached" and result.artist.mbid == MBID


def test_collect_not_permitted_fails_closed_before_network():
    resolver = ArtistResolver(mb_client(no_network), MemoryCache(uses=set()))
    with pytest.raises(SourceNotPermitted):
        resolver.resolve_name("Test Artist")
    with pytest.raises(SourceNotPermitted):
        resolver.resolve_mbid(MBID)


def test_unique_exact_match_is_cached_then_served_from_cache():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"artists": [
            artist_json(), artist_json(OTHER_MBID, "Test Artists", score=88)]})

    cache = MemoryCache()
    resolver = ArtistResolver(mb_client(handler), cache)
    first = resolver.resolve_name("Test Artist")
    second = resolver.resolve_name("Test Artist")

    assert first.status == "resolved"
    assert first.artist.mapping_confidence == 0.9
    assert first.artist.mapping_method == "musicbrainz-search-exact"
    assert second.status == "cached" and second.artist.artist_id == first.artist.artist_id
    assert len(calls) == 1


def test_namesakes_are_ambiguous_and_not_cached():
    def handler(request):
        return httpx.Response(200, json={"artists": [
            artist_json(MBID, disambiguation="US rapper"),
            artist_json(OTHER_MBID, disambiguation="UK band"),
        ]})

    cache = MemoryCache()
    result = ArtistResolver(mb_client(handler), cache).resolve_name("Test Artist")
    assert result.status == "ambiguous"
    assert {c.disambiguation for c in result.candidates} == {"US rapper", "UK band"}
    assert cache.rows == {}


def test_fuzzy_only_hits_are_ambiguous():
    handler = lambda r: httpx.Response(200, json={"artists": [artist_json(name="Tst Artist", score=92)]})
    result = ArtistResolver(mb_client(handler), MemoryCache()).resolve_name("Test Artist")
    assert result.status == "ambiguous" and len(result.candidates) == 1


def test_no_hits_is_not_found():
    handler = lambda r: httpx.Response(200, json={"artists": []})
    assert ArtistResolver(mb_client(handler), MemoryCache()).resolve_name("Nobody").status == "not_found"


def test_match_without_retention_permission_is_returned_uncached():
    cache = MemoryCache(uses={"collect"})
    handler = lambda r: httpx.Response(200, json=artist_json())
    result = ArtistResolver(mb_client(handler), cache).resolve_mbid(MBID)
    assert result.status == "uncached" and result.candidates[0].mbid == MBID
    assert cache.rows == {}


def test_mbid_lookup_is_cached_with_full_confidence():
    handler = lambda r: httpx.Response(200, json={k: v for k, v in artist_json().items() if k != "score"})
    result = ArtistResolver(mb_client(handler), MemoryCache()).resolve_mbid(MBID)
    assert result.status == "resolved"
    assert result.artist.mapping_confidence == 1.0
    assert result.artist.mapping_method == "musicbrainz-lookup"


def supabase(handler, key="sb_secret_test"):
    return SupabaseArtistCache(
        "https://project.supabase.invalid/", key,
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_supabase_cache_calls_rpc_with_server_key_only_in_apikey_for_new_keys():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=True)

    assert supabase(handler).permitted("collect") is True
    request = seen[0]
    assert str(request.url) == "https://project.supabase.invalid/rest/v1/rpc/musicbrainz_use_is_permitted"
    assert json.loads(request.content) == {"requested_use": "collect"}
    assert request.headers["apikey"] == "sb_secret_test"
    assert "authorization" not in request.headers


def test_supabase_cache_sends_bearer_for_legacy_jwt_keys():
    seen = []
    supabase(lambda r: seen.append(r) or httpx.Response(200, json=False), key="eyJ.test").permitted(
        "collect"
    )
    assert seen[0].headers["authorization"] == "Bearer eyJ.test"


def test_supabase_store_writes_with_its_run_then_reads_back():
    artist_id, run_id = uuid4(), uuid4()
    calls = []

    def handler(request):
        function = request.url.path.rsplit("/", 1)[-1]
        calls.append((function, json.loads(request.content)))
        if function == "cache_musicbrainz_artist":
            return httpx.Response(200, json=str(artist_id))
        return httpx.Response(200, json=[{
            "artist_id": str(artist_id), "mbid": str(MBID), "canonical_name": "Test Artist",
            "disambiguation": None, "mapping_confidence": "0.900",
            "mapping_method": "musicbrainz-search-exact",
        }])

    stored = supabase(handler).store(
        ArtistCandidate(mbid=MBID, name="Test Artist"), confidence=0.9,
        method="musicbrainz-search-exact", collection_run_id=run_id,
    )
    assert stored.artist_id == artist_id and stored.mapping_confidence == 0.9
    assert calls[0] == ("cache_musicbrainz_artist", {
        "requested_mbid": str(MBID), "artist_name": "Test Artist", "artist_disambiguation": None,
        "confidence": 0.9, "method": "musicbrainz-search-exact", "run_id": str(run_id),
    })
    assert calls[1][0] == "musicbrainz_artist_by_mbid"


def test_supabase_permission_denied_maps_to_source_not_permitted():
    with pytest.raises(SourceNotPermitted) as exc:
        supabase(lambda r: httpx.Response(403, json={"code": "42501"})).store(
            ArtistCandidate(mbid=MBID, name="Test Artist"), confidence=1.0, method="m",
            collection_run_id=uuid4(),
        )
    assert exc.value.use == "derived_retention"


def test_supabase_cache_requires_configuration():
    with pytest.raises(MusicBrainzError, match="SUPABASE_URL"):
        SupabaseArtistCache("", "")


# Collection runs: one logical network request is one run, opened before the request and
# finalized after it. Cache hits and denials open none.

# Mirrors the logical_key check in 202610180002_musicbrainz_collection_runs.sql.
RUN_KEY = re.compile(
    r"^artist-(search:[0-9a-f]{64}|lookup:[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}):[0-9a-f]{32}$"
)


def name_hash(name):
    return hashlib.sha256(name.casefold().encode()).hexdigest()


def test_run_is_opened_before_the_request_and_that_row_is_finalized():
    cache = MemoryCache()
    handler = tracked(cache, lambda r: httpx.Response(200, json={"artists": [
        artist_json(), artist_json(OTHER_MBID, "Test Artists", score=88)]}))
    result = ArtistResolver(mb_client(handler), cache).resolve_name("Test Artist")

    [(run_id, run)] = cache.runs.items()
    assert [kind for kind, _ in cache.events] == ["begin", "request", "finish", "store"]
    assert cache.events[0][1] == cache.events[2][1] == cache.events[3][1] == run_id
    assert result.status == "resolved" and result.collection_run_id == run_id
    assert (run["status"], run["item_count"], run["error_code"]) == ("succeeded", 2, None)
    assert run["permission_id"] == PERMISSION_ID
    assert RUN_KEY.match(run["logical_key"])
    assert run["logical_key"].startswith(f"artist-search:{name_hash('test artist')}:")
    assert "test" not in run["logical_key"].casefold().replace(name_hash("test artist"), "")


def test_ambiguous_search_still_finalizes_its_run():
    handler = lambda r: httpx.Response(200, json={"artists": [
        artist_json(MBID, disambiguation="US rapper"),
        artist_json(OTHER_MBID, disambiguation="UK band"),
    ]})
    cache = MemoryCache()
    result = ArtistResolver(mb_client(handler), cache).resolve_name("Test Artist")
    assert result.status == "ambiguous" and result.collection_run_id in cache.runs
    assert [(r["status"], r["item_count"]) for r in cache.finished()] == [("succeeded", 2)]


def test_search_without_hits_finalizes_empty_run():
    cache = MemoryCache()
    handler = lambda r: httpx.Response(200, json={"artists": []})
    result = ArtistResolver(mb_client(handler), cache).resolve_name("Nobody")
    assert result.status == "not_found" and result.collection_run_id in cache.runs
    assert [(r["status"], r["item_count"], r["error_code"]) for r in cache.finished()] == [
        ("empty", 0, None)
    ]


def test_lookup_runs_are_keyed_by_mbid():
    cache = MemoryCache()
    found = ArtistResolver(mb_client(lambda r: httpx.Response(200, json=artist_json())), cache)
    missing = ArtistResolver(mb_client(lambda r: httpx.Response(404)), cache)

    assert found.resolve_mbid(MBID).status == "resolved"
    assert missing.resolve_mbid(OTHER_MBID).status == "not_found"

    runs = list(cache.runs.values())
    assert [(r["status"], r["item_count"]) for r in runs] == [("succeeded", 1), ("empty", 0)]
    assert runs[0]["logical_key"].startswith(f"artist-lookup:{MBID}:")
    assert runs[1]["logical_key"].startswith(f"artist-lookup:{OTHER_MBID}:")
    assert all(RUN_KEY.match(r["logical_key"]) for r in runs)


def test_uncached_match_finalizes_run():
    cache = MemoryCache(uses={"collect"})
    result = ArtistResolver(
        mb_client(lambda r: httpx.Response(200, json=artist_json())), cache
    ).resolve_mbid(MBID)
    assert result.status == "uncached" and result.collection_run_id in cache.runs
    assert [r["status"] for r in cache.finished()] == ["succeeded"]


@pytest.mark.parametrize(
    ("handler", "code"),
    [
        (lambda r: httpx.Response(502, text="secret upstream detail"), "upstream_unavailable"),
        (lambda r: httpx.Response(400, text="secret upstream detail"), "unexpected_status"),
        (lambda r: httpx.Response(200, text="secret not json"), "invalid_json"),
        (lambda r: httpx.Response(200, json={"secret": "shape"}), "unexpected_shape"),
    ],
)
def test_failed_lookup_finalizes_fixed_error_code_and_reraises(handler, code):
    cache = MemoryCache()
    with pytest.raises(MusicBrainzError) as exc:
        ArtistResolver(mb_client(handler), cache).resolve_mbid(MBID)
    assert exc.value.code == code
    [run] = cache.finished()
    assert (run["status"], run["item_count"], run["error_code"]) == ("failed", 0, code)
    assert "secret" not in json.dumps(run, default=str)
    assert cache.rows == {}


def test_unreachable_search_finalizes_network_error():
    def handler(request):
        raise httpx.ConnectError("secret resolver detail", request=request)

    cache = MemoryCache()
    with pytest.raises(MusicBrainzError, match="Could not reach"):
        ArtistResolver(mb_client(handler), cache).resolve_name("Test Artist")
    assert [(r["status"], r["error_code"]) for r in cache.finished()] == [
        ("failed", "network_error")
    ]


def test_unexpected_exception_finalizes_generic_code_and_propagates():
    def handler(request):
        raise ValueError("secret bug detail")

    cache = MemoryCache()
    with pytest.raises(ValueError):
        ArtistResolver(mb_client(handler), cache).resolve_name("Test Artist")
    assert [(r["status"], r["error_code"]) for r in cache.finished()] == [
        ("failed", "unexpected_error")
    ]


def test_cache_hits_and_denials_open_no_run():
    cache = MemoryCache()
    cache.seed(ArtistCandidate(mbid=MBID, name="Test Artist"))
    resolver = ArtistResolver(mb_client(no_network), cache)
    assert resolver.resolve_name("Test Artist").collection_run_id is None
    assert resolver.resolve_mbid(MBID).collection_run_id is None

    denied = MemoryCache(uses=set())
    with pytest.raises(SourceNotPermitted):
        ArtistResolver(mb_client(no_network), denied).resolve_name("Test Artist")
    assert cache.runs == {} and denied.runs == {}


@pytest.mark.parametrize(
    "error",
    [MusicBrainzError("Supabase RPC begin_musicbrainz_run returned 500."), RuntimeError("down")],
)
def test_run_that_cannot_be_opened_means_no_request_and_no_cache_write(error):
    cache = MemoryCache()
    cache.begin_error = error
    resolver = ArtistResolver(mb_client(no_network), cache)
    with pytest.raises(MusicBrainzError) as exc:
        resolver.resolve_mbid(MBID)
    if not isinstance(error, MusicBrainzError):
        assert exc.value.code == "run_not_opened"
    with pytest.raises(MusicBrainzError):
        resolver.resolve_name("Test Artist")
    assert cache.events == [] and cache.rows == {}


def test_result_whose_run_cannot_be_finalized_is_discarded_and_not_cached():
    cache = MemoryCache()
    cache.finish_error = MusicBrainzError("Supabase RPC finish_musicbrainz_run returned 500.")
    resolver = ArtistResolver(mb_client(lambda r: httpx.Response(200, json=artist_json())), cache)
    with pytest.raises(MusicBrainzError) as exc:
        resolver.resolve_mbid(MBID)
    assert exc.value.code == "run_not_finalized"
    assert cache.rows == {}
    assert [kind for kind, _ in cache.events] == ["begin"]


def test_finalize_failure_does_not_mask_the_call_failure(caplog):
    cache = MemoryCache()
    cache.finish_error = RuntimeError("supabase down")
    resolver = ArtistResolver(mb_client(lambda r: httpx.Response(502)), cache)
    with caplog.at_level(logging.WARNING, logger="app.musicbrainz"), pytest.raises(
        MusicBrainzError
    ) as exc:
        resolver.resolve_mbid(MBID)
    assert exc.value.code == "upstream_unavailable"
    assert "was not finalized (RuntimeError)" in caplog.text


def test_store_needs_a_finalized_succeeded_run():
    cache = MemoryCache()
    run = cache.begin_run(run_key("lookup", MBID))
    artist = ArtistCandidate(mbid=MBID, name="Test Artist")
    with pytest.raises(MusicBrainzError):
        cache.store(artist, confidence=1.0, method="m", collection_run_id=run.collection_run_id)
    with pytest.raises(MusicBrainzError):
        cache.store(artist, confidence=1.0, method="m", collection_run_id=uuid4())
    assert cache.rows == {}


def test_retries_are_attempts_inside_one_run():
    clock = FakeClock()
    cache = MemoryCache()
    responses = iter([httpx.Response(503, headers={"Retry-After": "2"}),
                      httpx.Response(503),
                      httpx.Response(200, json=artist_json())])
    handler = tracked(cache, lambda r: next(responses))
    result = ArtistResolver(mb_client(handler, clock), cache).resolve_mbid(MBID)

    assert result.status == "resolved"
    assert [kind for kind, _ in cache.events] == [
        "begin", "request", "request", "request", "finish", "store"]
    [(run_id, run)] = cache.runs.items()
    assert result.collection_run_id == run_id
    assert (run["status"], run["item_count"]) == ("succeeded", 1)


def test_exhausted_retries_finalize_one_failed_run():
    cache = MemoryCache()
    handler = tracked(cache, lambda r: httpx.Response(503))
    with pytest.raises(MusicBrainzError, match="after retries"):
        ArtistResolver(mb_client(handler), cache).resolve_mbid(MBID)
    kinds = [kind for kind, _ in cache.events]
    assert kinds == ["begin"] + ["request"] * 4 + ["finish"]
    assert [(r["status"], r["error_code"]) for r in cache.runs.values()] == [
        ("failed", "upstream_unavailable")
    ]


def test_long_retry_after_fails_the_run_instead_of_holding_it_open():
    clock = FakeClock()
    cache = MemoryCache()
    wait = str(int(MAX_RETRY_AFTER_SECONDS) + 1)
    handler = tracked(cache, lambda r: httpx.Response(429, headers={"Retry-After": wait}))
    with pytest.raises(MusicBrainzError) as exc:
        ArtistResolver(mb_client(handler, clock), cache).resolve_mbid(MBID)
    assert exc.value.code == "upstream_unavailable"
    assert [kind for kind, _ in cache.events] == ["begin", "request", "finish"]
    assert all(s < MAX_RETRY_AFTER_SECONDS for s in clock.sleeps)


def test_run_keys_hash_the_normalized_name_and_are_unique_per_call():
    first, second = run_key("search", "  Test   ARTIST "), run_key("search", "test artist")
    assert first != second
    assert first.rsplit(":", 1)[0] == second.rsplit(":", 1)[0]
    assert all(RUN_KEY.match(k) for k in (first, second, run_key("lookup", MBID)))


def test_supabase_begin_run_returns_the_captured_permission():
    seen = []
    run_id = uuid4()

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=[{
            "collection_run_id": str(run_id), "permission_id": str(PERMISSION_ID),
            "started_at": "2026-10-18T12:00:00+00:00",
        }])

    key = run_key("lookup", MBID)
    run = supabase(handler).begin_run(key)
    assert run == OpenRun(collection_run_id=run_id, permission_id=PERMISSION_ID,
                          started_at=datetime(2026, 10, 18, 12, 0, tzinfo=UTC))
    assert seen[0].url.path == "/rest/v1/rpc/begin_musicbrainz_run"
    assert json.loads(seen[0].content) == {
        "run_logical_key": key, "run_adapter_version": ADAPTER_VERSION,
    }


@pytest.mark.parametrize(
    "body",
    [[], [{"collection_run_id": str(uuid4()), "permission_id": None,
           "started_at": "2026-10-18T12:00:00+00:00"}], {"unexpected": True}],
)
def test_supabase_begin_run_rejects_a_run_without_its_permission(body):
    with pytest.raises(MusicBrainzError) as exc:
        supabase(lambda r: httpx.Response(200, json=body)).begin_run(run_key("lookup", MBID))
    assert exc.value.code == "run_not_opened"


def test_supabase_begin_run_denial_is_a_collect_denial():
    with pytest.raises(SourceNotPermitted) as exc:
        supabase(lambda r: httpx.Response(403, json={"code": "42501"})).begin_run(
            run_key("lookup", MBID)
        )
    assert exc.value.use == "collect"


def test_supabase_finish_run_calls_rpc_with_fixed_fields():
    seen = []
    run_id = uuid4()
    supabase(lambda r: seen.append(r) or httpx.Response(204)).finish_run(
        run_id, "failed", 0, "network_error"
    )
    assert seen[0].url.path == "/rest/v1/rpc/finish_musicbrainz_run"
    assert json.loads(seen[0].content) == {
        "run_id": str(run_id), "run_status": "failed", "run_item_count": 0,
        "run_error_code": "network_error",
    }


# --- Field/use boundary (docs/metabrainz-readiness.md) --------------------------------
# A future core-data (CC0) permission covers only MBID, name and disambiguation.
# Supplementary data (tags and genre associations, ratings, annotations, search indexes)
# is CC BY-NC-SA and must never be requested or kept under that permission.

# Fields the resolver never asks for or keeps: supplementary data (tags, genre
# associations, ratings, annotations) and core fields it does not need yet (aliases,
# sort name), which would need the matrix and permission scope updated first.
NOT_REQUESTED = {"tags": [{"name": "indie", "count": 3}], "genres": [{"name": "indie rock"}],
                 "rating": {"value": 4.5, "votes-count": 2}, "annotation": "user text",
                 "aliases": [{"name": "TA"}], "sort-name": "Artist, Test"}


@pytest.mark.parametrize("call", ["search", "lookup"])
def test_only_core_identity_fields_are_requested_or_kept(call):
    seen = []

    def handler(request):
        seen.append(request)
        body = {**artist_json(), **NOT_REQUESTED}
        return httpx.Response(200, json={"artists": [body]} if call == "search" else body)

    client = mb_client(handler)
    result = client.search_artists("Test Artist")[0] if call == "search" else client.get_artist(MBID)
    # No include parameter: tags, genres, ratings and aliases are never asked for.
    assert "inc" not in seen[0].url.params
    # Only identity fields survive parsing; the search score is a transient match signal.
    assert set(result.model_dump(exclude_none=True)) <= {"mbid", "name", "score"}
    assert set(ArtistCandidate.model_fields) == {"mbid", "name", "disambiguation", "score"}


def test_the_cache_write_carries_no_score_or_supplementary_field():
    sent = []

    def handler(request):
        sent.append((request.url.path, json.loads(request.content or b"null")))
        if request.url.path.endswith("/musicbrainz_artist_by_mbid"):
            return httpx.Response(200, json=[{
                "artist_id": str(uuid4()), "mbid": str(MBID), "canonical_name": "Test Artist",
                "disambiguation": None, "mapping_confidence": 1.0,
                "mapping_method": "musicbrainz-lookup"}])
        return httpx.Response(200, json=None)

    cache = SupabaseArtistCache("https://project.supabase.invalid", "service-key",
                                http=httpx.Client(transport=httpx.MockTransport(handler)))
    cache.store(ArtistCandidate(mbid=MBID, name="Test Artist", score=100), confidence=1.0,
                method="musicbrainz-lookup", collection_run_id=uuid4())
    (payload,) = [body for path, body in sent if path.endswith("/cache_musicbrainz_artist")]
    assert set(payload) == {"requested_mbid", "artist_name", "artist_disambiguation",
                            "confidence", "method", "run_id"}
