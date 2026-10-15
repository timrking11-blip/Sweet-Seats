# Architecture review — research agent install (2026-10-15)

| # | Discrepancy | Severity | Recommendation |
|---|---|---|---|
| 1 | Repo is still **public**; README says private change pending. Webhook/agent code reveals endpoints. | High | Confirm private visibility before deploying. |
| 2 | **Linear and Perplexity are not in the Authority map** or Source Registry (03). Deny-by-default says unregistered sources are denied. | High | Add Notion decision: Perplexity = advisory research (no storage/training rights); Linear = work tracking. |
| 3 | **No runtime provisioned** (Phase 2). The webhook has nowhere to run. | Medium | Use Option A automation until Render worker exists. |
| 4 | Idempotency is in-memory; README requires durable jobs/outbox. | Medium | Add `research_runs` table in Phase 2. |
| 5 | Prior example used `@linear/mcp-server` npx package; official Linear MCP is remote at `mcp.linear.app`. | Low | Use remote MCP (Option C). |
| 6 | Prior example called the sync Perplexity client inside `async` code (blocks the loop). | Low | Fixed: agent is sync and runs as a background task. |
| 7 | Supabase: `pg_graphql`, `pgmq`, `pg_net`, `pg_cron` available but **not installed**; 0 public tables; 0 storage buckets. | Info | No GraphQL storage exists yet; see below. |
| 8 | Agent placed in `jobs/` per README's recommended layout; `tests/` likewise. | Info | Consistent. |

## GraphQL storage
You do not have GraphQL storage today. Linear's GraphQL is Linear's API, not your storage. Supabase can expose `pg_graphql` once enabled and tables exist; recommended only for read access to `research_runs`. For triggers, prefer Linear webhooks → `pgmq` queue → worker over polling.
