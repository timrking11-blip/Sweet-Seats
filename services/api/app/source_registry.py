"""Planned provider sources (SS-ADR-003 deny-by-default source permissions).

A registry entry records intent and known terms constraints. It is not activation:
every permission use stays false until the owner records a separate approval with
evidence, terms version and validity window, mirroring supabase source_permissions.
"""
from __future__ import annotations

import copy
from uuid import uuid5

from .discovery import NAMESPACE, USES

TICKETMASTER_DISCOVERY = "ticketmaster-discovery"

_SOURCES: dict[str, dict] = {
    TICKETMASTER_DISCOVERY: {
        "source_id": str(uuid5(NAMESPACE, "source:" + TICKETMASTER_DISCOVERY)),
        "slug": TICKETMASTER_DISCOVERY,
        "name": "Ticketmaster Discovery API v2",
        "kind": "provider",
        "source_type": "event_listing_api",
        "official_url": "https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/",
        "terms_url": "https://developer.ticketmaster.com/support/terms-of-use/",
        "access_status": "planned",
        "adapter_version": "ticketmaster-discovery-v2-0.1",
        "rate_limit_note": "Default developer key: 5000 calls/day and 5 requests/second.",
        # Candidates for owner review only; candidacy grants nothing.
        "candidate_uses": ["collect", "display"],
        "constraints": [
            ("Discovery API only; Partner (cart/reserve/purchase), Top Picks and Availability "
             "are partner-only and out of scope."),
            "Do not cache Event Content beyond reasonable periods needed to provide the service.",
            "Do not replicate Ticketmaster's core ticketing experience.",
            "No revenue derived from the content except as the terms allow (affiliate).",
            "Remove content within 24 hours of a Ticketmaster request.",
            "priceRanges are optional display metadata, never price history.",
        ],
        "artist_mappings": {},
        "venue_mappings": {},
        "permission": {
            "permission_id": str(uuid5(NAMESPACE, "permission:" + TICKETMASTER_DISCOVERY)),
            "terms_version": None,
            "evidence_ref": None,
            "approved_at": None,
            "expires_at": None,
            "revoked_at": None,
            "uses": dict.fromkeys(sorted(USES), False),
        },
    },
}


def planned_source(slug: str) -> dict:
    """Return a copy so callers cannot widen the registered grant in place."""
    return copy.deepcopy(_SOURCES[slug])
