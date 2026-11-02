"""MusicBrainz artist identity client with a Supabase-backed MBID cache.

Policy (docs/governance.md, docs/provider-use.md): MusicBrainz is registered as a planned
source (supabase/migrations/202610180001_musicbrainz_artist_cache.sql). A network call needs
the 'collect' permission and a cache write needs 'derived_retention'; both are checked through
public.source_use_is_permitted and fail closed until the owner approves a SourcePermission.
Only identity fields are kept: MBID, name and disambiguation.

Provenance fails closed (supabase/migrations/202610180002_musicbrainz_collection_runs.sql).
Before any network access the resolver opens a public.collection_runs row, which captures the
exact SourcePermission that authorizes 'collect' at the run start; if the row cannot be opened
there is no request. After the response it finalizes that same row. If finalizing fails the
result is discarded, and a cache write needs the finalized, succeeded run. Rows carry a fixed
error code and a hashed or MBID-based logical key, never a name or payload.

Retries are attempts inside one collection run, not separate records: one logical request is
one run, authorized by the permission captured when it opened. Retries are bounded by
MAX_RETRIES, and a Retry-After longer than MAX_RETRY_AFTER_SECONDS fails the run instead of
holding it open.

The web service needs no API key for reads. It requires a User-Agent that names the app and
a contact, and allows about one request per second per IP. The throttle here is per process;
run a single collector, or share a limiter, before adding workers.

Usage (export the variables in your own terminal):
    MUSICBRAINZ_CONTACT, SUPABASE_URL (or NEXT_PUBLIC_SUPABASE_URL), SUPABASE_SERVICE_ROLE_KEY
    python -m app.musicbrainz "Phoebe Bridgers"
    python -m app.musicbrainz --mbid 2d2a8b2b-...
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import threading
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

import httpx
from pydantic import BaseModel, ValidationError

API_ROOT = "https://musicbrainz.org/ws/2"
APP_NAME = "SweetSeats"
APP_VERSION = "0.1.0"
ADAPTER_VERSION = "musicbrainz-ws2-0.1"
MIN_INTERVAL_SECONDS = 1.0
MAX_RETRIES = 3
MAX_RETRY_AFTER_SECONDS = 30.0
SEARCH_LIMIT = 5
# Confidence recorded on source_entity_mappings. A direct MBID lookup is certain; a unique
# exact-name search hit is strong but can still be a namesake, so it stays below 1.
LOOKUP_CONFIDENCE = 1.0
EXACT_SEARCH_CONFIDENCE = 0.9

Use = Literal["collect", "derived_retention"]
RunStatus = Literal["succeeded", "empty", "failed"]

log = logging.getLogger(__name__)


class MusicBrainzError(RuntimeError):
    """Messages never echo credentials or provider payloads. code is a fixed snake_case value
    that is safe to store as collection_runs.error_code."""

    def __init__(self, message: str, *, code: str = "musicbrainz_error") -> None:
        super().__init__(message)
        self.code = code


class SourceNotPermitted(MusicBrainzError):
    def __init__(self, use: str) -> None:
        super().__init__(
            f"MusicBrainz '{use}' is not permitted by an approved SourcePermission.",
            code="not_permitted",
        )
        self.use = use


class ArtistCandidate(BaseModel):
    mbid: UUID
    name: str
    disambiguation: str | None = None
    score: int | None = None


class CachedArtist(BaseModel):
    artist_id: UUID
    mbid: UUID
    name: str
    disambiguation: str | None = None
    mapping_confidence: float
    mapping_method: str


class Resolution(BaseModel):
    """cached: served from Supabase; resolved: fetched and cached; uncached: matched but
    retention is not permitted; ambiguous: needs review; not_found: no match.
    collection_run_id: the finalized run that fetched this result; None when no network call
    was made."""

    status: Literal["cached", "resolved", "uncached", "ambiguous", "not_found"]
    artist: CachedArtist | None = None
    candidates: list[ArtistCandidate] = []
    collection_run_id: UUID | None = None


class OpenRun(BaseModel):
    """A public.collection_runs row opened before a MusicBrainz call, with the permission
    that authorized it at started_at."""

    collection_run_id: UUID
    permission_id: UUID
    started_at: datetime


def user_agent(contact: str | None) -> str:
    contact = (contact or "").strip()
    if not contact:
        raise MusicBrainzError(
            "MUSICBRAINZ_CONTACT is not set. MusicBrainz requires a contact (an email or URL) "
            "in the User-Agent."
        )
    return f"{APP_NAME}/{APP_VERSION} ( {contact} )"


def _lucene_phrase(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _clean_name(name: str) -> str:
    name = name.strip() if isinstance(name, str) else ""
    if not 0 < len(name) <= 300:
        raise MusicBrainzError("Artist name must be 1-300 characters.", code="invalid_name")
    return name


def run_key(operation: Literal["search", "lookup"], subject: str | UUID) -> str:
    """Unique per call: the operation, a SHA-256 of the normalized name (or the MBID), and a
    nonce, so the run row identifies what was asked without storing the name."""
    if operation == "search":
        normalized = " ".join(str(subject).split()).casefold()
        subject = hashlib.sha256(normalized.encode()).hexdigest()
    return f"artist-{operation}:{subject}:{uuid4().hex}"


def _candidate(item: dict[str, Any]) -> ArtistCandidate:
    return ArtistCandidate(
        mbid=item["id"],
        name=item["name"],
        disambiguation=item.get("disambiguation") or None,
        score=item.get("score"),
    )


class MusicBrainzClient:
    """Read-only MusicBrainz web service client with a per-process 1 request/second throttle."""

    def __init__(
        self,
        user_agent: str,
        *,
        http: httpx.Client | None = None,
        min_interval: float = MIN_INTERVAL_SECONDS,
        max_retries: int = MAX_RETRIES,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = http or httpx.Client(timeout=15.0)
        self._headers = {"User-Agent": user_agent, "Accept": "application/json"}
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def search_artists(self, name: str, *, limit: int = SEARCH_LIMIT) -> list[ArtistCandidate]:
        body = self._get(
            "/artist", {"query": f"artist:{_lucene_phrase(_clean_name(name))}", "limit": limit}
        )
        try:
            return [_candidate(item) for item in (body or {}).get("artists", [])]
        except (KeyError, TypeError, ValidationError) as exc:
            raise MusicBrainzError(
                "Unexpected MusicBrainz search response shape.", code="unexpected_shape"
            ) from exc

    def get_artist(self, mbid: UUID) -> ArtistCandidate | None:
        body = self._get(f"/artist/{mbid}", {})
        if body is None:
            return None
        try:
            return _candidate(body)
        except (KeyError, TypeError, ValidationError) as exc:
            raise MusicBrainzError(
                "Unexpected MusicBrainz artist response shape.", code="unexpected_shape"
            ) from exc

    def _throttle(self) -> None:
        with self._lock:
            wait = self._next_allowed - self._clock()
            if wait > 0:
                self._sleep(wait)
            self._next_allowed = self._clock() + self._min_interval

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Returns None for 404. Retries 429/503 (MusicBrainz rate limiting) and other 5xx."""
        for attempt in range(self._max_retries + 1):
            self._throttle()
            try:
                response = self._http.get(
                    API_ROOT + path, params={**params, "fmt": "json"}, headers=self._headers
                )
            except httpx.HTTPError as exc:
                if attempt == self._max_retries:
                    raise MusicBrainzError(
                        "Could not reach MusicBrainz.", code="network_error"
                    ) from exc
                self._sleep(2**attempt)
                continue
            if response.status_code == 404:
                return None
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == self._max_retries:
                    raise MusicBrainzError(
                        f"MusicBrainz returned {response.status_code} after retries.",
                        code="upstream_unavailable",
                    )
                retry_after = response.headers.get("retry-after", "")
                wait = float(retry_after) if retry_after.isdigit() else 2**attempt
                if wait > MAX_RETRY_AFTER_SECONDS:
                    # Honour the server by not retrying sooner; the run fails instead.
                    raise MusicBrainzError(
                        f"MusicBrainz returned {response.status_code} with a long Retry-After.",
                        code="upstream_unavailable",
                    )
                self._sleep(wait)
                continue
            if response.status_code != 200:
                raise MusicBrainzError(
                    f"MusicBrainz returned {response.status_code}.", code="unexpected_status"
                )
            try:
                return response.json()
            except ValueError as exc:
                raise MusicBrainzError(
                    "MusicBrainz returned invalid JSON.", code="invalid_json"
                ) from exc
        raise AssertionError("unreachable")


