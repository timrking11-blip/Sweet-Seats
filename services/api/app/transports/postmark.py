"""Postmark email transport for alert deliveries (Build Plan S2; proposed).

Postmark does not de-duplicate sends by a key, so this transport is not idempotent. It
does reconcile: every message carries the delivery's stable key as Postmark metadata
(dedupe_key), and reconcile searches outbound messages by it before any retry (G-07).
Postmark's search can lag a send by seconds; the worker reconciles on a later tick, not
immediately after a send.

The server token is read from the environment by the caller and never logged or put in
an error. Errors are fixed codes. Endpoint references are secret-store pointers, never
addresses: the caller supplies the resolver (the store is an open owner decision).
Open tracking is off: an open is recorded only with outcome consent, which a transport
cannot see, so tracking waits for a per-recipient decision.
"""
from __future__ import annotations

import os
from collections.abc import Callable

import httpx

from ..alerts import DeliveryUncertain, Transport, TransportError

API = "https://api.postmarkapp.com"
TOKEN_ENV = "SWEET_SEATS_POSTMARK_SERVER_TOKEN"
FROM_ENV = "SWEET_SEATS_POSTMARK_FROM"
STREAM_ENV = "SWEET_SEATS_POSTMARK_STREAM"
METADATA_KEY = "dedupe_key"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)

# Postmark ErrorCode values that mean this recipient cannot be sent to.
RECIPIENT_REJECTED = {300, 406}

Resolver = Callable[[str], str]
NOTICE = ("You get this because you follow this artist on Sweet Seats. "
          "Manage or stop alerts in your account settings.")


def footer(message: dict) -> str:
    """Where this came from, built from the projection at send time; nothing stored."""
    lines = ["Where this came from:"]
    for source in message.get("provenance") or []:
        lines.append(f"- {source['name']}: {source['url']} (seen {source['observed_at']})")
    if len(lines) == 1:
        lines.append("- Source details are unavailable for this event.")
    lines.append(f"First seen by Sweet Seats {message.get('first_seen_at') or 'unknown'}; "
                 f"last confirmed {message.get('last_confirmed_at') or 'unknown'}.")
    return "\n".join(lines)


def text_body(message: dict) -> str:
    when = message.get("starts_at") or f"{message['local_date']} (time to be announced)"
    return "\n".join([
        f"{message['headline']}: {message['title']}",
        f"{message['venue']}, {when}",
        "",
        footer(message),
        "",
        NOTICE,
    ])


class PostmarkTransport(Transport):
    idempotent = False
    reconciles = True

    def __init__(self, token: str, sender: str, resolve: Resolver, *,
                 stream: str = "outbound", client: httpx.Client | None = None):
        if not token or not sender:
            raise ValueError("postmark_not_configured")
        self._headers = {"Accept": "application/json", "X-Postmark-Server-Token": token}
        self.sender, self.stream, self.resolve = sender, stream, resolve
        self.client = client or httpx.Client(base_url=API, timeout=TIMEOUT)

    @classmethod
    def from_env(cls, resolve: Resolver, client: httpx.Client | None = None) -> PostmarkTransport:
        return cls(os.environ.get(TOKEN_ENV, ""), os.environ.get(FROM_ENV, ""), resolve,
                   stream=os.environ.get(STREAM_ENV, "outbound"), client=client)

    def _address(self, endpoint_ref: str) -> str:
        try:
            address = self.resolve(endpoint_ref)
        except Exception:  # noqa: BLE001 - nothing was sent; the store may recover.
            raise TransportError("endpoint_unresolved") from None
        if not isinstance(address, str) or "@" not in address:
            raise TransportError("endpoint_unresolved")
        return address

    def send(self, channel: str, endpoint_ref: str, message: dict, idempotency_key: str) -> str:
        if channel != "email":
            raise TransportError("unsupported_channel", permanent=True)
        body = {
            "From": self.sender,
            "To": self._address(endpoint_ref),
            "Subject": f"{message['headline']}: {message['title']}"[:200],
            "TextBody": text_body(message),
            "MessageStream": self.stream,
            "Tag": message.get("template_version", "alerts"),
            "Metadata": {METADATA_KEY: idempotency_key},
            "TrackOpens": False,
            "TrackLinks": "None",
        }
        try:
            response = self.client.post("/email", json=body, headers=self._headers)
        except (httpx.ConnectError, httpx.ConnectTimeout):
            raise TransportError("provider_unreachable") from None  # Never reached Postmark.
        except httpx.HTTPError:
            raise DeliveryUncertain("outcome_unknown") from None
        return self._message_id(response)

    @staticmethod
    def _message_id(response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            data = {}
        code = data.get("ErrorCode") if isinstance(data, dict) else None
        if response.status_code == 200 and code == 0:
            message_id = data.get("MessageID")
            if isinstance(message_id, str) and message_id:
                return message_id
            raise DeliveryUncertain("missing_message_id")
        if response.status_code == 401 or code == 10:
            raise TransportError("provider_auth")
        if response.status_code == 422 and code in RECIPIENT_REJECTED:
            raise TransportError("recipient_rejected", permanent=True)
        if response.status_code == 422:
            raise TransportError("provider_rejected")
        if response.status_code == 429:
            raise TransportError("rate_limited")
        if response.status_code >= 500:
            # Postmark may have accepted it before failing; ask before re-sending.
            raise DeliveryUncertain("provider_unavailable")
        raise DeliveryUncertain("unexpected_response")

    def reconcile(self, channel: str, endpoint_ref: str, idempotency_key: str) -> str | bool | None:
        try:
            response = self.client.get(
                "/messages/outbound", headers=self._headers,
                params={"count": 2, "offset": 0, f"metadata_{METADATA_KEY}": idempotency_key})
            data = response.json() if response.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            return None
        if not isinstance(data, dict) or not isinstance(data.get("Messages"), list):
            return None
        found = [m.get("MessageID") for m in data["Messages"]
                 if isinstance(m, dict) and (m.get("Metadata") or {}).get(METADATA_KEY) == idempotency_key]
        found = [m for m in found if isinstance(m, str) and m]
        if found:
            return found[0]
        return False if data.get("TotalCount") == 0 else None
