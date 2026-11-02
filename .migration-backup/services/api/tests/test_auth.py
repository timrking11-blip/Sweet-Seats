"""Supabase-issued identity is verified on the server; every malformed or foreign token
is rejected with one generic answer. No database needed."""
from datetime import timedelta
from uuid import uuid4

import pytest
from conftest import TEST_ISSUER, TEST_JWT_SECRET, mint_token
from fastapi.testclient import TestClient

from app.auth import AuthConfig, AuthError, AuthUnavailable, configured, verify
from app.discovery import timestamp
from app.main import app
from app.me import auth_now

NOW = timestamp("2026-10-29T12:00:00Z")
CONFIG = AuthConfig(TEST_JWT_SECRET.encode(), TEST_ISSUER)


def claims(**changes):
    base = {"sub": str(uuid4()), "role": "authenticated", "aud": "authenticated",
            "iss": TEST_ISSUER, "iat": int(NOW.timestamp()) - 60,
            "exp": int(NOW.timestamp()) + 3600, "is_anonymous": False}
    base.update(changes)
    return {k: v for k, v in base.items() if v is not None}


def test_a_valid_user_token_yields_its_subject():
    body = claims()
    assert str(verify(mint_token(body), CONFIG, NOW).user_id) == body["sub"]
    # Supabase may send a list audience.
    assert verify(mint_token(claims(aud=["authenticated", "x"])), CONFIG, NOW)


def deep_header() -> str:
    """A header nested deeply enough to exhaust the JSON parser's recursion."""
    import base64
    raw = base64.urlsafe_b64encode(b"[" * 5000).rstrip(b"=").decode()
    return raw + "." + mint_token(claims()).split(".", 1)[1]


def alternative_signature(token: str) -> str:
    """The same signature bytes with different unused trailing bits."""
    head, signature = token.rsplit(".", 1)
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    last = alphabet.index(signature[-1])
    return head + "." + signature[:-1] + alphabet[last ^ 1]


def flip(token: str, index: int) -> str:
    parts = token.split(".")
    segment = parts[index]
    parts[index] = segment[:-2] + ("A" if segment[-2] != "A" else "B") + segment[-1]
    return ".".join(parts)


@pytest.mark.parametrize(("token", "code"), [
    (mint_token(claims(), secret="another-projects-secret-0123456789ab"), "bad_signature"),
    (flip(mint_token(claims()), 1), "bad_signature"),  # A changed payload.
    (flip(mint_token(claims()), 2), "bad_signature"),
    (mint_token(claims(), header={"alg": "none", "typ": "JWT"}), "unsupported_algorithm"),
    (mint_token(claims(), header={"alg": "HS512"}), "unsupported_algorithm"),
    (mint_token(claims(), header={"alg": "ES256", "kid": "k"}), "unsupported_algorithm"),
    (mint_token(claims(), header={"alg": "HS256", "crit": ["exp"]}), "unsupported_algorithm"),
    (mint_token(claims(exp=int(NOW.timestamp()))), "expired"),  # Expiry is exclusive.
    (mint_token(claims(exp=None)), "invalid_exp"),
    (mint_token(claims(exp=True)), "invalid_exp"),
    (mint_token(claims(nbf=int(NOW.timestamp()) + 120)), "not_yet_valid"),
    (mint_token(claims(iat=int(NOW.timestamp()) + 120)), "invalid_iat"),
    (mint_token(claims(iss="https://other.supabase.invalid/auth/v1")), "wrong_issuer"),
    (mint_token(claims(aud="anon")), "wrong_audience"),
    (mint_token(claims(role="anon")), "not_a_user_session"),
    (mint_token(claims(role="service_role")), "not_a_user_session"),
    (mint_token(claims(is_anonymous=True)), "not_a_user_session"),
    (mint_token(claims(sub="not-a-uuid")), "invalid_subject"),
    (mint_token(claims(sub=str(uuid4()).upper())), "invalid_subject"),
    (mint_token(claims(exp=float("nan"))), "invalid_exp"),
    (mint_token(claims(exp=float("inf"))), "invalid_exp"),
    (mint_token(claims(nbf=float("nan"))), "invalid_nbf"),
    (mint_token(claims(exp=10 ** 400)), "invalid_exp"),
    ("W" * 7000 + "." + mint_token(claims()).split(".", 1)[1], "malformed_token"),
    (deep_header(), "malformed_token"),
    (alternative_signature(mint_token(claims())), "bad_signature"),
    ("a.b", "malformed_token"),
    ("a.b.c.d", "malformed_token"),
    (mint_token(claims()).rsplit(".", 1)[0] + ".!!!", "malformed_token"),
    ("x" * 9000, "malformed_token"),
])
def test_rejected_tokens(token, code):
    with pytest.raises(AuthError) as rejected:
        verify(token, CONFIG, NOW)
    assert rejected.value.code == code


def test_verification_fails_closed_without_configuration(monkeypatch):
    monkeypatch.delenv("SWEET_SEATS_SUPABASE_JWT_SECRET", raising=False)
    monkeypatch.setenv("SWEET_SEATS_SUPABASE_ISSUER", TEST_ISSUER)
    with pytest.raises(AuthUnavailable):
        configured()
    monkeypatch.setenv("SWEET_SEATS_SUPABASE_JWT_SECRET", "too-short")
    with pytest.raises(AuthUnavailable):
        configured()


@pytest.fixture
def client():
    app.dependency_overrides[auth_now] = lambda: NOW
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(auth_now, None)


def test_unconfigured_sign_in_answers_503_not_a_guess(client, monkeypatch):
    monkeypatch.delenv("SWEET_SEATS_SUPABASE_JWT_SECRET", raising=False)
    response = client.get("/v1/me", headers={"Authorization": "Bearer " + mint_token(claims())})
    assert response.status_code == 503


@pytest.mark.parametrize("header", [
    None, "", "Bearer", "Basic dXNlcjpwYXNz", "Bearer a.b.c",
    "Bearer " + mint_token(claims(exp=int((NOW - timedelta(minutes=1)).timestamp()))),
    "Bearer " + mint_token(claims(role="service_role")),
])
def test_the_api_rejects_every_bad_credential_the_same_way(client, auth_env, header):
    headers = {} if header is None else {"Authorization": header}
    response = client.get("/v1/me", headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "Sign-in required."}
    assert response.headers["www-authenticate"] == 'Bearer error="invalid_token"'
    assert response.headers["cache-control"].startswith("private, no-store")
