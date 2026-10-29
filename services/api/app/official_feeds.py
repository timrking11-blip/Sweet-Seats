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
One elapsed-time budget covers the whole fetch: every DNS lookup, connection, TLS
handshake, response header and body read, across all redirects. Invalid feed
configuration is refused with a fixed code before any request.

Recurring events are not expanded. A UID group carrying a recurrence rule, recurrence
dates, exclusions or an overridden instance is skipped whole with one fixed reason,
never mapped as its first occurrence; so is a UID that appears more than once.

Identity is never decided by name. A venue feed's venue and an artist feed's artist
come from the feed configuration. Other names in the calendar (support acts, the
LOCATION of an artist's show) become feed-scoped vendor keys such as
"name:glass-harbor"; only a reviewed crosswalk maps a key to a canonical UUID, and an
unmapped key goes to the review queue.
"""
from __future__ import annotations

import functools
import http.client
import ipaddress
import os
import re
import socket
import ssl
import threading
import time
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo, available_timezones

from .discovery import DiscoveryError, permitted, provider_url

ADAPTER_VERSION = "official-ics-0.1"
ENABLE_FLAG = "SWEET_SEATS_OFFICIAL_FEEDS_ENABLED"
MAX_BODY_BYTES = 2_000_000
MAX_REDIRECTS = 3
# A system resolver or injected transport may ignore cancellation. Such work keeps
# its slot until it exits, preventing repeated deadlines from accumulating threads.
_OPERATION_SLOTS = threading.BoundedSemaphore(4)
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
FEED_TIMEZONE = "America/New_York"
STATUS = {"CONFIRMED": "scheduled", "CANCELLED": "cancelled", "TENTATIVE": "unknown"}
# Properties that make a VEVENT part of a recurring series (RFC 5545 3.8.4.4, 3.8.5).
RECURRENCE = frozenset({"RRULE", "RDATE", "EXDATE", "EXRULE", "RECURRENCE-ID"})
# The configured identity each feed kind must carry.
IDENTITY_FIELDS = {"venue": "vendor_venue_id", "artist": "vendor_artist_id"}
# Whitespace, control characters, non-ASCII and backslashes: never in a URL we request.
UNSAFE_URL = re.compile(r"[^\x21-\x7e]|\\")
# A validator we are willing to send back as a request header: short printable ASCII.
HEADER_VALUE = re.compile(r"[\x20-\x7e]{1,256}")
# Separators for co-billed acts in a venue calendar SUMMARY, in priority order.
BILLING_SEPARATORS = re.compile(r"\s+(?:\+|w/|with|&)\s+", re.IGNORECASE)

# (status, headers, body) for one GET of url, connecting only to the given, already
# checked IP address, with request headers. The last argument is the seconds left in the
# fetch's total budget; the call must finish within it. Never follows redirects.
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


@functools.cache
def _zones() -> frozenset[str]:
    return frozenset(available_timezones())


def _zone(key: object, code: str) -> ZoneInfo:
    """An IANA zone by its exact key; anything else (Windows names, paths) raises code."""
    if not isinstance(key, str) or key not in _zones():
        raise FeedError(code)
    return ZoneInfo(key)


def check_feed(feed: object) -> None:
    """Raise a fixed code unless the feed configuration is complete and valid.

    fetch_feed checks it before any request, and map_feed before mapping.
    """
    if not isinstance(feed, Mapping):
        raise FeedError("invalid_feed_config")
    if feed.get("kind") not in IDENTITY_FIELDS:
        raise FeedError("unsupported_feed_kind")
    identity = feed.get(IDENTITY_FIELDS[feed["kind"]])
    if not isinstance(identity, str) or not 0 < len(identity.strip()) <= 200:
        raise FeedError("missing_feed_identity")
    _zone(feed.get("timezone", FEED_TIMEZONE), "invalid_timezone")
    url = feed.get("url")
    if not isinstance(url, str) or UNSAFE_URL.search(url):
        raise FeedError("invalid_provider_url")
    provider_url(url)


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
    tz = _zone(feed_tz, "invalid_timezone")
    try:
        if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
            if not re.fullmatch(r"\d{8}", value):
                raise ValueError(value)
            return None, date(int(value[:4]), int(value[4:6]), int(value[6:8])).isoformat()
        parsed = datetime.strptime(value.removesuffix("Z"), "%Y%m%dT%H%M%S")
    except ValueError:
        raise FeedError("invalid_start") from None
    if value.endswith("Z"):
        moment = parsed.replace(tzinfo=UTC)
    elif "TZID" in params:
        moment = parsed.replace(tzinfo=_zone(params["TZID"].strip('"'), "unsupported_timezone"))
    else:
        # Floating time with no zone: the calendar's local wall time is unknown.
        raise FeedError("floating_start_time")
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
    if RECURRENCE & set(event):
        raise FeedError("unsupported_recurrence")
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
    """Map a whole calendar; one malformed event is skipped, not the whole feed.

    Events are grouped by UID first. A group with a recurrence property in any member
    (the series master or an overridden instance) is skipped whole as
    unsupported_recurrence; a UID repeated without one is skipped as duplicate_uid. No
    series becomes a misleading first occurrence, and no vendor event ID repeats.
    """
    check_feed(feed)
    records, display, skipped = [], {}, []
    groups: dict[str, list[dict]] = {}
    for event in parse_ics(text):
        groups.setdefault(event.get("UID", ({}, ""))[1].strip(), []).append(event)
    for uid, group in groups.items():
        if uid and any(RECURRENCE & set(event) for event in group):
            skipped.append({"vendor_event_id": uid, "error_code": "unsupported_recurrence"})
            continue
        if uid and len(group) > 1:
            skipped.append({"vendor_event_id": uid, "error_code": "duplicate_uid"})
            continue
        for event in group:  # One event, or every event without a UID (each is skipped).
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
    every IPv6 form that embeds an IPv4 address (IPv4-compatible ::/96, IPv4-mapped,
    6to4, Teredo, NAT64).
    """
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and (
            address.scope_id or address.packed[:12] == bytes(12) or address.ipv4_mapped
            or address.sixtofour or address.teredo
            or any(address in prefix for prefix in NAT64) or address.is_site_local):
        return False
    return (address.is_global and not address.is_multicast and not address.is_private
            and not address.is_loopback and not address.is_link_local
            and not address.is_reserved and not address.is_unspecified)


def approved_host(source: Mapping) -> str:
    """The one host requests may reach: that of the registry entry's official_url."""
    official = source.get("official_url")
    try:
        if not isinstance(official, str) or UNSAFE_URL.search(official):
            raise DiscoveryError("invalid_provider_url")
        return urlsplit(provider_url(official)).hostname
    except (DiscoveryError, ValueError):
        raise FeedError("host_not_approved") from None


def _check_url(url: str, host: str) -> None:
    """https, printable ASCII, no userinfo, exactly the approved host, the default port."""
    try:
        if not isinstance(url, str) or UNSAFE_URL.search(url):
            raise DiscoveryError("invalid_provider_url")
        parts = urlsplit(provider_url(url))
        port = parts.port
    except (DiscoveryError, ValueError):
        raise FeedError("invalid_provider_url") from None
    if "@" in parts.netloc:
        raise FeedError("invalid_provider_url")
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


def _bounded(call: Callable[[], object], remaining: float):
    """call() within remaining seconds of elapsed time, or deadline_exceeded.

    The call runs on a daemon thread, so even a step that ignores timeouts (the system
    resolver has none) cannot hold the fetch past its budget.
    """
    if remaining <= 0:
        raise FeedError("deadline_exceeded")
    if not _OPERATION_SLOTS.acquire(blocking=False):
        raise FeedError("operation_capacity_exceeded")
    box: dict = {}

    def target():
        try:
            box["value"] = call()
        except BaseException as exc:  # noqa: BLE001 - handed back to the caller below.
            box["error"] = exc
        finally:
            _OPERATION_SLOTS.release()

    worker = threading.Thread(target=target, daemon=True, name="sweet-seats-feed-operation")
    try:
        worker.start()
    except BaseException:
        _OPERATION_SLOTS.release()
        raise
    worker.join(remaining)
    if worker.is_alive():
        raise FeedError("deadline_exceeded")
    if "error" in box:
        raise box["error"]
    return box["value"]


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connects to one checked address; TLS still verifies the certificate for host.

    Every socket operation is bounded by what is left of the budget, and abort() (the
    deadline watchdog) shuts the socket down to interrupt a read in progress.
    """

    def __init__(self, host: str, address: str, timeout: float, port: int = 443):
        self._tls = ssl.create_default_context()
        super().__init__(host, port, timeout=timeout, context=self._tls)
        self._address = address
        self._deadline = time.monotonic() + timeout
        self._raw: socket.socket | None = None
        self.aborted = threading.Event()
        # http.client can clear self.sock when the response owns a closing connection.
        # Keep the active socket independently, including during the TLS handshake.
        self._io_socket: socket.socket | None = None
        self._socket_lock = threading.Lock()

    def remaining(self) -> float:
        left = self._deadline - time.monotonic()
        if left <= 0 or self.aborted.is_set():
            raise FeedError("deadline_exceeded")
        return left

    def expired(self) -> bool:
        return self.aborted.is_set() or time.monotonic() >= self._deadline

    def connect(self):
        raw = socket.create_connection((self._address, self.port), self.remaining())
        with self._socket_lock:
            if self.aborted.is_set():
                raw.close()
                raise FeedError("deadline_exceeded")
            self._raw = raw
            raw.settimeout(self.remaining())
            # Register the SSLSocket before starting a potentially blocking handshake.
            # wrap_socket detaches raw, so abort must use the new socket from now on.
            self._io_socket = self._tls.wrap_socket(
                raw, server_hostname=self.host, do_handshake_on_connect=False)
            self.sock = self._io_socket
        self.sock.do_handshake()

    def retain_socket(self):
        # Also supports the plain loopback connection used in transport tests.
        with self._socket_lock:
            if self._io_socket is None:
                self._io_socket = self.sock
        self.remaining()

    def abort(self):
        self.aborted.set()
        with self._socket_lock:
            active = self._io_socket or self._raw
            if active is not None:
                try:
                    active.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def set_read_timeout(self):
        active = self._io_socket
        if active is None:
            raise FeedError("network_error")
        active.settimeout(self.remaining())

    def close(self):
        super().close()
        # A response with Connection: close still owns its file object; closing the
        # retained socket here is safe, and the response is closed by the transport.
        if self._io_socket is not None:
            self._io_socket.close()
        if self._raw is not None:
            self._raw.close()


def _read_body(conn: _PinnedHTTPSConnection, response) -> bytes:
    """Read until the end of the body or just past the size cap, under the budget."""
    chunks, size = [], 0
    while size <= MAX_BODY_BYTES:
        conn.set_read_timeout()
        chunk = response.read1(65536)  # Returns as soon as any bytes arrive.
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if response.isclosed():
            break
    return b"".join(chunks)


def _pinned_transport(url: str, address: str, headers: Mapping[str, str], timeout: float,
                      *, connection: Callable[..., _PinnedHTTPSConnection] | None = None):
    parts = urlsplit(url)
    target = (parts.path or "/") + ("?" + parts.query if parts.query else "")
    conn = (connection or _PinnedHTTPSConnection)(parts.hostname, address, timeout)
    watchdog = threading.Timer(timeout, conn.abort)
    watchdog.daemon = True
    watchdog.start()
    response = None
    try:
        conn.connect()
        conn.retain_socket()
        conn.set_read_timeout()
        conn.request("GET", target, headers={"User-Agent": "sweet-seats-monitor/0.1",
                                             "Accept": "text/calendar", **headers})
        response = conn.getresponse()
        body = _read_body(conn, response) if response.status == 200 else b""
        conn.remaining()  # An aborted read can look like a clean end of body.
        return response.status, dict(response.getheaders()), body
    except FeedError:
        raise
    except (OSError, http.client.HTTPException, ValueError):
        raise FeedError("deadline_exceeded" if conn.expired() else "network_error") from None
    finally:
        watchdog.cancel()
        watchdog.join()
        if response is not None:
            response.close()
        conn.close()


def _validator_headers(validators: Mapping | None) -> dict[str, str]:
    """Conditional-GET headers from the previous fetch; malformed values are not sent."""
    headers = {}
    for header, key in (("If-None-Match", "etag"), ("If-Modified-Since", "last_modified")):
        value = (validators or {}).get(key)
        if isinstance(value, str) and HEADER_VALUE.fullmatch(value):
            headers[header] = value
    return headers


def fetch_feed(source: dict, feed: Mapping, now: datetime, *, validators: Mapping | None = None,
               transport: Transport | None = None, resolver: Resolver | None = None,
               env: Mapping[str, str] | None = None, timeout: float = 10.0) -> dict:
    """Permission, the enable flag and a valid configuration, all before any request.

    The feed URL must be on the source's approved host. Every request, the first and
    each redirect, is re-checked: same host, port 443, public addresses only. timeout is
    the total elapsed-time budget for the whole fetch, redirects included.

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
    try:
        check_feed(feed)
        host = approved_host(source)
        _check_url(feed["url"], host)
    except DiscoveryError as exc:
        return {**result, "status": "skipped", "error_code": str(exc)}
    url = feed["url"]
    headers = _validator_headers(validators)
    deadline = time.monotonic() + timeout

    def remaining() -> float:
        return deadline - time.monotonic()

    calls = 0
    try:
        for hop in range(MAX_REDIRECTS + 1):
            if hop:
                _check_url(url, host)
            address = _bounded(
                functools.partial(_public_address_for, host, resolver or _resolve), remaining())
            calls += 1
            status, raw_headers, body = _bounded(
                functools.partial(transport or _pinned_transport, url, address, headers,
                                  remaining()), remaining())
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
    # Keep only validators we would send back next time.
    seen = {"etag": lower.get("etag"), "last_modified": lower.get("last-modified")}
    kept = {k: v for k, v in seen.items() if v and HEADER_VALUE.fullmatch(v)}
    base = {**result, "network_calls": calls, "validators": kept or result["validators"]}
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
