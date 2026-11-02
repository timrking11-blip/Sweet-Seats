"""Inventory Status integration boundary; intentionally has no transport implementation.

Discovery credentials and grants never authorize Inventory Status. A future change
must verify separate entitlement/rights and implement an independently gated adapter.
"""
from .discovery import DiscoveryError


class InventoryStatusAdapter:
    enabled = False

    def fetch(self, event_id: str) -> dict:
        # Even caller mutation of enabled cannot activate an unimplemented transport.
        raise DiscoveryError("inventory_status_not_authorized_or_implemented")
