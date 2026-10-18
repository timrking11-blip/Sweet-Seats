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
    ArtistCandidate,
    ArtistResolver,
    CachedArtist,
    CollectionRun,
    MusicBrainzClient,
    MusicBrainzError,
    SourceNotPermitted,
    SupabaseArtistCache,
    run_key,
    user_agent,
)

MBID = UUID("6c7a9f0b-3c1e-4d5a-9a43-0d0b3e1f7a11")
OTHER_MBID = UUID("0f3e2a1b-7c6d-4e5f-8a9b-1c2d3e4f5a6b")
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
    def __init__(self, uses: set[str] = frozenset({"collect", "derived_retention"})) -> None:
        self.uses = set(uses)
        self.rows: dict[UUID, CachedArtist] = {}
        self.runs: list[CollectionRun] = []
        self.record_error: Exception | None = None

    def permitted(self, use):
        return use in self.uses

    def by_mbid(self, mbid):
        return self.rows.get(mbid)

    def by_name(self, name):
        return [r for r in self.rows.values() if r.name.casefold() == name.strip().casefold()]

    def store(self, artist: ArtistCandidate, *, confidence, method):
        row = self.rows.get(artist.mbid) or CachedArtist(
            artist_id=uuid4(), mbid=artist.mbid, name=artist.name,
            disambiguation=artist.disambiguation, mapping_confidence=confidence,
            mapping_method=method,
        )
        self.rows[artist.mbid] = row
        return row

    def record_run(self, run: CollectionRun):
        if self.record_error:
            raise self.record_error
        self.runs.append(run)


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
    cache.store(ArtistCandidate(mbid=MBID, name="Test Artist"), confidence=0.9, method="m")
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


def test_supabase_store_writes_then_reads_back():
    artist_id = uuid4()
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
        method="musicbrainz-search-exact",
    )
    assert stored.artist_id == artist_id and stored.mapping_confidence == 0.9
    assert calls[0] == ("cache_musicbrainz_artist", {
        "requested_mbid": str(MBID), "artist_name": "Test Artist", "artist_disambiguation": None,
        "confidence": 0.9, "method": "musicbrainz-search-exact",
    })
    assert calls[1][0] == "musicbrainz_artist_by_mbid"


def test_supabase_permission_denied_maps_to_source_not_permitted():
    with pytest.raises(SourceNotPermitted):
        supabase(lambda r: httpx.Response(403, json={"code": "42501"})).store(
            ArtistCandidate(mbid=MBID, name="Test Artist"), confidence=1.0, method="m"
        )


def test_supabase_cache_requires_configuration():
    with pytest.raises(MusicBrainzError, match="SUPABASE_URL"):
        SupabaseArtistCache("", "")


# Collection runs: every network call records exactly one run; cache hits and denials record none.

# Mirrors the logical_key check in 202610180002_musicbrainz_collection_runs.sql.
RUN_KEY = re.compile(
    r"^artist-(search:[0-9a-f]{64}|lookup:[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}):[0-9a-f]{32}$"
)


def name_hash(name):
    return hashlib.sha256(name.casefold().encode()).hexdigest()


def test_search_records_succeeded_run_without_the_name():
    handler = lambda r: httpx.Response(200, json={"artists": [
        artist_json(), artist_json(OTHER_MBID, "Test Artists", score=88)]})
    cache = MemoryCache()
    result = ArtistResolver(mb_client(handler), cache).resolve_name("Test Artist")

    assert result.status == "resolved" and result.run_recorded is True
    [run] = cache.runs
    assert (run.status, run.item_count, run.error_code) == ("succeeded", 2, None)
    assert run.adapter_version == ADAPTER_VERSION
    assert RUN_KEY.match(run.logical_key)
    assert run.logical_key.startswith(f"artist-search:{name_hash('test artist')}:")
    assert "test" not in run.logical_key.casefold().replace(name_hash("test artist"), "")
    assert run.started_at.tzinfo is not None and run.started_at <= datetime.now(UTC)


def test_ambiguous_search_still_records_its_run():
    handler = lambda r: httpx.Response(200, json={"artists": [
        artist_json(MBID, disambiguation="US rapper"),
        artist_json(OTHER_MBID, disambiguation="UK band"),
    ]})
    cache = MemoryCache()
    result = ArtistResolver(mb_client(handler), cache).resolve_name("Test Artist")
    assert result.status == "ambiguous" and result.run_recorded is True
    assert [(r.status, r.item_count) for r in cache.runs] == [("succeeded", 2)]


def test_search_without_hits_records_empty_run():
    cache = MemoryCache()
    handler = lambda r: httpx.Response(200, json={"artists": []})
    result = ArtistResolver(mb_client(handler), cache).resolve_name("Nobody")
    assert result.status == "not_found" and result.run_recorded is True
    assert [(r.status, r.item_count, r.error_code) for r in cache.runs] == [("empty", 0, None)]


