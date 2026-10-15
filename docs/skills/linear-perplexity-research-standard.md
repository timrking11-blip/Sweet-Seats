# SS-RESEARCH-0.1 — Linear × Perplexity Research Skills Standard

Status: proposed (requires a Notion decision ID before becoming authoritative — see README Authority table).

## 1. Skills (capabilities the system must have)

| Skill | Owner | Contract |
|---|---|---|
| Intake | Linear | Issue labeled `research` (fast) or `research:deep` (medium preset). Title = question, description = context/constraints. |
| Gate | `jobs/linear_research/agent.py::gate` | Deny by default: no label → skip; blocked claims (guaranteed savings, cheapest price, unannounced access, auto-purchase) → skip. |
| Research | Perplexity Agent API (`responses.create(preset=...)`) | `fast` for lookups, `medium` for multi-step deep research. Must return cited sources. |
| Write-back | Linear GraphQL `commentCreate` (or Linear MCP) | One comment per run, timestamped, ends with "Human review required". |
| Verify | Webhook receiver | HMAC-SHA256 `Linear-Signature` over raw body; reject `webhookTimestamp` older than 60 s. |
| Idempotency | Agent | One report per issue per trigger; move to Postgres `research_runs` in Phase 2. |
| Escalation | Human | Agents never change state, create child issues, or close issues without approval. |

## 2. Build options

| Option | When to use | Trigger | Write-back | Effort |
|---|---|---|---|---|
| A. Perplexity Computer automation | Simple recurring/one-off research, no code | Scheduled or Linear-connector trigger | Linear connector | Lowest |
| B. Python job (this repo) | Default for Sweet Seats | Linear webhook → FastAPI → background task | Linear GraphQL | Low |
| C. Custom MCP agent | Agent needs to browse/edit many Linear objects | Same as B | Linear MCP (`https://mcp.linear.app/mcp`, OAuth or API key bearer) | Medium |
| D. Event pipeline | High volume, retries, audit | Webhook → Supabase `pgmq`/outbox → worker | GraphQL + Postgres log | Higher |

Rule: start with A for simple research flows; use B for anything that must be tested in GitHub; graduate to D only when Phase 2 runtime exists.

## 3. Simple-research automation recipe (Option A)

Daily: "Find Linear issues labeled `research` with no comment containing 'Research report'. For each, run fast web research on the title/description and post a cited comment ending in 'Human review required'." Escalate `research:deep` issues to Option B.

## 4. Custom agent rules (Options B–D)

1. Read issue → gate → research → write back; nothing else without approval.
2. Respond to webhooks in < 5 s; do the work in a background task/worker.
3. Max 3–5 concurrent deep-research jobs.
4. Secrets only in env vars (`PERPLEXITY_API_KEY`, `LINEAR_API_KEY`, `LINEAR_WEBHOOK_SECRET`); never commit.
5. Research output is advisory text, not a source of record; it is not a licensed data source and must not feed pricing models.

## 5. Linear GraphQL event triggers

Subscribe a Linear webhook (Settings → API → Webhooks) to `Issue` and `Comment` resources.

| Event | Condition | Action |
|---|---|---|
| Issue create | has `research` label | fast research |
| Issue update | `updatedFrom.labelIds` present and research label now on | research (prevents firing on every edit) |
| Comment create | body starts with `/research` | re-run with comment as follow-up (future) |
| Issue update | state → "Ready for research" | deep research (future) |
| Cycle/project milestone | scheduled | batch digest via automation |

Use GraphQL queries (`issues(filter: {labels: {name: {eq: "research"}}})`) for backfill/polling when webhooks are missed.

## 6. Tests required before merge

`tests/linear_research`: label gate, preset routing, blocked claims, idempotency, signature + replay window, trigger rules. CI: `.github/workflows/research-agent-tests.yml`.
