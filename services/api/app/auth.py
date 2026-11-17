"""Server-side verification of Supabase-issued identity (Phase 2 closure; proposed,
docs/contracts/user-api-v0.1.md).

The API never takes a user id from the client. A request acts as a user only after its
bearer token's algorithm, signature, issuer, audience, role, subject and validity window
are verified here. The verified subject then becomes auth.uid() in a database session
running as the authenticated role (app.me), so row-level security decides what the user
can read or change, not a user_id filter in the API.

Supported signing: HS256 with the project's JWT secret (Supabase's symmetric signing).
Asymmetric signing keys (ES256/RS256 published as JWKS) need a reviewed cryptography
dependency and are an open owner decision; such tokens are rejected until then.
Anonymous Supabase sign-ins are rejected (proposed): they have no verified contact for
consent. Nothing here logs or returns the token or its claims.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

SECRET_ENV = "SWEET_SEATS_SUPABASE_JWT_SECRET"
ISSUER_ENV = "SWEET_SEATS_SUPABASE_ISSUER"
MAX_TOKEN_BYTES = 8192
# Clock skew allowed for nbf and iat only; exp is never extended.
LEEWAY = timedelta(seconds=30)
AUDIENCE = "authenticated"
# Unpadded base64url only; the decoder would otherwise skip characters it does not know.
SEGMENT = re.compile(r"[A-Za-z0-9_-]+")


class AuthError(Exception):
    """The token is not acceptable. A fixed code; never token content."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class AuthUnavailable(Exception):
    """Verification is not configured, so no request can act as a user (fail closed)."""


@dataclass(frozen=True)
class AuthConfig:
    secret: bytes
    issuer: str


@dataclass(frozen=True)
class Identity:
    user_id: UUID
    # When the user last proved who they are (signed in or re-authenticated), from the
    # token's amr timestamps or auth_time; None when the token does not say.
    authenticated_at: datetime | None = None


def configured() -> AuthConfig:
    secret = os.environ.get(SECRET_ENV, "")
    issuer = os.environ.get(ISSUER_ENV, "")
    # A short secret is a configuration error, not a usable key.
    if len(secret) < 32 or not issuer.startswith("https://"):
        raise AuthUnavailable()
    return AuthConfig(secret.encode(), issuer)


def _segment(part: str) -> bytes:
    if not SEGMENT.fullmatch(part) or len(part) % 4 == 1:
        raise AuthError("malformed_token")
    try:
        return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))
    except (binascii.Error, ValueError):
        raise AuthError("malformed_token") from None


def _json(part: str) -> dict:
    try:
        value = json.loads(_segment(part))
    except (UnicodeDecodeError, ValueError, RecursionError):  # Deep nesting is malformed too.
        raise AuthError("malformed_token") from None
    if not isinstance(value, dict):
        raise AuthError("malformed_token")
    return value


def _number(claims: dict, name: str, *, required: bool = False) -> float | None:
    value = claims.get(name)
    if value is None and not required:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise AuthError(f"invalid_{name}")
    try:
        number = float(value)
    except OverflowError:
        raise AuthError(f"invalid_{name}") from None
    if not math.isfinite(number):  # NaN compares false with everything; never let it pass.
        raise AuthError(f"invalid_{name}")
    return number


def _authenticated_at(claims: dict, at: float) -> datetime | None:
    """The newest authentication time the token states: Supabase's amr list of
    {method, timestamp}, else auth_time. A malformed or future time rejects the token."""
    amr = claims.get("amr")
    if amr is not None:
        if not isinstance(amr, list) or len(amr) > 16:
            raise AuthError("invalid_amr")
        if not all(isinstance(entry, dict) for entry in amr):
            raise AuthError("invalid_amr")
        latest = max((_number(entry, "timestamp", required=True) for entry in amr), default=None)
    else:
        latest = _number(claims, "auth_time")
    if latest is None:
        return None
    if latest > at + LEEWAY.total_seconds() or latest < 0:
        raise AuthError("invalid_amr")
    return datetime.fromtimestamp(latest, UTC)


def verify(token: str, config: AuthConfig, now: datetime) -> Identity:
    """The verified identity in token at now, or AuthError."""
    if len(token.encode()) > MAX_TOKEN_BYTES or token.count(".") != 2:
        raise AuthError("malformed_token")
    header_part, payload_part, signature_part = token.split(".")
    header = _json(header_part)
    # Only the configured algorithm: never "none", never one the token chooses.
    if header.get("alg") != "HS256" or "crit" in header or header.get("typ", "JWT") != "JWT":
        raise AuthError("unsupported_algorithm")
    _segment(signature_part)  # Shape check only; the comparison below is on the encoding.
    expected = base64.urlsafe_b64encode(hmac.new(
        config.secret, f"{header_part}.{payload_part}".encode(), hashlib.sha256).digest())
    # Comparing the canonical encoding rejects alternative encodings of the same bytes.
    if not hmac.compare_digest(expected.rstrip(b"="), signature_part.encode()):
        raise AuthError("bad_signature")
    claims = _json(payload_part)
    at = now.timestamp()
    if at >= _number(claims, "exp", required=True):
        raise AuthError("expired")
    not_before = _number(claims, "nbf")
    if not_before is not None and at + LEEWAY.total_seconds() < not_before:
        raise AuthError("not_yet_valid")
    issued = _number(claims, "iat")
    if issued is not None and issued > at + LEEWAY.total_seconds():
        raise AuthError("invalid_iat")
    if claims.get("iss") != config.issuer:
        raise AuthError("wrong_issuer")
    audience = claims.get("aud")
    if not (audience == AUDIENCE or (isinstance(audience, list) and AUDIENCE in audience)):
        raise AuthError("wrong_audience")
    # anon and service_role tokens are not user sessions.
    if claims.get("role") != "authenticated" or claims.get("is_anonymous") is True:
        raise AuthError("not_a_user_session")
    subject = claims.get("sub")
    try:
        user_id = UUID(subject) if isinstance(subject, str) else None
    except ValueError:
        user_id = None
    if user_id is None or str(user_id) != subject:
        raise AuthError("invalid_subject")
    try:
        authenticated_at = _authenticated_at(claims, at)
    except AuthError as exc:
        raise AuthError("invalid_amr") from exc
    return Identity(user_id, authenticated_at)


def bearer(authorization: str | None) -> str:
    """The token in an Authorization header, or AuthError."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token or " " in token:
        raise AuthError("missing_token")
    return token