def test_lookup_records_runs_keyed_by_mbid():
    cache = MemoryCache()
    found = ArtistResolver(mb_client(lambda r: httpx.Response(200, json=artist_json())), cache)
    missing = ArtistResolver(mb_client(lambda r: httpx.Response(404)), cache)

    assert found.resolve_mbid(MBID).status == "resolved"
    assert missing.resolve_mbid(OTHER_MBID).status == "not_found"

    assert [(r.status, r.item_count) for r in cache.runs] == [("succeeded", 1), ("empty", 0)]
    assert cache.runs[0].logical_key.startswith(f"artist-lookup:{MBID}:")
    assert cache.runs[1].logical_key.startswith(f"artist-lookup:{OTHER_MBID}:")
    assert all(RUN_KEY.match(r.logical_key) for r in cache.runs)


def test_uncached_match_records_run():
    cache = MemoryCache(uses={"collect"})
    result = ArtistResolver(
        mb_client(lambda r: httpx.Response(200, json=artist_json())), cache
    ).resolve_mbid(MBID)
    assert result.status == "uncached" and result.run_recorded is True
    assert [r.status for r in cache.runs] == ["succeeded"]


@pytest.mark.parametrize(
    ("handler", "code"),
    [
        (lambda r: httpx.Response(502, text="secret upstream detail"), "upstream_unavailable"),
        (lambda r: httpx.Response(400, text="secret upstream detail"), "unexpected_status"),
        (lambda r: httpx.Response(200, text="secret not json"), "invalid_json"),
        (lambda r: httpx.Response(200, json={"secret": "shape"}), "unexpected_shape"),
    ],
)
def test_failed_lookup_records_fixed_error_code_and_reraises(handler, code):
    cache = MemoryCache()
    with pytest.raises(MusicBrainzError) as exc:
        ArtistResolver(mb_client(handler), cache).resolve_mbid(MBID)
    assert exc.value.code == code
    [run] = cache.runs
    assert (run.status, run.item_count, run.error_code) == ("failed", 0, code)
    assert "secret" not in run.model_dump_json()
    assert cache.rows == {}


def test_unreachable_search_records_network_error():
    def handler(request):
        raise httpx.ConnectError("secret resolver detail", request=request)

    cache = MemoryCache()
    with pytest.raises(MusicBrainzError, match="Could not reach"):
        ArtistResolver(mb_client(handler), cache).resolve_name("Test Artist")
    assert [(r.status, r.error_code) for r in cache.runs] == [("failed", "network_error")]


def test_unexpected_exception_records_generic_code_and_propagates():
    def handler(request):
        raise ValueError("secret bug detail")

    cache = MemoryCache()
    with pytest.raises(ValueError):
        ArtistResolver(mb_client(handler), cache).resolve_name("Test Artist")
    assert [(r.status, r.error_code) for r in cache.runs] == [("failed", "unexpected_error")]


def test_cache_hits_and_denials_record_no_run():
    cache = MemoryCache()
    cache.store(ArtistCandidate(mbid=MBID, name="Test Artist"), confidence=0.9, method="m")
    resolver = ArtistResolver(mb_client(no_network), cache)
    assert resolver.resolve_name("Test Artist").run_recorded is None
    assert resolver.resolve_mbid(MBID).run_recorded is None

    denied = MemoryCache(uses=set())
    with pytest.raises(SourceNotPermitted):
        ArtistResolver(mb_client(no_network), denied).resolve_name("Test Artist")
    assert cache.runs == [] and denied.runs == []


def test_run_recording_failure_keeps_the_lookup_result(caplog):
    cache = MemoryCache()
    cache.record_error = MusicBrainzError("Supabase RPC record_musicbrainz_run returned 500.")
    resolver = ArtistResolver(mb_client(lambda r: httpx.Response(200, json=artist_json())), cache)

    with caplog.at_level(logging.WARNING, logger="app.musicbrainz"):
        result = resolver.resolve_mbid(MBID)

    assert result.status == "resolved" and result.artist.mbid == MBID
    assert result.run_recorded is False
    assert "was not recorded (musicbrainz_error)" in caplog.text


def test_run_recording_failure_does_not_mask_the_call_failure():
    cache = MemoryCache()
    cache.record_error = RuntimeError("supabase down")
    resolver = ArtistResolver(mb_client(lambda r: httpx.Response(502)), cache)
    with pytest.raises(MusicBrainzError) as exc:
        resolver.resolve_mbid(MBID)
    assert exc.value.code == "upstream_unavailable"


def test_run_keys_hash_the_normalized_name_and_are_unique_per_call():
    first, second = run_key("search", "  Test   ARTIST "), run_key("search", "test artist")
    assert first != second
    assert first.rsplit(":", 1)[0] == second.rsplit(":", 1)[0]
    assert all(RUN_KEY.match(k) for k in (first, second, run_key("lookup", MBID)))


def test_supabase_record_run_calls_rpc_with_fixed_fields():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=str(uuid4()))

    started = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
    key = run_key("lookup", MBID)
    supabase(handler).record_run(CollectionRun(
        logical_key=key, status="failed", item_count=0, error_code="network_error",
        started_at=started,
    ))
    request = seen[0]
    assert request.url.path == "/rest/v1/rpc/record_musicbrainz_run"
    assert json.loads(request.content) == {
        "run_logical_key": key, "run_status": "failed", "run_item_count": 0,
        "run_error_code": "network_error", "run_adapter_version": ADAPTER_VERSION,
        "run_started_at": "2026-10-18T12:00:00+00:00",
    }
