"""Ticketmaster Discovery API v2 adapter (planned source, disabled by default).

Fixture-first: the map_* functions turn Discovery v2 responses into the source event
record accepted by discovery.normalize, plus display-only metadata kept beside it.
Live HTTP stays off unless SWEET_SEATS_TICKETMASTER_ENABLED=true and
TICKETMASTER_API_KEY are both set, and collect_events checks the source permission
before any request. Raw payloads are never retained here, and priceRanges are
display metadata only: never price history.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from pathlib import Path

from .discovery import ROOT, DiscoveryError, permitted, timestamp

BASE_URL = "https://app.ticketmaster.com/discovery/v2/"
ADAPTER_VERSION = "ticketmaster-discovery-v2-0.1"
ENABLE_FLAG = "SWEET_SEATS_TICKETMASTER_ENABLED"
KEY_VARIABLE = "TICKETMASTER_API_KEY"
DAILY_LIMIT = 5000
PER_SECOND = 5
MAX_BODY_BYTES = 4_000_000
DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "ticketmaster" / "events.json"
PRICE_POLICY = "display_only_not_price_history"
STATUS = {"onsale": "scheduled", "offsale": "scheduled", "rescheduled": "scheduled",
          "postponed": "postponed", "cancelled": "cancelled", "canceled": "cancelled"}
SEARCH_PARAMS = {"id", "keyword", "attractionId", "venueId", "postalCode", "latlong", "geoPoint",
                 "radius", "unit", "city", "stateCode", "countryCode", "dmaId", "marketId",
                 "classificationName", "classificationId", "segmentId", "genreId",
                 "startDateTime", "endDateTime", "onsaleStartDateTime", "includeTBA",
                 "includeTBD", "includeTest", "size", "page", "sort", "locale", "source"}
ENDPOINT = re.compile(r"(events|venues|attractions)(/[A-Za-z0-9_-]{1,64})?\.json")
APIKEY_PARAM = re.compile(r"(apikey=)[^&\s'\"]+", re.IGNORECASE)

# (status, headers, body) for a GET of the given URL with the given timeout.
Transport = Callable[[str, float], tuple[int, Mapping[str, str], bytes]]
log = logging.getLogger(__name__)


class TicketmasterError(DiscoveryError):
    """Fixed codes only: never a URL, query string, payload or key."""


def redact(text: str, *secrets: str) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return APIKEY_PARAM.sub(r"\1[REDACTED]", text)


def enabled(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return (env.get(ENABLE_FLAG, "").strip().lower() == "true"
            and bool(env.get(KEY_VARIABLE, "").strip()))


def _zulu(value: datetime) -> str:
    if value.tzinfo is None:
        raise TicketmasterError("invalid_zoned_timestamp")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _text(value: object, code: str) -> str:
    if not isinstance(value, str) or not 0 < len(value.strip()) <= 300:
        raise TicketmasterError(code)
    return value.strip()


def _optional(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and 0 < len(value.strip()) <= 300 else None


def _https_url(value: object, code: str) -> str:
    parsed = urllib.parse.urlsplit(value) if isinstance(value, str) and len(value) <= 2048 else None
    if (parsed is None or parsed.scheme != "https" or not parsed.hostname
            or parsed.username or parsed.password):
        raise TicketmasterError(code)
    return value


def _segment_genre(entity: Mapping) -> tuple[str | None, str | None]:
    for item in entity.get("classifications") or []:
        if isinstance(item, Mapping) and item.get("primary") is True:
            return (_optional((item.get("segment") or {}).get("name")),
                    _optional((item.get("genre") or {}).get("name")))
    return None, None


def map_venue(venue: Mapping) -> dict:
    """An identity candidate: reviewed venue mappings, never names, decide identity."""
    if not isinstance(venue, Mapping) or venue.get("type", "venue") != "venue":
        raise TicketmasterError("invalid_venue")
    if venue.get("test") is True:
        raise TicketmasterError("test_venue")
    location = venue.get("location") or {}
    url = venue.get("url")
    return {"vendor_venue_id": _text(venue.get("id"), "invalid_venue_id"),
            "name": _text(venue.get("name"), "invalid_venue_name"),
            "timezone": _optional(venue.get("timezone")),
            "address_line1": _optional((venue.get("address") or {}).get("line1")),
            "city": _optional((venue.get("city") or {}).get("name")),
            "state_code": _optional((venue.get("state") or {}).get("stateCode")),
            "postal_code": _optional(venue.get("postalCode")),
            "country_code": _optional((venue.get("country") or {}).get("countryCode")),
            "latitude": _optional(location.get("latitude")),
            "longitude": _optional(location.get("longitude")),
            "source_url": _https_url(url, "invalid_venue_url") if url else None,
            "review_status": "unreviewed"}


def map_attraction(attraction: Mapping) -> dict:
    """An identity candidate; images and external links are deliberately dropped."""
    if not isinstance(attraction, Mapping) or attraction.get("type", "attraction") != "attraction":
        raise TicketmasterError("invalid_attraction")
    if attraction.get("test") is True:
        raise TicketmasterError("test_attraction")
    segment, genre = _segment_genre(attraction)
    url = attraction.get("url")
    return {"vendor_artist_id": _text(attraction.get("id"), "invalid_attraction_id"),
            "name": _text(attraction.get("name"), "invalid_attraction_name"),
            "segment": segment, "genre": genre,
            "source_url": _https_url(url, "invalid_attraction_url") if url else None,
            "review_status": "unreviewed"}


def _schedule(dates: Mapping) -> tuple[str | None, str, dict]:
    start = dates.get("start") if isinstance(dates.get("start"), Mapping) else {}
    try:
        local_date = date.fromisoformat(start.get("localDate")).isoformat()
    except (TypeError, ValueError):
        raise TicketmasterError("missing_local_date") from None
    flags = {"date_tba": start.get("dateTBA") is True or start.get("dateTBD") is True,
             "time_tba": start.get("timeTBA") is True,
             "no_specific_time": start.get("noSpecificTime") is True}
    starts_at = None
    # Only Ticketmaster's own UTC instant is used; a local time is never re-zoned here.
    if not any(flags.values()) and start.get("dateTime"):
        starts_at = _zulu(timestamp(start["dateTime"]))
    flags["local_time"] = _optional(start.get("localTime")) if starts_at else None
    return starts_at, local_date, flags


def _price_ranges(value: object) -> list[dict]:
    ranges = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, Mapping):
            continue
        low, high, currency = item.get("min"), item.get("max"), item.get("currency")
        if (isinstance(low, int | float) and isinstance(high, int | float)
                and not isinstance(low, bool) and not isinstance(high, bool)
                and 0 <= low <= high and isinstance(currency, str)
                and re.fullmatch(r"[A-Z]{3}", currency)):
            ranges.append({"type": _optional(item.get("type")), "currency": currency,
                           "min": float(low), "max": float(high)})
    return ranges


def _public_onsale(sales: object) -> str | None:
    """Public on-sale start as a UTC instant; TBD or malformed values are unknown, not guessed."""
    public = sales.get("public") if isinstance(sales, Mapping) else None
    if not isinstance(public, Mapping) or public.get("startTBD") is True:
        return None
    try:
        return _zulu(timestamp(public["startDateTime"]))
    except (KeyError, DiscoveryError):
        return None


def map_event(event: Mapping, observed_at: datetime) -> dict:
    """Return {"record": source event record, "display": display-only metadata}.

    Attraction order is taken as billing order: the first credit is the headliner and
    the rest support. Reviewed artist and venue mappings resolve identity downstream.
    """
    if not isinstance(event, Mapping) or event.get("type", "event") != "event":
        raise TicketmasterError("invalid_event")
    if event.get("test") is True:
        raise TicketmasterError("test_event")
    vendor_event_id = _text(event.get("id"), "invalid_event_id")
    embedded = event.get("_embedded") if isinstance(event.get("_embedded"), Mapping) else {}
    venues = embedded.get("venues")
    if not isinstance(venues, list) or not venues:
        raise TicketmasterError("missing_venue")
    venue = map_venue(venues[0])
    attractions = embedded.get("attractions")
    if not isinstance(attractions, list) or not attractions:
        raise TicketmasterError("missing_attraction_credits")
    credits, performers = [], []
    for attraction in attractions:
        credit = map_attraction(attraction)
        if credit["vendor_artist_id"] in {p["vendor_artist_id"] for p in performers}:
            continue
        performers.append({"vendor_artist_id": credit["vendor_artist_id"],
                           "role": "headliner" if not performers else "support",
                           "billing_order": len(performers)})
        credits.append({"vendor_artist_id": credit["vendor_artist_id"], "name": credit["name"]})
    dates = event.get("dates") if isinstance(event.get("dates"), Mapping) else {}
    starts_at, local_date, schedule = _schedule(dates)
    timezone = _optional(dates.get("timezone")) or venue["timezone"]
    if timezone is None:
        raise TicketmasterError("missing_timezone")
    status = dates.get("status") if isinstance(dates.get("status"), Mapping) else {}
    code = _optional(status.get("code"))
    url = _https_url(event.get("url"), "invalid_event_url")
    observed = _zulu(observed_at)
    record = {"vendor_event_id": vendor_event_id,
              "title": _text(event.get("name"), "invalid_event_name"),
              "venue_vendor_id": venue["vendor_venue_id"], "performers": performers,
              "starts_at": starts_at, "local_date": local_date, "timezone": timezone,
              "status": STATUS.get((code or "").lower(), "unknown"),
              "observed_at": observed, "available_at": observed,
              "source_url": url, "ticket_url": url}
    onsale_at = _public_onsale(event.get("sales"))
    if onsale_at:
        record["onsale_at"] = onsale_at
    display = {"status_code": code, **schedule, "start_time_known": starts_at is not None,
               "venue": venue, "attractions": credits,
               "price_ranges": _price_ranges(event.get("priceRanges")),
               "price_policy": PRICE_POLICY}
    return {"record": record, "display": display}


def _embedded(payload: Mapping, kind: str) -> list:
    if not isinstance(payload, Mapping):
        raise TicketmasterError("invalid_response")
    embedded = payload.get("_embedded")
    if embedded is None:  # Discovery omits _embedded when a search has no results.
        return []
    items = embedded.get(kind) if isinstance(embedded, Mapping) else None
    if not isinstance(items, list):
        raise TicketmasterError("invalid_response")
    return items


def _page(payload: Mapping) -> dict | None:
    page = payload.get("page")
    if not isinstance(page, Mapping):
        return None
    keys = ("size", "totalElements", "totalPages", "number")
    return {key: page[key] for key in keys if type(page.get(key)) is int and page[key] >= 0}


def _map_all(items: list, mapper: Callable[[Mapping], dict], id_key: str) -> tuple[list, list]:
    mapped, skipped = [], []
    for item in items:
        try:
            mapped.append(mapper(item))
        except DiscoveryError as exc:
            vendor_id = item.get("id") if isinstance(item, Mapping) else None
            skipped.append({id_key: vendor_id if isinstance(vendor_id, str) else None,
                            "error_code": str(exc)})
    return mapped, skipped


def map_event_search(payload: Mapping, observed_at: datetime) -> dict:
    """Map an events.json page; one malformed event is skipped, not the whole page."""
    mapped, skipped = _map_all(_embedded(payload, "events"),
                               lambda item: map_event(item, observed_at), "vendor_event_id")
    return {"records": [m["record"] for m in mapped],
            "display": {m["record"]["vendor_event_id"]: m["display"] for m in mapped},
            "skipped": skipped, "page": _page(payload)}


def map_venue_search(payload: Mapping) -> dict:
    venues, skipped = _map_all(_embedded(payload, "venues"), map_venue, "vendor_venue_id")
    return {"venues": venues, "skipped": skipped, "page": _page(payload)}


def map_attraction_search(payload: Mapping) -> dict:
    attractions, skipped = _map_all(_embedded(payload, "attractions"), map_attraction,
                                    "vendor_artist_id")
    return {"attractions": attractions, "skipped": skipped, "page": _page(payload)}


def _urllib_transport(url: str, timeout: float) -> tuple[int, Mapping[str, str], bytes]:
    request = urllib.request.Request(url, headers={"Accept": "application/json",
                                                   "User-Agent": "sweet-seats-discovery/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), response.read(MAX_BODY_BYTES + 1)
    except urllib.error.HTTPError as exc:
        headers = dict(exc.headers.items()) if exc.headers else {}
        exc.close()
        return exc.code, headers, b""
    except (urllib.error.URLError, TimeoutError, OSError):
        raise TicketmasterError("network_error") from None


class TicketmasterClient:
    """Rate-limited Discovery v2 client: 5 req/s, 5000/day, Rate-Limit-* aware.

    Construct through from_env so the enable flag is honoured. The key is only ever
    placed in the request query string and is redacted everywhere else.
    """

    def __init__(self, api_key: str, *, transport: Transport | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 sleep: Callable[[float], None] = time.sleep, daily_limit: int = DAILY_LIMIT,
                 per_second: int = PER_SECOND, max_retries: int = 3, timeout: float = 10.0,
                 max_backoff: float = 30.0):
        if not isinstance(api_key, str) or not api_key.strip():
            raise TicketmasterError("missing_api_key")
        self._key = api_key.strip()
        self._transport = transport or _urllib_transport
        self._clock, self._wall_clock, self._sleep = clock, wall_clock, sleep
        self._daily_limit, self._per_second = daily_limit, per_second
        self._max_retries, self._timeout, self._max_backoff = max_retries, timeout, max_backoff
        self._recent: deque[float] = deque()
        self._day: date | None = None
        self._day_count = 0
        self._blocked_until: datetime | None = None
        self.request_count = 0

    def __repr__(self) -> str:
        return f"TicketmasterClient(api_key=[REDACTED], requests={self.request_count})"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None, **kwargs) -> TicketmasterClient | None:
        env = os.environ if env is None else env
        return cls(env[KEY_VARIABLE], **kwargs) if enabled(env) else None

    def _reserve(self) -> None:
        now = self._wall_clock()
        if self._blocked_until and now < self._blocked_until:
            raise TicketmasterError("quota_exhausted")
        if self._day != now.date():
            self._day, self._day_count = now.date(), 0
        if self._day_count >= self._daily_limit:
            raise TicketmasterError("daily_quota_exhausted")
        tick = self._clock()
        while self._recent and tick - self._recent[0] >= 1.0:
            self._recent.popleft()
        if len(self._recent) >= self._per_second:
            self._sleep(1.0 - (tick - self._recent[0]))
            tick = self._clock()
            self._recent.popleft()
        self._recent.append(tick)
        self._day_count += 1
        self.request_count += 1

    def _observe_limits(self, headers: Mapping[str, str]) -> None:
        try:
            available = int(headers["rate-limit-available"])
            reset = datetime.fromtimestamp(int(headers["rate-limit-reset"]) / 1000, UTC)
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            return
        if available <= 0:
            self._blocked_until = reset

    def _backoff(self, attempt: int, headers: Mapping[str, str]) -> float:
        try:
            delay = float(headers["retry-after"])
        except (KeyError, TypeError, ValueError):
            delay = 2.0 ** attempt
        return min(max(delay, 0.0), self._max_backoff)

    def get(self, path: str, params: Mapping[str, object] | None = None) -> dict:
        if not ENDPOINT.fullmatch(path):
            raise TicketmasterError("unsupported_endpoint")
        query = {key: str(value).lower() if isinstance(value, bool) else str(value)
                 for key, value in (params or {}).items() if value is not None}
        if not set(query) <= SEARCH_PARAMS:
            raise TicketmasterError("unsupported_parameter")
        url = BASE_URL + path + "?" + urllib.parse.urlencode({**query, "apikey": self._key})
        for attempt in range(self._max_retries + 1):
            self._reserve()
            log.debug("ticketmaster GET %s", redact(url, self._key))
            try:
                status, raw_headers, body = self._transport(url, self._timeout)
            except TicketmasterError:
                raise
            except Exception:  # noqa: BLE001 - any transport error may embed the keyed URL.
                raise TicketmasterError("transport_error") from None
            headers = {str(k).lower(): str(v) for k, v in raw_headers.items()}
            self._observe_limits(headers)
            if status == 200:
                if len(body) > MAX_BODY_BYTES:
                    raise TicketmasterError("response_too_large")
                try:
                    payload = json.loads(body)
                except (TypeError, ValueError):
                    raise TicketmasterError("invalid_json") from None
                if not isinstance(payload, dict):
                    raise TicketmasterError("invalid_response")
                return payload
            if status == 429 and self._blocked_until and self._wall_clock() < self._blocked_until:
                raise TicketmasterError("quota_exhausted")
            if status == 429 or 500 <= status < 600:
                if attempt == self._max_retries:
                    raise TicketmasterError("rate_limited" if status == 429 else "provider_unavailable")
                self._sleep(self._backoff(attempt, headers))
                continue
            raise TicketmasterError({401: "unauthorized", 403: "forbidden",
                                     404: "not_found"}.get(status, "http_error"))
        raise TicketmasterError("provider_unavailable")

    def search_events(self, **params: object) -> dict:
        return self.get("events.json", params)

    def get_event(self, event_id: str) -> dict:
        return self.get(f"events/{event_id}.json")

    def search_venues(self, **params: object) -> dict:
        return self.get("venues.json", params)

    def get_venue(self, venue_id: str) -> dict:
        return self.get(f"venues/{venue_id}.json")

    def search_attractions(self, **params: object) -> dict:
        return self.get("attractions.json", params)

    def get_attraction(self, attraction_id: str) -> dict:
        return self.get(f"attractions/{attraction_id}.json")


def collect_events(source: dict, now: datetime, params: Mapping[str, object] | None = None, *,
                   client: TicketmasterClient | None = None,
                   env: Mapping[str, str] | None = None) -> dict:
    """Permission, then the enable flag; both pass before any request is made.

    The result holds mapped records only: the raw payload is discarded, and storage
    still has to pass discovery.ingest's retention gates.
    """
    result = {"source_id": source.get("source_id"), "adapter_version": ADAPTER_VERSION,
              "finished_at": _zulu(now), "records": [], "display": {}, "skipped": [],
              "page": None, "network_calls": 0}
    if not permitted(source, "collect", now):
        return {**result, "status": "skipped", "error_code": "permission_denied"}
    if not enabled(env):
        return {**result, "status": "skipped", "error_code": "provider_disabled"}
    client = client or TicketmasterClient.from_env(env)
    before = client.request_count
    try:
        mapped = map_event_search(client.search_events(**(params or {})), now)
    except DiscoveryError as exc:
        return {**result, "status": "failed", "error_code": str(exc),
                "network_calls": client.request_count - before}
    return {**result, **mapped, "status": "succeeded" if mapped["records"] else "empty",
            "error_code": None, "network_calls": client.request_count - before}


def main() -> None:
    parser = argparse.ArgumentParser(description="Map a synthetic Discovery v2 fixture offline.")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    args = parser.parse_args()
    try:
        payload = json.loads(args.fixture.read_text(encoding="utf-8"))
        mapped = map_event_search(payload, datetime.now(UTC))
        print(json.dumps({"synthetic": True, "records": len(mapped["records"]),
                          "skipped": [s["error_code"] for s in mapped["skipped"]],
                          "network_calls": 0}))
    except (DiscoveryError, OSError, ValueError):
        parser.exit(1, "Fixture mapping failed; no provider call was made.\n")


if __name__ == "__main__":
    main()
