"""Official artist and venue calendar adapter (iCalendar / ICS; disabled by default).

Roadmap Phase 3 "curated official monitors": an artist's or venue's own published
calendar, the source expected to announce shows first. Fixture-first like the
Ticketmaster adapter: map_feed turns an ICS document into source event records that
discovery.ingest_collection accepts. Live HTTP stays off unless
SWEET_SEATS_OFFICIAL_FEEDS_ENABLED=true, and fetch_feed checks the source permission
before any request. Raw payloads are never retained.

Requests go only to the host of the source's owner-approved official_url, over https
on port 443, and only to an address that resolves as public. The connection is pinned
to the address that was checked, so DNS cannot swap in another one. Redirects are
followed by hand: at most MAX_REDIRECTS, each to the same approved host, each re-checked.

Identity is never decided by name. A venue feed's venue and an artist feed's artist
come from the feed configuration. Other names in the calendar (support acts, the
LOCATION of an artist's show) become feed-scoped vendor keys such as
"name:glass-harbor"; only a reviewed crosswalk maps a key to a canonical UUID, and an
unmapped key goes to the review queue.
"""
from __future__ import annotations

import http.client
import ipaddress
import os
import re
import socket
import ssl
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .discovery import DiscoveryError, permitted, provider_url

ADAPTER_VERSION = "official-ics-0.1"
ENABLE_FLAG = "SWEET_SEATS_OFFICIAL_FEEDS_ENABLED"
MAX_BODY_BYTES = 2_000_000
MAX_REDIRECTS = 3
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
FEED_TIMEZONE = "America/New_York"
STATUS = {"CONFIRMED": "scheduled", "CANCELLED": "cancelled", "TENTATIVE": "unknown"}
# Separators for co-billed acts in a venue calendar SUMMARY, in priority order.
BILLING_SEPARATORS = re.compile(r"\s+(?:\+|w/|with|&)\s+", re.IGNORECASE)

# (status, headers, body) for one GET of url, connecting only to the given, already
# checked IP address, with request headers and a timeout. Never follows redirects.
Transport = Callable[[str, str, Mapping[str, str], float], tuple[int, Mapping[str, str], bytes]]
# The IP addresses a host name resolves to, for (host, port).
Resolver = Callable[[str, int], list[str]]
# IPv6 prefixes that carry an IPv4 address (NAT64; RFC 6052 and RFC 8215).
NAT64 = (ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("64:ff9b:1::/48"))


class FeedError(DiscoveryError):
    """Fixed codes only: never a URL, header or payload."""


