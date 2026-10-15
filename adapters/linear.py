"""Linear GraphQL adapter (internal tooling only; not a Sweet Seats product data source)."""
from __future__ import annotations

import hashlib
import hmac
import os
import time

import httpx

LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
REPLAY_WINDOW_MS = 60_000  # Linear recommends rejecting deliveries older than 1 minute.

ISSUE_QUERY = """
query Issue($id: String!) {
  issue(id: $id) {
    id identifier title description url
    labels { nodes { name } }
  }
}"""

COMMENT_MUTATION = """
mutation CommentCreate($input: CommentCreateInput!) {
  commentCreate(input: $input) { success comment { id url } }
}"""

LABELED_ISSUES_QUERY = """
query LabeledIssues($label: String!) {
  issues(first: 50, filter: {
    labels: { name: { eq: $label } },
    state: { type: { nin: ["completed", "canceled"] } }
  }) { nodes { id identifier } }
}"""


class LinearError(RuntimeError):
    pass


class LinearClient:
    def __init__(self, api_key: str | None = None, transport: httpx.AsyncBaseTransport | None = None):
        self.api_key = api_key or os.environ["LINEAR_API_KEY"]
        self._transport = transport

    async def graphql(self, query: str, variables: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=30, transport=self._transport) as client:
            resp = await client.post(
                LINEAR_GRAPHQL_URL,
                headers={"Authorization": self.api_key, "Content-Type": "application/json"},
                json={"query": query, "variables": variables or {}},
            )
            resp.raise_for_status()
            payload = resp.json()
        if payload.get("errors"):
            raise LinearError(payload["errors"])
        return payload["data"]

    async def get_issue(self, issue_id: str) -> dict:
        return (await self.graphql(ISSUE_QUERY, {"id": issue_id}))["issue"]

    async def add_comment(self, issue_id: str, body: str) -> dict:
        data = await self.graphql(COMMENT_MUTATION, {"input": {"issueId": issue_id, "body": body}})
        if not data["commentCreate"]["success"]:
            raise LinearError("commentCreate returned success=false")
        return data["commentCreate"]["comment"]

    async def open_issues_with_label(self, label: str) -> list[dict]:
        return (await self.graphql(LABELED_ISSUES_QUERY, {"label": label}))["issues"]["nodes"]


def verify_webhook(raw_body: bytes, signature: str | None, secret: str, webhook_timestamp_ms: int | None,
                   now_ms: int | None = None) -> bool:
    """Verify Linear-Signature (hex HMAC-SHA256 of raw body) and the 60s replay window."""
    if not signature or webhook_timestamp_ms is None:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return False
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    return abs(now_ms - int(webhook_timestamp_ms)) <= REPLAY_WINDOW_MS
