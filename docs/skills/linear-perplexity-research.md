# Skill standard: Linear + Perplexity web research agents

Status: proposed (needs Notion decision ID). Applies to any agent in Sweet Seats that reads work from Linear, does web research through Perplexity, and writes results back.

## Build options

| Option | Trigger | Perplexity preset | Best for | Notes |
|---|---|---|---|---|
| A. Scheduled automation (simple research) | Cron sweep of open issues labeled `research-quick` | `low` | Fact checks, vendor lookups, API terms summaries | Default for simple flows. Cheap, predictable. |
| B. Event-driven webhook | Linear `Issue` create/update with `research` label | `medium` | Decision-ready deep research | Must enqueue; Linear webhooks time out at 5s. |
| C. Custom agent via Linear MCP | Agent session (Claude/Cursor/Computer) | `medium` or custom model + `web_search` tool | Interactive triage, spawning sub-issues | Remote MCP at `https://mcp.linear.app/mcp`. Writes need human approval. |
| D. Perplexity Computer automation | Scheduled task in Computer | n/a (Computer researches) | Owner-only digests, no code | Requires Linear connector; outside repo authority. |

## Required behaviours (all options)

1. Verify `Linear-Signature` (hex HMAC-SHA256 of raw body) and reject `webhookTimestamp` older than 60s.
2. Respond 200 within 5s; never run research inline in the webhook.
3. One active job per issue (unique index on `research_jobs`); webhook and sweep must not double-post.
4. Write back as a Linear comment containing the marker `<!-- sweet-seats:research-report -->`; never change issue state, assignee or create sub-issues without human approval.
5. Max 3 concurrent deep-research jobs.
6. Cite sources; separate facts from interpretation; footer "human review required".
7. Research output is internal planning material. It is not a Sweet Seats data source and must never feed events, offers, features or model training (Source Registry 03).
8. Secrets via env (`PERPLEXITY_API_KEY`, `LINEAR_API_KEY`, `LINEAR_WEBHOOK_SECRET`); never in Git.

## Labels

| Label | Flow |
|---|---|
| `research-quick` | Option A, preset `low` |
| `research` | Option B, preset `medium` (wins if both present) |

## Code map

- `adapters/linear.py` GraphQL client + webhook verification
- `adapters/perplexity_research.py` preset routing, prompt, Agent API call
- `jobs/linear_research.py` queue protocol, worker, scheduled sweep
- `services/api/linear_webhook.py` FastAPI receiver
- `db/migrations/0001_research_jobs.sql` proposed durable queue (not applied)
- `tests/test_linear_research.py` 7 tests, no network
