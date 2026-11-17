"""Postmark delivery webhooks (Build Plan S2; proposed).

Postmark calls this with basic-auth credentials set on the webhook URL. A hard bounce,
spam complaint or unsubscribe revokes the subscription the message went to, and the
consent history records why (consent_events.source: bounce, complaint or user). An open
becomes an outcome_events row only while the user has outcome consent, at most once per
alert. Messages are matched only by the dedupe_key metadata this service set on send,
never by recipient address. Unknown records are acknowledged and ignored so Postmark
does not retry them; nothing from the payload is logged or echoed.
"""
from __future__ import annotations

import base64
import hmac
import os
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException

from .discovery import DiscoveryError
from .discovery_postgres import PostgresStore, configured_dsn
from .transports.postmark import METADATA_KEY

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])

USER_ENV = "SWEET_SEATS_POSTMARK_WEBHOOK_USER"
PASSWORD_ENV = "SWEET_SEATS_POSTMARK_WEBHOOK_PASSWORD"
# Bounce types after which sending to the address cannot succeed.
PERMANENT_BOUNCES = {"HardBounce", "BadEmailAddress", "ManuallyDeactivated", "SpamNotification"}
ACK = {"status": "ok"}


def webhook_store() -> PostgresStore:
    dsn = configured_dsn()
    try:
        if not dsn:
            raise DiscoveryError("store_unavailable")
        return PostgresStore(dsn)
    except DiscoveryError:
        raise HTTPException(status_code=503, detail="Webhook store unavailable.") from None


def require_postmark(authorization: Annotated[str | None, Header()] = None) -> None:
    user, password = os.environ.get(USER_ENV, ""), os.environ.get(PASSWORD_ENV, "")
    if len(user) < 8 or len(password) < 24:
        raise HTTPException(status_code=503, detail="Webhook not configured.")
    expected = base64.b64encode(f"{user}:{password}".encode()).decode()
    scheme, _, given = (authorization or "").partition(" ")
    if scheme.lower() != "basic" or not hmac.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Unauthorized.",
                            headers={"WWW-Authenticate": 'Basic realm="postmark"'})


def _delivery(conn, payload: dict) -> dict | None:
    key = (payload.get("Metadata") or {}).get(METADATA_KEY) if isinstance(
        payload.get("Metadata"), dict) else None
    try:
        key = str(UUID(key)) if isinstance(key, str) else None
    except ValueError:
        key = None
    if key is None:
        return None
    return conn.execute(
        """SELECT d.alert_id, d.subscription_id, a.user_id, a.event_id
           FROM alert_deliveries d JOIN alerts a USING (alert_id)
           WHERE d.delivery_key = %s""", (key,)).fetchone()


def _revoke(conn, delivery: dict, source: str) -> None:
    conn.execute("SELECT set_config('sweet_seats.consent_source', %s, true)", (source,))
    conn.execute(
        """UPDATE notification_subscriptions SET revoked_at = now()
           WHERE subscription_id = %s AND revoked_at IS NULL""", (delivery["subscription_id"],))
    conn.execute("SELECT set_config('sweet_seats.consent_source', '', true)")


def _occurred(value: object, now: datetime) -> datetime:
    try:
        at = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        at = None
    if at is None or at.tzinfo is None or at > now + timedelta(minutes=5):
        return now
    return at.astimezone(UTC)


def _record_open(conn, delivery: dict, at: datetime) -> None:
    conn.execute(
        """INSERT INTO outcome_events (user_id, alert_id, event_id, kind, occurred_at)
           SELECT %(user)s, %(alert)s, %(event)s, 'alert_opened', %(at)s
           FROM user_profiles p
           WHERE p.user_id = %(user)s AND p.outcome_consent_at IS NOT NULL
             AND p.deletion_requested_at IS NULL
             AND NOT EXISTS (SELECT 1 FROM outcome_events o
                             WHERE o.alert_id = %(alert)s AND o.user_id = %(user)s
                               AND o.kind = 'alert_opened')""",
        {"user": delivery["user_id"], "alert": delivery["alert_id"],
         "event": delivery["event_id"], "at": at})


def webhook_now() -> datetime:
    return datetime.now(UTC)


@router.post("/postmark", dependencies=[Depends(require_postmark)])
def postmark(payload: dict, store: Annotated[PostgresStore, Depends(webhook_store)],
             now: datetime = Depends(webhook_now)) -> dict:
    record = payload.get("RecordType")
    with store._connect() as conn, conn.transaction():
        delivery = _delivery(conn, payload)
        if delivery is None:
            return ACK
        if record == "Bounce" and payload.get("Type") in PERMANENT_BOUNCES:
            _revoke(conn, delivery, "bounce")
        elif record == "SpamComplaint":
            _revoke(conn, delivery, "complaint")
        elif record == "SubscriptionChange" and payload.get("SuppressSending") is True:
            _revoke(conn, delivery, "user")  # The recipient used the unsubscribe link.
        elif record == "Open":
            _record_open(conn, delivery, _occurred(payload.get("ReceivedAt"), now))
    return ACK
