"""Release regressions: populated upgrades and real loopback HTTP/TLS lifecycle."""
import socket
import ssl
import subprocess
import threading
import time
from datetime import timedelta
from uuid import uuid4

import pytest
from conftest import MIGRATIONS, apply_migrations, disposable_store

from app import official_feeds as feeds
from app.discovery import DEFAULT_FIXTURE, timestamp


@pytest.fixture(scope="module")
def tls_contexts(tmp_path_factory):
    folder = tmp_path_factory.mktemp("feed-tls")
    cert, key = folder / "cert.pem", folder / "key.pem"
    # Disposable test-only key; never committed or used outside a loopback server.
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
        "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost",
        "-keyout", str(key), "-out", str(cert),
    ], check=True, capture_output=True)
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(cert, key)
    return server, ssl.create_default_context(cafile=str(cert))


class Server:
    def __init__(self, payload, *, context=None, drip=False, drip_body=False):
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.port = self.listener.getsockname()[1]
        self.closed = threading.Event()
        self.stop = threading.Event()
        self.client = None

        def serve():
            try:
                raw, _ = self.listener.accept()
                raw.settimeout(2)
                self.client = context.wrap_socket(raw, server_side=True) if context else raw
                self.client.recv(65536)
                outgoing = payload
                if drip_body:
                    head, outgoing = payload.split(b"\r\n\r\n", 1)
                    self.client.sendall(head + b"\r\n\r\n")
                if drip or drip_body:
                    for byte in outgoing:
                        self.client.sendall(bytes([byte]))
                        if self.stop.wait(.03):
                            break
                else:
                    self.client.sendall(payload)
                # Client shutdown must be visible to the server, even during a drip.
                self.client.recv(1)
            except (OSError, ssl.SSLError):
                pass
            finally:
                if self.client:
                    self.client.close()
                self.closed.set()
        self.worker = threading.Thread(target=serve, daemon=True)
        self.worker.start()

    def close(self):
        self.stop.set()
        if self.client:
            try:
                self.client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self.listener.close()
        self.worker.join(3)
        assert not self.worker.is_alive()


def connection_for(server, context=None):
    class Local(feeds._PinnedHTTPSConnection):
        def __init__(self, host, address, timeout):
            super().__init__(host, address, timeout, port=server.port)
            if context:
                self._tls = context

        def connect(self):
            if context:
                return super().connect()
            self._raw = socket.create_connection((self._address, self.port), self.remaining())
            self.sock = self._raw
    return Local


@pytest.mark.parametrize("tls", [False, True])
@pytest.mark.parametrize("head", [
    b"HTTP/1.0 200 OK\r\nContent-Length: 3\r\n\r\n",
    b"HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: 3\r\n\r\n",
    b"HTTP/1.0 200 OK\r\n\r\n",  # EOF-delimited body.
])
def test_connection_closing_responses_return_complete_body(head, tls, tls_contexts):
    server_context, client_context = tls_contexts if tls else (None, None)
    server = Server(head + b"abc", context=server_context)
    try:
        # EOF-delimited responses need the server to close after the response.
        if b"Content-Length" not in head:
            server.stop.set()
            # Server normally waits for client EOF; shutdown write supplies body EOF.
            original = connection_for(server, client_context)
            class Closing(original):
                def getresponse(self):
                    response = super().getresponse()
                    server.client.shutdown(socket.SHUT_WR)
                    return response
            connection = Closing
        else:
            connection = connection_for(server, client_context)
        status, _, body = feeds._pinned_transport(
            "https://localhost/feed", "127.0.0.1", {}, 1, connection=connection)
        assert (status, body) == (200, b"abc")
        assert server.closed.wait(1)
    finally:
        server.close()


@pytest.mark.parametrize("drip_body", [False, True])
@pytest.mark.parametrize("close_header", [False, True])
def test_tls_watchdog_closes_dripping_peer(tls_contexts, close_header, drip_body):
    server_context, client_context = tls_contexts
    payload = (b"HTTP/1.1 200 OK\r\n" +
               (b"Connection: close\r\n" if close_header else b"") +
               b"X-Slow: " + b"x" * 80 + b"\r\nContent-Length: 80\r\n\r\n" + b"b" * 80)
    server = Server(payload, context=server_context, drip=not drip_body, drip_body=drip_body)
    start = time.monotonic()
    try:
        with pytest.raises(feeds.FeedError, match="deadline_exceeded"):
            feeds._pinned_transport("https://localhost/feed", "127.0.0.1", {}, .3,
                                    connection=connection_for(server, client_context))
        assert time.monotonic() - start < 1
        assert server.closed.wait(1), "TLS peer was left alive after the deadline"
    finally:
        server.close()


def test_stuck_operations_have_a_fixed_concurrency_cap():
    release = threading.Event()
    entered = []
    lock = threading.Lock()

    def stuck():
        with lock:
            entered.append(threading.current_thread())
        release.wait(3)
    try:
        for _ in range(12):
            with pytest.raises(feeds.FeedError):
                feeds._bounded(stuck, .01)
        assert 0 < len(entered) <= 4, "timed-out operations accumulated without a cap"
    finally:
        release.set()
        for worker in entered:
            worker.join(1)
        assert all(not worker.is_alive() for worker in entered)
    # Released capacity is reusable.
    assert feeds._bounded(lambda: 42, 1) == 42


def test_populated_alert_upgrade_preserves_legacy_states():
    import json
    before = [p for p in MIGRATIONS if p.name < "20261028100000"]
    after = [p for p in MIGRATIONS if p.name >= "20261028100000"]
    now = timestamp("2026-10-18T07:00:00Z")
    with disposable_store(before) as store:
        store.seed(json.loads(DEFAULT_FIXTURE.read_text()), now)
        with store._connect() as conn:
            user = uuid4()
            conn.execute("INSERT INTO auth.users(id) VALUES (%s)", (user,))
            conn.execute("INSERT INTO user_profiles(user_id) VALUES (%s)", (user,))
            event = conn.execute("SELECT event_id FROM events LIMIT 1").fetchone()["event_id"]
            ids = {}
            for status in ("pending", "sending", "sent", "failed", "suppressed"):
                row = conn.execute(
                    """INSERT INTO alerts(user_id,event_id,trigger_type,dedupe_key,template_version,
                         status,expires_at,lease_owner,lease_expires_at,sent_at,suppressed_reason)
                       VALUES (%s,%s,'announced',%s,'alerts-v1',%s,%s,%s,%s,%s,%s)
                       RETURNING alert_id""",
                    (user, event, status, status, now + timedelta(days=1),
                     "old-worker" if status == "sending" else None,
                     now + timedelta(minutes=5) if status == "sending" else None,
                     now if status == "sent" else None,
                     "expired" if status == "suppressed" else None)).fetchone()
                ids[status] = row["alert_id"]
        apply_migrations(store, after)
        with store._connect() as conn:
            rows = {r["status"]: r for r in conn.execute("SELECT * FROM alerts")}
            assert {s: r["alert_id"] for s, r in rows.items()} == ids
            assert rows["failed"]["last_error_code"] == "legacy_delivery_failed"
            assert rows["sending"]["claim_token"] is not None
            assert rows["sending"]["lease_owner"] == "old-worker"
            assert rows["sent"]["sent_at"] == now
            assert rows["suppressed"]["suppressed_reason"] == "expired"
