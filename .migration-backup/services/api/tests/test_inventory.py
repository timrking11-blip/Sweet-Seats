import pytest

from app.discovery import DiscoveryError
from app.inventory import InventoryStatusAdapter


def test_inventory_cannot_be_activated_by_discovery_credentials(monkeypatch):
    monkeypatch.setenv("TICKETMASTER_API_KEY", "synthetic-canary")
    adapter = InventoryStatusAdapter()
    assert adapter.enabled is False
    adapter.enabled = True
    with pytest.raises(DiscoveryError, match="inventory_status_not_authorized"):
        adapter.fetch("synthetic-event")
