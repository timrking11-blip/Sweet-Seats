# Linear research agent: architecture review

## Discrepancies with the Sweet Seats architecture

1. Phase mismatch. README states Phase 0 with no product code; this adds code before Phase 1 contracts and Phase 2 durable jobs/outbox exist. Treated as internal tooling, isolated from product modules.
2. No Notion decision. Linear and Perplexity are not in 01 Authority Map or 03 Source Registry. Owner must record a decision ID before merge.
3. Durable queue missing. Webhook route uses an in-memory queue (lost on restart). Phase 2 must replace it with the `research_jobs` table (or pgmq).
4. Data-use boundary. Web research must not become a product source; unknown permissions deny by default.
5. Earlier sample used `npx @linear/mcp-server`; Linear's official MCP server is remote (`https://mcp.linear.app/mcp`). Use that URL.
6. Earlier sample called the sync Perplexity SDK inside async code; fixed with `asyncio.to_thread`.
7. Supabase project has zero tables and `pg_graphql` is not installed, so there is no GraphQL storage yet.

## GraphQL storage status (checked 2026-10-15)

Supabase project `hgxkoqzcqmujlvqiwbig` (Postgres 17, us-east-1): no tables in `public`; `pg_graphql`, `pg_net`, `pg_cron`, `pgmq` available but not installed. Installed: `pgcrypto`, `uuid-ossp`, `pg_stat_statements`, `supabase_vault`.

## Leveraging Linear GraphQL for event-based triggers

- Webhooks are the trigger; GraphQL is the read/write path. Linear payloads carry `action`, `type`, `data`, `webhookId`, `webhookTimestamp`. Subscribe to `Issue`, `Comment`, `IssueLabel`, `Project`.
- Trigger matrix: label added (`research`/`research-quick`); comment starting `/research` (follow-up question on same issue); Project update (weekly research digest); Issue SLA (escalate stale research).
- Re-fetch via GraphQL on every event; never trust the webhook body for writes.
- Persist `webhookId` in `research_jobs.linear_webhook_id` for idempotency across Linear's retries (1 min, 1 h, 6 h).
- Use GraphQL filters for the scheduled sweep (`labels.name eq`, `state.type nin completed/canceled`).
- Optional: enable `pg_graphql` only when the frontend needs it; the FastAPI service can use SQL directly. Do not expose `research_jobs` through it (RLS on, no public policies).