class ArtistCache(Protocol):
    def permitted(self, use: Use) -> bool: ...
    def by_mbid(self, mbid: UUID) -> CachedArtist | None: ...
    def by_name(self, name: str) -> list[CachedArtist]: ...
    def store(
        self, artist: ArtistCandidate, *, confidence: float, method: str, collection_run_id: UUID
    ) -> CachedArtist: ...
    def begin_run(self, logical_key: str) -> OpenRun: ...
    def finish_run(
        self, collection_run_id: UUID, status: RunStatus, item_count: int, error_code: str | None
    ) -> None: ...


class SupabaseArtistCache:
    """Calls the migration's functions through PostgREST RPC with a server-only key."""

    def __init__(self, url: str, service_key: str, *, http: httpx.Client | None = None) -> None:
        if not url or not service_key:
            raise MusicBrainzError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for the artist cache."
            )
        self._rpc_root = url.rstrip("/") + "/rest/v1/rpc/"
        self._http = http or httpx.Client(timeout=15.0)
        self._headers = {"apikey": service_key, "Content-Type": "application/json"}
        # Legacy service_role keys are JWTs; new sb_secret_ keys go in the apikey header only.
        if service_key.startswith("eyJ"):
            self._headers["Authorization"] = f"Bearer {service_key}"

    def _rpc(
        self, function: str, payload: dict[str, Any], *, denied_use: Use = "derived_retention"
    ) -> Any:
        try:
            response = self._http.post(
                self._rpc_root + function, json=payload, headers=self._headers
            )
        except httpx.HTTPError as exc:
            raise MusicBrainzError("Could not reach Supabase.") from exc
        if response.status_code == 403:
            raise SourceNotPermitted(denied_use)
        if response.status_code >= 400:
            raise MusicBrainzError(f"Supabase RPC {function} returned {response.status_code}.")
        # Void functions (finish_musicbrainz_run) answer 204 with no body.
        return response.json() if response.content else None

    @staticmethod
    def _row(row: dict[str, Any]) -> CachedArtist:
        return CachedArtist(
            artist_id=row["artist_id"],
            mbid=row["mbid"],
            name=row["canonical_name"],
            disambiguation=row.get("disambiguation"),
            mapping_confidence=float(row["mapping_confidence"]),
            mapping_method=row["mapping_method"],
        )

    def permitted(self, use: Use) -> bool:
        return self._rpc("musicbrainz_use_is_permitted", {"requested_use": use}) is True

    def by_mbid(self, mbid: UUID) -> CachedArtist | None:
        rows = self._rpc("musicbrainz_artist_by_mbid", {"requested_mbid": str(mbid)})
        return self._row(rows[0]) if rows else None

    def by_name(self, name: str) -> list[CachedArtist]:
        rows = self._rpc("musicbrainz_artists_by_name", {"requested_name": name})
        return [self._row(row) for row in rows]

    def store(
        self, artist: ArtistCandidate, *, confidence: float, method: str, collection_run_id: UUID
    ) -> CachedArtist:
        self._rpc(
            "cache_musicbrainz_artist",
            {
                "requested_mbid": str(artist.mbid),
                "artist_name": artist.name,
                "artist_disambiguation": artist.disambiguation,
                "confidence": confidence,
                "method": method,
                "run_id": str(collection_run_id),
            },
        )
        cached = self.by_mbid(artist.mbid)
        if cached is None:
            raise MusicBrainzError("Cached MusicBrainz artist could not be read back.")
        return cached

    def begin_run(self, logical_key: str) -> OpenRun:
        rows = self._rpc(
            "begin_musicbrainz_run",
            {"run_logical_key": logical_key, "run_adapter_version": ADAPTER_VERSION},
            denied_use="collect",
        )
        try:
            [row] = rows
            return OpenRun.model_validate(row)
        except (TypeError, ValueError) as exc:  # ValidationError is a ValueError.
            raise MusicBrainzError(
                "Supabase did not return the opened collection run.", code="run_not_opened"
            ) from exc

    def finish_run(
        self, collection_run_id: UUID, status: RunStatus, item_count: int, error_code: str | None
    ) -> None:
        self._rpc(
            "finish_musicbrainz_run",
            {
                "run_id": str(collection_run_id),
                "run_status": status,
                "run_item_count": item_count,
                "run_error_code": error_code,
            },
        )


