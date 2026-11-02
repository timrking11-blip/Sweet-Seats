from app.main import discovery_mode, health


def test_health_is_available() -> None:
    assert health() == {"status": "ok", "service": "sweet-seats-api"}


def test_discovery_is_honest_about_source_status() -> None:
    assert discovery_mode()["mode"] == "synthetic"

