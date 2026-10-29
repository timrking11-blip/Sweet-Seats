"""Signed-in user workflows: profile, follows, consent withdrawal and deletion requests
(Phase 2 closure; proposed, docs/contracts/user-api-v0.1.md).

Every query runs in a transaction as the authenticated role, with the verified token
subject as auth.uid() (app.auth). No query here filters by user_id: row-level security
is the ownership boundary, and a row the user cannot see answers 404, whoever owns it.
Request bodies forbid unknown fields, so a client cannot name a user_id.

Creating a notification subscription is not offered: it needs a verified endpoint and a
recorded consent version, and the notification vendor is an open owner decision. The
database only lets signed-in users revoke (20261029100000_user_consent_integrity.sql).
A deletion request is recorded and suppresses pending alerts at once; the purge itself
waits for the retention decision.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .auth import AuthError, AuthUnavailable, Identity, bearer, configured, verify
from .discovery import DiscoveryError
from .discovery_postgres import PostgresStore

router = APIRouter(prefix="/v1/me", tags=["me"])

# Run as the API role Supabase gives signed-in users, with only the verified subject.
ACT_AS_USER = "SET LOCAL ROLE authenticated"


def auth_now() -> datetime:
    return datetime.now(UTC)


def user_store() -> PostgresStore:
    dsn = os.environ.get("SWEET_SEATS_LOCAL_DATABASE_URL")
    try:
        if not dsn:
            raise DiscoveryError("store_unavailable")
        return PostgresStore(dsn)
    except DiscoveryError:
        raise HTTPException(status_code=503, detail="Account service unavailable.") from None


def current_user(authorization: Annotated[str | None, Header()] = None,
                 now: datetime = Depends(auth_now)) -> Identity:
    try:
        return verify(bearer(authorization), configured(), now)
    except AuthUnavailable:
        raise HTTPException(status_code=503, detail="Sign-in is not configured.") from None
    except AuthError:
        # One answer for every rejection: the client learns nothing about which check failed.
        raise HTTPException(status_code=401, detail="Sign-in required.",
                            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'}) from None


@contextmanager
def user_session(store: PostgresStore, identity: Identity) -> Iterator[psycopg.Connection]:
    """A transaction that runs as the signed-in user under row-level security."""
    subject = str(identity.user_id)
    claims = json.dumps({"sub": subject, "role": "authenticated"})
    try:
        with store._connect() as conn, conn.transaction():
            conn.execute(ACT_AS_USER)
            # Both settings auth.uid() can read, so neither can carry another value.
            conn.execute("SELECT set_config('request.jwt.claims', %s, true), "
                         "set_config('request.jwt.claim.sub', %s, true)", (claims, subject))
            yield conn
    except psycopg.errors.InsufficientPrivilege as exc:
        # Only the deletion-request trigger is the user's state. Any other refusal (a
        # login that may not switch role, an RLS check) is a server fault, not a 409.
        if exc.diag.message_primary == "deletion_requested":
            raise HTTPException(status_code=409, detail="Account deletion requested.") from None
        raise HTTPException(status_code=503, detail="Account service unavailable.") from None
    except psycopg.OperationalError:
        raise HTTPException(status_code=503, detail="Account service unavailable.") from None


User = Annotated[Identity, Depends(current_user)]
Store = Annotated[PostgresStore, Depends(user_store)]


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locale: str = Field(default="en-US", pattern=r"^[a-z]{2,3}(-[A-Z]{2})?$")
    timezone: str = "America/New_York"

    @field_validator("timezone")
    @classmethod
    def iana_timezone(cls, value: str) -> str:
        # Exact IANA keys only; ZoneInfo alone also accepts file-system paths.
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("unknown time zone") from None
        if value not in available_timezones():
            raise ValueError("unknown time zone")
        return value


def _overview(conn) -> dict:
    profile = conn.execute(
        """SELECT locale, timezone, consent_version, deletion_requested_at,
                  outcome_consent_at IS NOT NULL AS outcome_consent
           FROM public.user_profiles""").fetchone()
    follows = conn.execute(
        """SELECT artist_id, enabled, updated_at FROM public.artist_follows
           ORDER BY created_at, artist_id""").fetchall()
    # The endpoint reference is a secret-store pointer; it is never returned.
    subscriptions = conn.execute(
        """SELECT subscription_id, channel, consent_version, consent_at, revoked_at
           FROM public.notification_subscriptions ORDER BY created_at, subscription_id""").fetchall()
    return {"profile": profile, "follows": follows, "subscriptions": subscriptions}


@router.get("")
def me(user: User, store: Store) -> dict:
    with user_session(store, user) as conn:
        return {"user_id": str(user.user_id), **_overview(conn)}


@router.put("/profile")
def put_profile(body: ProfileIn, user: User, store: Store) -> dict:
    with user_session(store, user) as conn:
        try:
            with conn.transaction():
                conn.execute(
                    """INSERT INTO public.user_profiles(user_id, locale, timezone)
                       VALUES ((SELECT auth.uid()), %s, %s)
                       ON CONFLICT (user_id) DO UPDATE
                         SET locale = excluded.locale, timezone = excluded.timezone,
                             updated_at = now()""", (body.locale, body.timezone))
        except psycopg.errors.ForeignKeyViolation:
            raise HTTPException(status_code=409, detail="Account not found.") from None
        return _overview(conn)["profile"]


@router.put("/follows/{artist_id}")
def follow(artist_id: UUID, user: User, store: Store) -> dict:
    with user_session(store, user) as conn:
        try:
            with conn.transaction():
                row = conn.execute(
                    """INSERT INTO public.artist_follows(user_id, artist_id)
                       VALUES ((SELECT auth.uid()), %s)
                       ON CONFLICT (user_id, artist_id) DO UPDATE
                         SET enabled = true, updated_at = now()
                       RETURNING artist_id, enabled, updated_at""", (artist_id,)).fetchone()
        except psycopg.errors.ForeignKeyViolation as exc:
            missing_profile = exc.diag.constraint_name == "artist_follows_user_id_fkey"
            raise HTTPException(status_code=409 if missing_profile else 404,
                                detail="Create a profile first." if missing_profile
                                else "Artist not found.") from None
        return row


@router.delete("/follows/{artist_id}", status_code=204)
def unfollow(artist_id: UUID, user: User, store: Store) -> Response:
    """Disable the follow. Alerts already queued for it are suppressed before any send."""
    with user_session(store, user) as conn:
        row = conn.execute(
            """UPDATE public.artist_follows SET enabled = false, updated_at = now()
               WHERE artist_id = %s RETURNING artist_id""", (artist_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Follow not found.")
    return Response(status_code=204)


@router.post("/subscriptions/{subscription_id}/revoke")
def revoke(subscription_id: UUID, user: User, store: Store) -> dict:
    """Withdraw notification consent for one subscription. One way and idempotent; the
    database stamps the time. Pending deliveries to it are suppressed before any send."""
    with user_session(store, user) as conn:
        conn.execute(
            """UPDATE public.notification_subscriptions SET revoked_at = now()
               WHERE subscription_id = %s AND revoked_at IS NULL""", (subscription_id,))
        row = conn.execute(
            """SELECT subscription_id, channel, revoked_at FROM public.notification_subscriptions
               WHERE subscription_id = %s""", (subscription_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Subscription not found.")
    return row


@router.post("/deletion-request", status_code=202)
def request_deletion(user: User, store: Store) -> dict:
    """Record a deletion request, creating the profile row if the account has none.
    From then on no alert is planned or sent, and the profile and follows cannot be
    changed. Idempotent; the database stamps the time, and the user cannot withdraw it."""
    with user_session(store, user) as conn:
        try:
            with conn.transaction():
                conn.execute(
                    """INSERT INTO public.user_profiles(user_id, deletion_requested_at)
                       VALUES ((SELECT auth.uid()), now()) ON CONFLICT (user_id) DO NOTHING""")
        except psycopg.errors.ForeignKeyViolation:
            raise HTTPException(status_code=409, detail="Account not found.") from None
        conn.execute(
            """UPDATE public.user_profiles SET deletion_requested_at = now(), updated_at = now()
               WHERE deletion_requested_at IS NULL""")
        row = conn.execute("SELECT deletion_requested_at FROM public.user_profiles").fetchone()
    return {"deletion_requested_at": row["deletion_requested_at"],
            "pending_alerts": "suppressed", "purge": "pending_retention_decision"}
