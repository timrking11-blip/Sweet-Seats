"""Waitlist sign-up for the coming-soon page (Build Plan S4; proposed).

The server, not the browser, decides what consent was given: it records its own consent
version and a SHA-256 of the exact copy, and refuses a sign-up from a page that showed an
older version. Every accepted request answers the same way, whether the email is new, a
repeat or caught by the honeypot, so the endpoint never reveals who is on the list.
Rate limiting here is per process; a shared limit waits for the provisioned environment.
"""
from __future__ import annotations

import hashlib
import re
import threading
import time
from collections import deque
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .discovery import DiscoveryError
from .discovery_postgres import PostgresStore, configured_dsn

router = APIRouter(prefix="/v1/waitlist", tags=["waitlist"])

CONSENT_VERSION = "waitlist-2026-11-17"
CONSENT_COPY = (
    "Email me when Sweet Seats opens to testers, and about the pilot. "
    "I can unsubscribe at any time. Sweet Seats keeps my email and the artists I list "
    "only to invite me and choose which artists to cover, and never sells or shares them."
)
CONSENT_COPY_SHA256 = hashlib.sha256(CONSENT_COPY.encode("utf-8")).hexdigest()

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SOURCE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
ACCEPTED = {"status": "received"}

LIMIT, WINDOW_SECONDS = 5, 600


class SignupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=6, max_length=254)
    consent: bool
    consent_version: str = Field(max_length=64)
    source: str | None = Field(default=None, max_length=64)
    artists: list[Annotated[str, Field(max_length=100)]] = Field(default=[], max_length=10)
    # Honeypot: hidden from people, filled in by naive bots.
    website: str = Field(default="", max_length=200)

    @field_validator("email")
    @classmethod
    def normalise_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL.match(value):
            raise ValueError("not an email address")
        return value

    @field_validator("source")
    @classmethod
    def normalise_source(cls, value: str | None) -> str:
        value = (value or "").strip().lower()
        return value if SOURCE.match(value) else "direct"

    @field_validator("artists")
    @classmethod
    def clean_artists(cls, values: list[str]) -> list[str]:
        cleaned = []
        for value in values:
            value = " ".join(value.split())
            if value and not any(ord(c) < 32 for c in value) and value not in cleaned:
                cleaned.append(value)
        return cleaned


class RateLimiter:
    """A sliding window per client address, in this process only."""

    def __init__(self, limit: int = LIMIT, window: float = WINDOW_SECONDS, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self.hits: dict[str, deque] = {}
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self.clock()
        with self.lock:
            hits = self.hits.setdefault(key, deque())
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            if len(self.hits) > 10_000:  # Bound memory under a flood of distinct keys.
                self.hits = {k: v for k, v in self.hits.items() if v and now - v[-1] <= self.window}
            return True


limiter = RateLimiter()


def client_key(request: Request) -> str:
    # The hosting proxy appends the real client address last; earlier entries are client-set.
    forwarded = request.headers.get("x-forwarded-for", "")
    last = forwarded.split(",")[-1].strip()
    return last or (request.client.host if request.client else "unknown")


def waitlist_store() -> PostgresStore:
    dsn = configured_dsn()
    try:
        if not dsn:
            raise DiscoveryError("store_unavailable")
        return PostgresStore(dsn)
    except DiscoveryError:
        raise HTTPException(status_code=503, detail="Sign-up is not available yet.") from None


@router.get("/consent")
def consent_copy() -> dict:
    """The copy the page must show; its version comes back with the sign-up."""
    return {"version": CONSENT_VERSION, "copy": CONSENT_COPY}


@router.post("", status_code=202)
def sign_up(body: SignupIn, request: Request,
            store: Annotated[PostgresStore, Depends(waitlist_store)]) -> dict:
    if not limiter.allow(client_key(request)):
        raise HTTPException(status_code=429, detail="Too many sign-ups from here. Try again later.")
    if body.website:
        return ACCEPTED
    if not body.consent:
        raise HTTPException(status_code=422, detail="Consent is required to join the waitlist.")
    if body.consent_version != CONSENT_VERSION:
        raise HTTPException(status_code=409, detail="The sign-up text has changed. Reload the page.")
    with store._connect() as conn, conn.transaction():
        conn.execute(
            """INSERT INTO waitlist_signups(email, consent_version, consent_copy_sha256, source, artists)
               VALUES (%s, %s, %s, %s, %s) ON CONFLICT (email) DO NOTHING""",
            (body.email, CONSENT_VERSION, CONSENT_COPY_SHA256, body.source, body.artists),
        )
    return ACCEPTED
