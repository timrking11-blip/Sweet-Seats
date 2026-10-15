import hashlib, hmac, json, time
import httpx, pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adapters.linear import LinearClient, verify_webhook
from adapters.perplexity_research import preset_for_labels, build_prompt
from jobs import linear_research as jr
from services.api import linear_webhook as wh

SECRET = "test-secret"


def issue(labels):
    return {"id": "uuid-1", "identifier": "SS-1", "title": "Ticket API terms", "description": "Compare",
            "url": "https://linear.app/x", "labels": {"nodes": [{"name": n} for n in labels]}}


def fake_linear(labels, calls):
    def handler(req: httpx.Request):
        body = json.loads(req.content)
        calls.append(body)
        q = body["query"]
        if "commentCreate" in q:
            return httpx.Response(200, json={"data": {"commentCreate": {"success": True,
                                  "comment": {"id": "c1", "url": "https://linear.app/c1"}}}})
        if "issues(" in q:
            return httpx.Response(200, json={"data": {"issues": {"nodes": [{"id": "a", "identifier": "SS-2"},
                                                                           {"id": "a", "identifier": "SS-2"}]}}})
        return httpx.Response(200, json={"data": {"issue": issue(labels)}})
    return LinearClient("k", transport=httpx.MockTransport(handler))


class FakePplx:
    seen = []
    def __init__(self):
        self.responses = self
    def create(self, **kw):
        FakePplx.seen.append(kw)
        return type("R", (), {"output_text": "REPORT [1]"})()


def sign(raw):
    return hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()


def test_verify_webhook_good_bad_and_replay():
    raw, now = b'{"a":1}', 1_000_000
    assert verify_webhook(raw, sign(raw), SECRET, now, now_ms=now)
    assert not verify_webhook(raw, "00" * 32, SECRET, now, now_ms=now)
    assert not verify_webhook(raw, sign(raw), SECRET, now - 61_000, now_ms=now)
    assert not verify_webhook(raw, None, SECRET, now, now_ms=now)


def test_preset_routing():
    assert preset_for_labels(["research"]) == "medium"
    assert preset_for_labels(["research-quick"]) == "low"
    assert preset_for_labels(["research", "research-quick"]) == "medium"
    assert preset_for_labels(["bug"]) is None


def test_prompt_contains_issue():
    p = build_prompt(issue(["research"]))
    assert "SS-1" in p and "Sources" in p


async def test_process_job_posts_comment():
    calls, FakePplx.seen = [], []
    result = await jr.process_job(jr.ResearchJob("uuid-1", "webhook"), fake_linear(["research"], calls), FakePplx)
    assert result == "posted"
    assert FakePplx.seen[0]["preset"] == "medium"
    comment = calls[-1]["variables"]["input"]
    assert comment["issueId"] == "uuid-1" and jr.REPORT_MARKER in comment["body"] and "REPORT [1]" in comment["body"]


async def test_process_job_skips_unlabeled():
    calls = []
    assert await jr.process_job(jr.ResearchJob("uuid-1", "x"), fake_linear(["bug"], calls), FakePplx) == "skipped"
    assert not any("commentCreate" in c["query"] for c in calls)


async def test_sweep_dedupes_and_drain_isolates_failures():
    q, calls = jr.InMemoryQueue(), []
    linear = fake_linear(["research-quick"], calls)
    assert await jr.sweep(q, linear) == 1

    class Boom(FakePplx):
        def create(self, **kw):
            raise TimeoutError
    await q.enqueue(jr.ResearchJob("b", "x"))
    results = await jr.drain(q, linear, Boom)
    assert results == ["failed:TimeoutError", "failed:TimeoutError"]


def test_webhook_endpoint(monkeypatch):
    monkeypatch.setenv("LINEAR_WEBHOOK_SECRET", SECRET)
    wh.queue = jr.InMemoryQueue()
    app = FastAPI(); app.include_router(wh.router)
    c = TestClient(app)
    ev = {"action": "create", "type": "Issue", "webhookTimestamp": int(time.time() * 1000),
          "data": {"id": "uuid-9", "labels": [{"name": "research"}]}}
    raw = json.dumps(ev).encode()
    h = {"Linear-Signature": sign(raw), "Content-Type": "application/json"}
    assert c.post("/webhooks/linear", content=raw, headers=h).json() == {"status": "queued"}
    assert c.post("/webhooks/linear", content=raw, headers=h).json() == {"status": "duplicate"}
    assert c.post("/webhooks/linear", content=raw, headers={"Linear-Signature": "bad"}).status_code == 401
    ev2 = dict(ev, type="Comment"); raw2 = json.dumps(ev2).encode()
    assert c.post("/webhooks/linear", content=raw2, headers={"Linear-Signature": sign(raw2)}).json() == {"status": "ignored"}
