"""Offline tests for the unmounted Linear webhook authenticity helper. No network or server."""
import asyncio
import hashlib
import hmac
import json
from pathlib import Path
import re
import unittest

from services.api.linear_signature import (REPLAY_WINDOW_MS, WebhookRejected,
                                           authenticate_delivery, verify_signature,
                                           verify_timestamp)
from services.api.linear_webhook import linear_webhook

SECRET = "whsec_synthetic_test"
NOW = 1_800_000_000_000


def sign(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def event(ts=NOW) -> bytes:
    return json.dumps({"action": "create", "type": "Issue", "webhookTimestamp": ts,
                       "data": {"id": "iss-1", "team": {"key": "SS"}}}).encode()


class SignatureTests(unittest.TestCase):
    def test_valid_signature_accepted(self):
        body = event()
        verify_signature(body, sign(body), SECRET)

    def test_uppercase_or_padded_hex_accepted(self):
        body = event()
        verify_signature(body, f" {sign(body).upper()} ", SECRET)

    def test_bad_signature_rejected(self):
        with self.assertRaises(WebhookRejected) as e:
            verify_signature(event(), "deadbeef", SECRET)
        self.assertEqual(e.exception.status, 401)

    def test_missing_signature_rejected(self):
        for missing in (None, ""):
            with self.assertRaises(WebhookRejected) as e:
                verify_signature(event(), missing, SECRET)
            self.assertEqual(e.exception.status, 401)

    def test_unconfigured_secret_fails_closed(self):
        body = event()
        with self.assertRaises(WebhookRejected) as e:
            verify_signature(body, sign(body, ""), "")
        self.assertIn("not configured", e.exception.reason)

    def test_wrong_secret_rejected(self):
        body = event()
        with self.assertRaises(WebhookRejected):
            verify_signature(body, sign(body, "another-secret"), SECRET)

    def test_tampered_body_rejected(self):
        body = event()
        with self.assertRaises(WebhookRejected):
            verify_signature(body.replace(b"iss-1", b"iss-2"), sign(body), SECRET)

    def test_signature_binds_raw_bytes_not_parsed_json(self):
        body = event()
        reserialized = json.dumps(json.loads(body), separators=(",", ":")).encode()
        self.assertNotEqual(body, reserialized)
        with self.assertRaises(WebhookRejected):
            verify_signature(reserialized, sign(body), SECRET)

    def test_non_ascii_signature_is_rejection_not_crash(self):
        with self.assertRaises(WebhookRejected):
            verify_signature(event(), "é" * 64, SECRET)

    def test_rejection_reason_never_contains_secret_or_body(self):
        body = event()
        with self.assertRaises(WebhookRejected) as e:
            verify_signature(body, "deadbeef", SECRET)
        self.assertNotIn(SECRET, str(e.exception))
        self.assertNotIn("iss-1", str(e.exception))


class TimestampTests(unittest.TestCase):
    def test_current_timestamp_accepted(self):
        verify_timestamp({"webhookTimestamp": NOW}, now_ms=NOW)

    def test_window_boundary_is_inclusive(self):
        verify_timestamp({"webhookTimestamp": NOW - REPLAY_WINDOW_MS}, now_ms=NOW)
        verify_timestamp({"webhookTimestamp": NOW + REPLAY_WINDOW_MS}, now_ms=NOW)

    def test_replay_outside_window_rejected(self):
        with self.assertRaises(WebhookRejected) as e:
            verify_timestamp({"webhookTimestamp": NOW - 61_000}, now_ms=NOW)
        self.assertEqual(e.exception.status, 401)

    def test_future_skew_outside_window_rejected(self):
        with self.assertRaises(WebhookRejected):
            verify_timestamp({"webhookTimestamp": NOW + REPLAY_WINDOW_MS + 1}, now_ms=NOW)

    def test_missing_or_malformed_timestamp_rejected(self):
        for payload in ({}, {"webhookTimestamp": None}, {"webhookTimestamp": str(NOW)},
                        {"webhookTimestamp": True}, {"webhookTimestamp": float("nan")},
                        {"webhookTimestamp": float("inf")}):
            with self.subTest(payload=payload), self.assertRaises(WebhookRejected):
                verify_timestamp(payload, now_ms=NOW)

    def test_seconds_instead_of_milliseconds_rejected(self):
        with self.assertRaises(WebhookRejected):
            verify_timestamp({"webhookTimestamp": NOW // 1000}, now_ms=NOW)


class AuthenticateDeliveryTests(unittest.TestCase):
    def test_valid_delivery_returns_payload(self):
        body = event()
        payload = authenticate_delivery(body, sign(body), SECRET, now_ms=NOW)
        self.assertEqual(payload["data"]["id"], "iss-1")

    def test_signature_checked_before_parsing(self):
        body = b"not json"
        with self.assertRaises(WebhookRejected) as e:
            authenticate_delivery(body, "deadbeef", SECRET, now_ms=NOW)
        self.assertEqual(e.exception.status, 401)

    def test_signed_invalid_json_is_400(self):
        for body in (b"not json", b"\xff\xfe", b"[1, 2]"):
            with self.subTest(body=body), self.assertRaises(WebhookRejected) as e:
                authenticate_delivery(body, sign(body), SECRET, now_ms=NOW)
            self.assertEqual(e.exception.status, 400)

    def test_validly_signed_replay_rejected(self):
        body = event(ts=NOW - 61_000)
        with self.assertRaises(WebhookRejected):
            authenticate_delivery(body, sign(body), SECRET, now_ms=NOW)


class StillUnmountedTests(unittest.TestCase):
    def test_webhook_entrypoint_remains_disabled(self):
        with self.assertRaises(RuntimeError):
            asyncio.run(linear_webhook(None))

    def test_no_api_module_imports_the_helper(self):
        imports = re.compile(r"^\s*(from|import)\s[^\n]*linear_signature", re.MULTILINE)
        importers = [str(p) for p in Path("services/api").rglob("*.py")
                     if imports.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(importers, [], "helper must stay unmounted until activation is approved")


if __name__ == "__main__":
    unittest.main()
