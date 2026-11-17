"""Consent copies the server shows and records (G-15; proposed wording, for owner and
counsel review).

Each copy is registered in public.consent_copies with its version and the SHA-256 of
this exact text (migration 20261118100000_consent_events.sql). Changing a text means a
new version and a new registered row; a test fails if the two drift apart. The client
never chooses a version: it only says grant or withdraw.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Copy:
    kind: str
    version: str
    text: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


OUTCOMES = Copy(
    kind="outcomes",
    version="outcomes-2026-11-18",
    text=(
        "Let Sweet Seats record whether I open an alert, follow its link, and tell it when "
        "I bought tickets, so it can measure which alerts are useful. This is optional, "
        "never shared or sold, and I can turn it off at any time; turning it off stops new "
        "records."
    ),
)

CURRENT = {OUTCOMES.kind: OUTCOMES}
