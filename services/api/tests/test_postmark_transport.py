"""Postmark transport against a fake Postmark (httpx.MockTransport): no network, no key.
Every outcome maps to a fixed code, and an unknown outcome is uncertain, never 'sent'."""
import httpx
import pytest

from app.alerts import DeliveryUncertain, TransportError
from app.transports.postmark import PostmarkTransport, footer

KEY = "6f1c2a8e-4b1d-4c2e-9f0a-1b2c3d4e5f60"
MESSAGE = {"template_version": "alerts-v1", "headline": "Just announced", "title": "Synthetic Night",
           "venue": "Test Hall", "local_date": "2026-12-01", "starts_at": "2026-12-01T20:00:00-05:00",
           "provenance": [{"name": "Synthetic Venue Feed", "url": "https://venue.example.invalid/e/1",
                           "observed_at": "2026-11-18T10:00:00+00:00"}],
           "first_seen_at": "2026-11-18T10:00:00+00:00", "last_confirmed_at": "2026-11-18T12:00:00+00:00"}


def transport(handler, resolve=lambda ref: "fan@example.test"):
    client = httpx.Client(base_url="https://api.postmarkapp.com", transport=httpx.MockTransport(handler))
    return PostmarkTransport("server-token-123", "alerts@sweetseats.example", resolve, client=client)


def answer(status, body):
    return lambda request: httpx.Response(status, json=body)


def test_a_send_carries_the_key_the_footer_and_no_tracking():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"ErrorCode": 0, "MessageID": "pm-1", "Message": "OK"})

    assert transport(handler).send("email", "secret://email/a", MESSAGE, KEY) == "pm-1"
    request = seen[0]
    body = __import__("json").loads(request.content)
    assert request.url.path == "/email"
    assert request.headers["X-Postmark-Server-Token"] == "server-token-123"
    assert body["To"] == "fan@example.test" and body["Metadata"] == {"dedupe_key": KEY}
    assert body["TrackOpens"] is False and body["TrackLinks"] == "None"
    assert body["Subject"] == "Just announced: Synthetic Night"
    assert "Where this came from:" in body["TextBody"]
    assert "Synthetic Venue Feed: https://venue.example.invalid/e/1" in body["TextBody"]
    assert "last confirmed 2026-11-18T12:00:00+00:00" in body["TextBody"]


def test_an_event_without_sources_says_so():
    assert "Source details are unavailable" in footer({**MESSAGE, "provenance": []})


@pytest.mark.parametrize("status,body,code,permanent", [
    (422, {"ErrorCode": 406, "Message": "Inactive recipient"}, "recipient_rejected", True),
    (422, {"ErrorCode": 300, "Message": "Invalid email"}, "recipient_rejected", True),
    (422, {"ErrorCode": 412, "Message": "Account pending"}, "provider_rejected", False),
    (401, {"ErrorCode": 10, "Message": "Bad token"}, "provider_auth", False),
    (429, {"ErrorCode": 429}, "rate_limited", False),
])
def test_refusals_are_fixed_codes(status, body, code, permanent):
    with pytest.raises(TransportError) as raised:
        transport(answer(status, body)).send("email", "secret://email/a", MESSAGE, KEY)
    assert (raised.value.code, raised.value.permanent) == (code, permanent)
    assert "fan@example.test" not in str(raised.value)


@pytest.mark.parametrize("handler", [
    answer(500, {"ErrorCode": 500}),
    answer(200, {"ErrorCode": 0}),            # Accepted but no message id.
    lambda request: httpx.Response(200, content=b"not json"),
    lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("slow", request=request)),
])
def test_an_unknown_outcome_is_uncertain(handler):
    with pytest.raises(DeliveryUncertain):
        transport(handler).send("email", "secret://email/a", MESSAGE, KEY)


def test_a_send_that_never_connected_is_retryable():
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(TransportError) as raised:
        transport(refuse).send("email", "secret://email/a", MESSAGE, KEY)
    assert raised.value.code == "provider_unreachable" and not raised.value.permanent


@pytest.mark.parametrize("resolve", [lambda ref: (_ for _ in ()).throw(KeyError(ref)), lambda ref: ""])
def test_an_unresolvable_endpoint_sends_nothing(resolve):
    calls = []
    with pytest.raises(TransportError) as raised:
        transport(lambda r: calls.append(r), resolve).send("email", "secret://email/a", MESSAGE, KEY)
    assert raised.value.code == "endpoint_unresolved" and calls == []


def test_only_email_is_supported():
    with pytest.raises(TransportError) as raised:
        transport(answer(200, {})).send("web_push", "secret://push/a", MESSAGE, KEY)
    assert raised.value.permanent


def test_reconcile_finds_the_message_by_its_key():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"TotalCount": 1, "Messages": [
            {"MessageID": "pm-9", "Metadata": {"dedupe_key": KEY}}]})

    assert transport(handler).reconcile("email", "secret://email/a", KEY) == "pm-9"
    assert seen[0].url.params["metadata_dedupe_key"] == KEY


@pytest.mark.parametrize("handler,verdict", [
    (answer(200, {"TotalCount": 0, "Messages": []}), False),
    (answer(200, {"TotalCount": 1, "Messages": [{"MessageID": "x", "Metadata": {"dedupe_key": "other"}}]}), None),
    (answer(500, {}), None),
    (answer(200, {"unexpected": True}), None),
])
def test_reconcile_says_not_delivered_only_when_postmark_has_no_record(handler, verdict):
    assert transport(handler).reconcile("email", "secret://email/a", KEY) is verdict


def test_a_transport_needs_a_token_and_a_sender():
    with pytest.raises(ValueError):
        PostmarkTransport("", "alerts@sweetseats.example", lambda ref: "x@y.z")