def enabled(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return env.get(ENABLE_FLAG, "").strip().lower() == "true"


def vendor_key(prefix: str, name: str) -> str:
    """Feed-scoped vendor key from display text. A key, never an identity match."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        raise FeedError("empty_vendor_key")
    return f"{prefix}:{slug[:120]}"


def _unescape(value: str) -> str:
    return (value.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",")
            .replace("\\;", ";").replace("\\\\", "\\"))


def parse_ics(text: str) -> list[dict]:
    """Minimal RFC 5545 reader: unfolds lines and returns VEVENT properties.

    Each property maps to (params, value). Nested components (VALARM) are ignored.
    """
    if not isinstance(text, str) or "BEGIN:VCALENDAR" not in text:
        raise FeedError("invalid_calendar")
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in {" ", "\t"} and lines:
            lines[-1] += raw[1:]
        elif raw:
            lines.append(raw)
    events, current, depth = [], None, 0
    for line in lines:
        if line == "BEGIN:VEVENT":
            current, depth = {}, 0
            continue
        if current is None:
            continue
        if line.startswith("BEGIN:"):
            depth += 1
            continue
        if line.startswith("END:") and depth:
            depth -= 1
            continue
        if line == "END:VEVENT":
            events.append(current)
            current = None
            continue
        if depth or ":" not in line:
            continue
        head, value = line.split(":", 1)
        name, *param_parts = head.split(";")
        params = dict(part.split("=", 1) for part in param_parts if "=" in part)
        current.setdefault(name.upper(), (params, value))
    return events


def _start(prop: tuple[dict, str], feed_tz: str) -> tuple[str | None, str]:
    """(starts_at UTC or None, local_date) from a DTSTART property."""
    params, value = prop
    tz = ZoneInfo(feed_tz)
    try:
        if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
            return None, date(int(value[:4]), int(value[4:6]), int(value[6:8])).isoformat()
        parsed = datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S")
        if value.endswith("Z"):
            moment = parsed.replace(tzinfo=UTC)
        elif "TZID" in params:
            moment = parsed.replace(tzinfo=ZoneInfo(params["TZID"].strip('"')))
        else:
            # Floating time with no zone: the calendar's local wall time is unknown.
            raise FeedError("floating_start_time")
    except (ValueError, KeyError, ZoneInfoNotFoundError):
        raise FeedError("invalid_start") from None
    return (moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            moment.astimezone(tz).date().isoformat())


def _text(event: dict, name: str, code: str) -> str:
    value = _unescape(event.get(name, ({}, ""))[1]).strip()
    if not 0 < len(value) <= 300:
        raise FeedError(code)
    return value


def map_event(event: dict, feed: Mapping, observed_at: datetime) -> dict:
    """Map one VEVENT to {"record": source event record, "display": metadata}."""
    if "DTSTART" not in event:
        raise FeedError("missing_start")
    vendor_event_id = _text(event, "UID", "missing_uid")
    title = _text(event, "SUMMARY", "missing_summary")
    starts_at, local_date = _start(event["DTSTART"], feed.get("timezone", FEED_TIMEZONE))
    if feed["kind"] == "venue":
        venue_vendor_id = feed["vendor_venue_id"]
        names = [n.strip() for n in BILLING_SEPARATORS.split(title) if n.strip()]
        artist_keys = [vendor_key("name", n) for n in names]
    elif feed["kind"] == "artist":
        location = _unescape(event.get("LOCATION", ({}, ""))[1]).split(",")[0].strip()
        if not location:
            raise FeedError("missing_location")
        venue_vendor_id = vendor_key("location", location)
        artist_keys = [feed["vendor_artist_id"]]
    else:
        raise FeedError("unsupported_feed_kind")
    performers, seen = [], set()
    for key in artist_keys:
        if key in seen:
            continue
        seen.add(key)
        performers.append({"vendor_artist_id": key,
                           "role": "headliner" if not performers else "support",
                           "billing_order": len(performers)})
    url = event.get("URL", ({}, ""))[1].strip() or feed["url"]
    observed = observed_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = {"vendor_event_id": vendor_event_id, "title": title,
              "venue_vendor_id": venue_vendor_id, "performers": performers,
              "starts_at": starts_at, "local_date": local_date,
              "timezone": feed.get("timezone", FEED_TIMEZONE),
              "status": STATUS.get(event.get("STATUS", ({}, "CONFIRMED"))[1].upper(), "unknown"),
              "observed_at": observed, "available_at": observed,
              "source_url": provider_url(url), "ticket_url": None}
    # The calendar's own claimed publication time is display metadata; lead time uses
    # when Sweet Seats could know (available_at), never the source's claim.
    display = {"claimed_published_at": event.get("CREATED", event.get("DTSTAMP", ({}, None)))[1],
               "last_modified": event.get("LAST-MODIFIED", ({}, None))[1]}
    return {"record": record, "display": display}


def map_feed(text: str, feed: Mapping, observed_at: datetime) -> dict:
    """Map a whole calendar; one malformed event is skipped, not the whole feed."""
    records, display, skipped = [], {}, []
    for event in parse_ics(text):
        try:
            mapped = map_event(event, feed, observed_at)
        except DiscoveryError as exc:
            uid = event.get("UID", ({}, None))[1]
            skipped.append({"vendor_event_id": uid, "error_code": str(exc)})
            continue
        records.append(mapped["record"])
        display[mapped["record"]["vendor_event_id"]] = mapped["display"]
    return {"records": records, "display": display, "skipped": skipped}


def public_address(value: str) -> bool:
    """True only for a globally routable unicast IP address.

    Rejects private, loopback, link-local, multicast, reserved, unspecified, shared
    (100.64.0.0/10), documentation and site-local addresses, scoped IPv6 addresses, and
    every IPv6 form that embeds an IPv4 address (IPv4-mapped, 6to4, Teredo, NAT64).
    """
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and (
            address.scope_id or address.ipv4_mapped or address.sixtofour or address.teredo
            or any(address in prefix for prefix in NAT64) or address.is_site_local):
        return False
    return (address.is_global and not address.is_multicast and not address.is_private
            and not address.is_loopback and not address.is_link_local
            and not address.is_reserved and not address.is_unspecified)


def approved_host(source: Mapping) -> str:
    """The one host requests may reach: that of the registry entry's official_url."""
    try:
        return urlsplit(provider_url(source.get("official_url"))).hostname
    except DiscoveryError:
        raise FeedError("host_not_approved") from None


def _check_url(url: str, host: str) -> None:
    """https, no credentials, exactly the approved host, and the default port."""
    try:
        parts = urlsplit(provider_url(url))
        port = parts.port
    except (DiscoveryError, ValueError):
        raise FeedError("invalid_provider_url") from None
    if parts.hostname != host:
        raise FeedError("host_not_approved")
    if port not in (None, 443):
        raise FeedError("port_not_allowed")


def _resolve(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        raise FeedError("dns_error") from None
    return [info[4][0] for info in infos]


def _public_address_for(host: str, resolver: Resolver) -> str:
    """One address to connect to. Every address the host resolves to must be public."""
    addresses = resolver(host, 443)
    if not addresses:
        raise FeedError("dns_error")
    if not all(public_address(a) for a in addresses):
        raise FeedError("non_public_address")
    return addresses[0]


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connects to one checked address; TLS still verifies the certificate for host."""

    def __init__(self, host: str, address: str, timeout: float):
        self._tls = ssl.create_default_context()
        super().__init__(host, 443, timeout=timeout, context=self._tls)
        self._address = address

    def connect(self):
        sock = socket.create_connection((self._address, self.port), self.timeout)
        self.sock = self._tls.wrap_socket(sock, server_hostname=self.host)


def _pinned_transport(url: str, address: str, headers: Mapping[str, str], timeout: float):
    parts = urlsplit(url)
    target = (parts.path or "/") + ("?" + parts.query if parts.query else "")
    conn = _PinnedHTTPSConnection(parts.hostname, address, timeout)
    try:
        conn.request("GET", target, headers={"User-Agent": "sweet-seats-monitor/0.1",
                                             "Accept": "text/calendar", **headers})
        response = conn.getresponse()
        body = response.read(MAX_BODY_BYTES + 1) if response.status == 200 else b""
        return response.status, dict(response.getheaders()), body
    except (OSError, http.client.HTTPException):
        raise FeedError("network_error") from None
    finally:
        conn.close()


def fetch_feed(source: dict, feed: Mapping, now: datetime, *, validators: Mapping | None = None,
               transport: Transport | None = None, resolver: Resolver | None = None,
               env: Mapping[str, str] | None = None, timeout: float = 10.0) -> dict:
    """Permission, then the enable flag; both pass before any request is made.

    The feed URL must be on the source's approved host. Every request, the first and
    each redirect, is re-checked: same host, port 443, public addresses only.

    Sends If-None-Match / If-Modified-Since from the previous fetch, so an unchanged
    calendar costs one small request and returns "not_modified" (not "empty").
    """
    result = {"source_id": source.get("source_id"), "adapter_version": ADAPTER_VERSION,
              "records": [], "display": {}, "skipped": [], "network_calls": 0,
              "validators": dict(validators or {})}
    if not permitted(source, "collect", now):
        return {**result, "status": "skipped", "error_code": "permission_denied"}
    if not enabled(env):
        return {**result, "status": "skipped", "error_code": "provider_disabled"}
    url = provider_url(feed["url"])
    try:
        host = approved_host(source)
        _check_url(url, host)
    except FeedError as exc:
        return {**result, "status": "skipped", "error_code": str(exc)}
    headers = {}
    if validators and validators.get("etag"):
        headers["If-None-Match"] = validators["etag"]
    if validators and validators.get("last_modified"):
        headers["If-Modified-Since"] = validators["last_modified"]
    calls = 0
    try:
        for hop in range(MAX_REDIRECTS + 1):
            if hop:
                _check_url(url, host)
            address = _public_address_for(host, resolver or _resolve)
            calls += 1
            status, raw_headers, body = (transport or _pinned_transport)(
                url, address, headers, timeout)
            lower = {str(k).lower(): str(v) for k, v in raw_headers.items()}
            if status not in REDIRECT_STATUSES:
                break
            if not lower.get("location"):
                raise FeedError("redirect_without_location")
            url = urljoin(url, lower["location"])
        else:
            raise FeedError("too_many_redirects")
    except FeedError as exc:
        return {**result, "status": "failed", "error_code": str(exc), "network_calls": calls}
    seen = {"etag": lower.get("etag"), "last_modified": lower.get("last-modified")}
    base = {**result, "network_calls": calls,
            "validators": {k: v for k, v in seen.items() if v} or result["validators"]}
    if status == 304:
        return {**base, "status": "not_modified", "error_code": None}
    if status != 200:
        return {**base, "status": "failed", "error_code": f"http_{status}"}
    if len(body) > MAX_BODY_BYTES:
        return {**base, "status": "failed", "error_code": "response_too_large"}
    try:
        mapped = map_feed(body.decode("utf-8"), feed, now)
    except (DiscoveryError, UnicodeDecodeError):
        return {**base, "status": "failed", "error_code": "invalid_calendar"}
    return {**base, **mapped, "status": "succeeded" if mapped["records"] else "empty",
            "error_code": None}
