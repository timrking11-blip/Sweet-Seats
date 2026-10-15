"""FastAPI receiver for Linear webhooks. Run: uvicorn jobs.linear_research.webhook:app"""
import json
import os

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

from .agent import ResearchAgent, live_graphql, live_researcher, should_trigger, verify_linear_webhook

app = FastAPI()
agent = ResearchAgent(live_graphql, live_researcher)


@app.post("/webhooks/linear")
async def linear(request: Request, bg: BackgroundTasks, linear_signature: str | None = Header(None)):
    raw = await request.body()
    event = json.loads(raw)
    if not verify_linear_webhook(raw, linear_signature, os.environ["LINEAR_WEBHOOK_SECRET"],
                                 event.get("webhookTimestamp")):
        raise HTTPException(401, "bad signature")
    issue_id = should_trigger(event)
    if issue_id:
        bg.add_task(agent.handle, issue_id)  # respond <5s; Linear retries slow endpoints
    return {"queued": bool(issue_id)}