class ArtistResolver:
    """Resolves artist names or MBIDs to Sweet Seats artist UUIDs, cache first."""

    def __init__(self, client: MusicBrainzClient, cache: ArtistCache) -> None:
        self._client = client
        self._cache = cache

    def _collect(
        self, operation: Literal["search", "lookup"], subject: str | UUID, call: Callable[[], Any]
    ) -> tuple[Any, UUID]:
        """Opens the collection run, makes one logical network call (with its retries) and
        finalizes that same run. Fails closed at both ends: no open run means no request, and
        a result whose run cannot be finalized is discarded."""
        try:
            run = self._cache.begin_run(run_key(operation, subject))
        except MusicBrainzError:
            raise
        except Exception as exc:
            raise MusicBrainzError(
                "MusicBrainz collection run could not be opened.", code="run_not_opened"
            ) from exc
        try:
            result = call()
        except Exception as exc:
            code = exc.code if isinstance(exc, MusicBrainzError) else "unexpected_error"
            try:
                self._cache.finish_run(run.collection_run_id, "failed", 0, code)
            except Exception as finish_exc:  # noqa: BLE001 - never mask the call failure.
                # The row stays failed/'incomplete', which is still a failure.
                log.warning(
                    "MusicBrainz collection run %s was not finalized (%s).",
                    run.collection_run_id, getattr(finish_exc, "code", type(finish_exc).__name__),
                )
            raise
        count = len(result) if isinstance(result, list) else int(result is not None)
        try:
            self._cache.finish_run(
                run.collection_run_id, "succeeded" if count else "empty", count, None
            )
        except Exception as exc:
            raise MusicBrainzError(
                "MusicBrainz collection run could not be finalized; the result was discarded.",
                code="run_not_finalized",
            ) from exc
        return result, run.collection_run_id

    def _keep(
        self, artist: ArtistCandidate, *, confidence: float, method: str, run_id: UUID
    ) -> Resolution:
        if not self._cache.permitted("derived_retention"):
            return Resolution(status="uncached", candidates=[artist], collection_run_id=run_id)
        stored = self._cache.store(
            artist, confidence=confidence, method=method, collection_run_id=run_id
        )
        return Resolution(status="resolved", artist=stored, collection_run_id=run_id)

    def resolve_mbid(self, mbid: UUID) -> Resolution:
        cached = self._cache.by_mbid(mbid)
        if cached:
            return Resolution(status="cached", artist=cached)
        artist, run_id = self._collect("lookup", mbid, lambda: self._client.get_artist(mbid))
        if artist is None:
            return Resolution(status="not_found", collection_run_id=run_id)
        return self._keep(
            artist, confidence=LOOKUP_CONFIDENCE, method="musicbrainz-lookup", run_id=run_id
        )

    def resolve_name(self, name: str) -> Resolution:
        name = _clean_name(name)
        cached = self._cache.by_name(name)
        if len(cached) == 1:
            return Resolution(status="cached", artist=cached[0])
        if len(cached) > 1:
            return Resolution(
                status="ambiguous",
                candidates=[
                    ArtistCandidate(mbid=c.mbid, name=c.name, disambiguation=c.disambiguation)
                    for c in cached
                ],
            )

        candidates, run_id = self._collect(
            "search", name, lambda: self._client.search_artists(name)
        )
        if not candidates:
            return Resolution(status="not_found", collection_run_id=run_id)
        exact = [
            c for c in candidates if c.score == 100 and c.name.casefold() == name.casefold()
        ]
        if len(exact) != 1:
            # Namesakes or fuzzy hits need a person (or an MBID) to choose.
            return Resolution(
                status="ambiguous", candidates=exact or candidates, collection_run_id=run_id
            )
        return self._keep(
            exact[0], confidence=EXACT_SEARCH_CONFIDENCE, method="musicbrainz-search-exact",
            run_id=run_id,
        )


def from_env() -> ArtistResolver:
    client = MusicBrainzClient(user_agent(os.environ.get("MUSICBRAINZ_CONTACT")))
    cache = SupabaseArtistCache(
        os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL", ""),
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
    )
    return ArtistResolver(client, cache)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("name", nargs="?")
    target.add_argument("--mbid", type=UUID)
    args = parser.parse_args(argv)

    try:
        resolver = from_env()
        result = resolver.resolve_mbid(args.mbid) if args.mbid else resolver.resolve_name(args.name)
    except MusicBrainzError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
