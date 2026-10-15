import hashlib, hmac, json
from jobs.linear_research.agent import ResearchAgent, should_trigger, verify_linear_webhook

def issue(labels, title="Compare NYC venue APIs", desc="Which on-sale feeds exist?"):
    return {"id": "uuid-1", "identifier": "SS-1", "title": title, "description": desc, "url": "u",
            "labels": {"nodes": [{"name": l} for l in labels]}}

class FakeGQL:
    def __init__(self, iss): self.iss, self.calls = iss, []
    def __call__(self, q, v):
        self.calls.append(v)
        if "commentCreate" in q: return {"commentCreate": {"comment": {"id": "c1", "url": "cu"}}}
        return {"issue": self.iss}

def agent(iss, sink):
    return ResearchAgent(FakeGQL(iss), lambda p, preset: sink.append(preset) or "REPORT [1]")

def test_posts_fast_for_research_label():
    s = []; a = agent(issue(["research"]), s)
    out = a.handle("uuid-1")
    assert out["status"] == "posted" and s == ["fast"]
    body = a.graphql.calls[-1]["input"]["body"]
    assert "REPORT" in body and "Human review required" in body

def test_deep_label_uses_medium():
    s = []; agent(issue(["research:deep"]), s).handle("uuid-1"); assert s == ["medium"]

def test_skips_without_label():
    s = []; assert agent(issue(["bug"]), s).handle("uuid-1")["status"] == "skipped" and not s

def test_blocks_forbidden_claims():
    s = []; out = agent(issue(["research"], title="Find guaranteed savings"), s).handle("uuid-1")
    assert out["status"] == "skipped" and "blocked" in out["reason"] and not s

def test_idempotent():
    s = []; a = agent(issue(["research"]), s); a.handle("uuid-1")
    assert a.handle("uuid-1")["status"] == "duplicate" and len(s) == 1

def test_signature():
    body = json.dumps({"x": 1}).encode(); sig = hmac.new(b"k", body, hashlib.sha256).hexdigest()
    assert verify_linear_webhook(body, sig, "k", 1_000_000, now=lambda: 1000.0)
    assert not verify_linear_webhook(body, "bad", "k", 1_000_000, now=lambda: 1000.0)
    assert not verify_linear_webhook(body, sig, "k", 1_000_000, now=lambda: 2000.0)  # replay

def test_trigger_rules():
    ev = {"type": "Issue", "action": "create", "data": {"id": "i", "labels": [{"name": "research"}]}}
    assert should_trigger(ev) == "i"
    assert should_trigger({**ev, "action": "update", "updatedFrom": {"title": "x"}}) is None
    assert should_trigger({**ev, "action": "update", "updatedFrom": {"labelIds": []}}) == "i"
    assert should_trigger({**ev, "type": "Comment"}) is None
