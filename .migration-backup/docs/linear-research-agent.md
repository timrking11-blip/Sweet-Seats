# Research architecture reconciliation - 15 October 2026

Decision SS-ADR-007; contract SS-RESEARCH-0.2. Definition owner: Timothy King. [Full contract](contracts/research-v0.2.md).

Proposed amendment (not yet approved): [SS-RESEARCH-0.3](contracts/research-v0.3.md) replaces Perplexity with the Claude API as the research processor and binds approvals to an execution profile. SS-RESEARCH-0.2 governs until the amendment is recorded in Notion.

## Verified repository facts

GitHub metadata reports private visibility. Main at 68d08b9a89146271ea67fb7062a6ae450a3dd20e contains only README.md. PR #1 (feat/linear-research-agent) and PR #2 (feat/linear-research-agent-v2) contain competing unmerged scaffolds. The earlier statements "only README" and "code exists" referred to different branches and can both be true. This amendment reconciles PR #2; it is draft, not deployed. PR #1 is a historical alternative, not a second standard to merge.

## Resolved discrepancies

1. Authority: SS-ADR-007 adds internal tooling, with Notion approved intent and Linear execution tracking. Reports remain advisory.
2. Source boundary: research uses an internal processor/source registration; underlying evidence retains provenance and rights. No direct product/model ingestion.
3. Cadence: hourly scan for approved research-quick requests, not recurring research for every labeled issue. Other labels/modes deferred.
4. Idempotency: request/revision key and completed ledger; exact brief changes require new approval. Delivery dedupe is separate.
5. Publication: original worker's automatic comments removed; external write method now fails closed. Exact approvals and durable outbox required later.
6. Webhooks: original in-memory acknowledgement removed; no HTTP route registered. Durable enqueue is a prerequisite for future activation.
7. SDK/MCP: unverified automatic SDK call removed; remote MCP deferred. Provider versions/endpoints will be verified before implementation.
8. Storage: original incomplete queue migration withdrawn (no DDL). No live DB facts inferred from an account or active empty project. GraphQL is not storage and no extension is required to call Linear remotely.
9. Evidence: offline contract validation and synthetic plan only; no claim of live integration or production durability.

This narrows functionality intentionally to resolve unsafe semantics before activation; earlier source is preserved in Git history at 1f3071ee8f8442447eb2537f4c2d336dc782676b. Main, existing user/customer records and infrastructure are untouched.

## Remaining implementation work

Authenticated approval storage; persistent job/attempt/claim/lease/report/evidence ledger; aggregate cost reservations; scoped/paginated Linear reads; verified Perplexity adapter; failure/cancellation/retry reconciliation; retention enforcement; then hourly scheduler deployment. Publication is a later increment. No new microservice or production database is introduced here. Product discovery proceeds independently.
