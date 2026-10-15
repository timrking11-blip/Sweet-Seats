"""FastAPI route: verify Linear webhook, enqueue, return 200 fast (Linear times out at 5s)."""
from __future__ import annotations

import json
import os

from fastapi import APIRouter, HTTPException, Request

from adapters.linear import verify_webhook
from adapters.perplexity_research import LABEL_PRESETS
from jobs.linear_research import InMemoryQueue, JobQueue, ResearchJob

router = APIRouter()
queue: JobQueue = InMemoryQueue()  # replace with Postgres-backed queue in Phase 2


def is_research_trigger(event: dict) -> bool:
    if event.get("type") != "Issue" or event.get("action") not in ("create", "update"):
        return False
    labels = [l.get("name") for l in (event.get("data", {}).get("labels") or [])]
    return any(name in LABEL_PRESETS for name in labels)


@router.post("/webhooks/linear")
async def linear_webhook(request: Request):
    raw = await request.body()
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(400, "invalid json")
    if not verify_webhook(raw, request.headers.get("Linear-Signature"),
                          os.environ["LINEAR_WEBHOOK_SECRET"], event.get("webhookTimestamp")):
        raise HTTPException(401, "invalid signature")
    if not is_research_trigger(event):
        return {"status": "ignored"}
    queued = await queue.enqueue(ResearchJob(event["data"]["id"], "webhook"))
    return {"status": "queued" if queued else "duplicate"}
