"""Linear webhook authenticity checks for a future SS-RESEARCH-0.2 receiver.

Unmounted: no HTTP route imports this module, and services/api/linear_webhook.py stays
disabled. These are only the signed raw-body and replay checks that
docs/contracts/research-v0.2.md requires of a future receiver. Delivery dedupe, scope
checks and durable enqueue before acknowledgement remain unimplemented, so passing these
checks authorizes no execution, spending or publication.

Ported from the pre-SS-ADR-007 research agent (services/research_agent/webhook.py).
Scheme checked against https://linear.app/developers/webhooks on 2026-10-18: the
Linear-Signature header is the bare hex HMAC-SHA256 of the raw request body, keyed with
the webhook signing secret, and the signed body's webhookTimestamp (Unix milliseconds)
should be within one minute of receipt.

Standard library only, so the offline contract tests can run without API dependencies.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import time
from typing import Any

SIGNATURE_HEADER = "Linear-Signature"
TIMESTAMP_FIELD = "webhookTimestamp"
REPLAY_WINDOW_MS = 60_000


class WebhookRejected(Exception):
    """A delivery failed an authenticity check. The reason never contains the secret or body."""

    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status = status
        self.reason = reason


def verify_signature(raw_body: bytes, signature: str | None, secret: str) -> None:
    """Check Linear-Signature against the exact raw body. Fails closed without a secret."""
    if not secret:
        raise WebhookRejected(401, "webhook signing secret is not configured")
    if not signature:
        raise WebhookRejected(401, f"missing {SIGNATURE_HEADER}")
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    # Compare bytes so a non-ASCII header is a rejection rather than a TypeError.
    if not hmac.compare_digest(expected.encode("ascii"), signature.strip().lower().encode()):
        raise WebhookRejected(401, f"bad {SIGNATURE_HEADER}")


def verify_timestamp(payload: dict[str, Any], window_ms: int = REPLAY_WINDOW_MS,
                     now_ms: int | None = None) -> None:
    """Reject deliveries whose signed webhookTimestamp is missing or outside the window."""
    ts = payload.get(TIMESTAMP_FIELD)
    if isinstance(ts, bool) or not isinstance(ts, (int, float)) or not math.isfinite(ts):
        raise WebhookRejected(401, f"missing or invalid {TIMESTAMP_FIELD}")
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    if abs(now_ms - ts) > window_ms:
        raise WebhookRejected(401, f"stale {TIMESTAMP_FIELD}")


def authenticate_delivery(raw_body: bytes, signature: str | None, secret: str,
                          now_ms: int | None = None) -> dict[str, Any]:
    """Verify the signature before parsing, then the replay window; return the payload."""
    verify_signature(raw_body, signature, secret)
    try:
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WebhookRejected(400, "signed body is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise WebhookRejected(400, "signed body is not a JSON object")
    verify_timestamp(payload, now_ms=now_ms)
    return payload
