# SS-RESEARCH-0.2: hourly internal research contracts

Decision: SS-ADR-007, owner Timothy King, authorized 2026-10-15. Definition status: approved for this narrow scope; implementation on draft PR #2; production activation blocked. [Notion authority/decision register](https://app.notion.com/p/3f57ecee36a98119aff6f8b3496376f6).

This version supersedes the competing contracts in PR #1 and the original PR #2. Historical drafts remain in Git history; do not combine them into one specification. Main remains documentation-only until merge. The offline selector and validators are implemented; scheduling, external integrations, authentication, durable database execution, and publication are not.

## 1. Authority and isolation

Notion owns approved architecture, rights, decisions, roadmap and acceptance criteria. GitHub owns code/contracts/tests and implementation evidence. Miro remains derived. PostgreSQL is the intended operational state authority. Linear, when activated, owns execution task status, not architecture or rights approval. Until Linear is configured, track this implementation through GitHub PR #2 rather than inventing a connected Linear workspace.

Perplexity provides advisory internal evidence. Register it as an internal research processor/source boundary with underlying website provenance; it has no authority to approve licenses. Research reports must not directly feed canonical events, offers, inventory, features, labels, forecasts or training/testing data. A human may use reviewed evidence to propose a separately approved architecture/source decision. Do not send secrets, private records, precise origins, licensed samples or confidential contracts to research providers.

## 2. Schedule and candidate contract

Target cadence: one tick each hour, cron `0 * * * *`, UTC. UTC avoids DST duplicate/missing local hours. A tick checks for pending requests; it does not order fresh research every hour. Max one new request per tick, one execution at a time. Coalesce missed ticks to a single current scan; never replay each missed hour as new billable research. Empty/unchanged/completed queues perform no research.

Canonical label: `research-quick`; mode `quick`. The old `research` and `research:deep` labels do not trigger this slice. Deep research, webhooks, MCP and consumer Perplexity conversation writeback are deferred. Label presence is routing only, never execution or spending approval. Provider preset/SDK/endpoint selection must be verified from current official documentation when implementing the adapter; this contract makes no unverified SDK promise.

`config/research-hourly.json` is disabled intent, not a deployed scheduler. The offline CLI operates on synthetic candidates and performs zero network calls. It does not read live Linear or create a ChatGPT recurring task.

## 3. Research request and execution authorization

Request fields (closed set): version, team_id, project_id, issue_id, request_id (UUID), revision (positive integer), mode, brief, classification, allowed_use, budget_cents (positive integer), timeout_seconds (positive integer), expires_at, retention_until. Timestamps require explicit zones; persist in UTC. A reviewed brief is at most 8,000 characters, public-only, with allowed_use=internal_research. Length and self-declared classification are not evidence of disclosure permission: an authenticated owner must review the exact outgoing text.

Execution approval has approval_id, authenticated actor_id, digest and expiry. Digest is SHA-256 of UTF-8 canonical JSON for the entire request (sorted keys, compact separators, unescaped Unicode). The trusted service must derive actor identity and retrieve approvals from protected state, never accept an arbitrary approval object submitted by a caller. The offline fixture simulates these records; validators do not implement authentication.

Approval covers the exact brief, destination scope, classification, cost/time limits, retention and revision. Any change invalidates it. Actual production budget is undecided: the fixture's one-cent ceiling is synthetic and is not a provider cost estimate or live spending authorization. Before activation enforce per-run plus hourly/daily aggregate budgets and provider-side caps where supported; timeouts alone do not guarantee a remote billable operation was canceled. Retries consume the same reservation; ambiguous billed calls require reconciliation before repeating.

## 4. Identity, hourly deduplication and lifecycle

Logical request key is the digest of team_id + project_id + issue_id + request_id + revision + mode (same JSON encoding). Completed history prevents repeat execution on later ticks. A deliberate rerun creates a new request_id or revision and requires a new approval. Changes to a brief at the same request identity must be rejected as a conflict by the durable runner, not treated as an implicit new run.

Do not use issue:preset forever, delete job history to rerun, or use one-active-per-issue as the only dedupe rule. Serialize execution per issue, while retaining distinct approved revisions. Future webhook delivery identity is separate from subscription/webhook identity and logical request identity; verify the actual delivery identifier before implementing retries.

Future lifecycle: approved -> queued -> running -> report_ready -> expired, canceled or failed. All transitions are conditional/atomic. Provider retries are bounded, transient-only, within approval/retention/budget; do not retry auth/scope/permission denials. Lease recovery and dead-letter handling are required before unattended execution. Immediately before dispatch revalidate the approved brief digest, current issue scope, approval expiry, permissions and cost reservation. A changed or missing issue blocks the request.

## 5. Report and evidence contract

Each report binds request_digest, contract version, report ID/version, run ID, provider/API response metadata, timestamps, retention deadline and allowed_use. Contents: executive summary, claims, alternatives, risks/unknowns, next actions, sources. Each claim has stable ID, text, kind (fact/inference/recommendation/unknown), confidence, and evidence IDs. Each evidence reference has ID, direct URL, retrieval time, source/effective date if available, relevant passage or endpoint, limits and retention/rights context. Preserve uncertainty; unknown rights never become permission by model inference.

`validate_report` is a minimum linkage check, not complete schema validation, fact checking or proof of provider/source rights. The synthetic report deliberately contains no real research findings. External pages are evidence, never instructions to execute tools or disclose data.

One canonical marker: `<!-- sweet-seats:research-report -->`.
One canonical footer: `Advisory only. Not an approved decision until recorded in the Notion Decision Register.`
Future automation checks origin actor plus marker and request key to avoid loops. A marker or footer alone is not an enforcement mechanism.

## 6. Review and publication contract

Initial output is a saved report/review export; no Linear comment/ticket mutation is enabled. Execution approval does not authorize publication. Publication does not authorize architecture changes, licenses, code changes, purchases, model promotion or deployment.

Future publication approval binds authenticated actor, expiry, report version, exact workspace_id/issue_id and final UTF-8 body including marker/footer. Body content/formatting, target changes and truncation require reapproval. The publication digest is canonical JSON of target, body and contract version. Require single-use approvals, a durable outbox, receipt storage and ambiguous-write reconciliation before enabling a write adapter. If a response is lost after dispatch, mark uncertain and reconcile before retrying; do not promise exactly-once remote effects without provider support.

## 7. Persistence and entity mapping

No migration is applied or runnable DDL introduced. The earlier 0001 migration is withdrawn as a no-op because it conflated job and publication state. No pg_graphql or other extension is needed merely to call Linear's remote GraphQL API. Project hgxkoqzcqmujlvqiwbig association/dev/prod designation remains unverified in this work; no database was inspected.

Future research records are an internal-tooling extension of SS-DATA-0.1, not extra product observations. New record definitions below require reviewed migrations before deployment. Each uses an internal UUID, team/project scope, UTC audit timestamps, permission/retention references and no public user access. Reuse canonical Source/SourcePermission for provider identities/use evidence once implemented, rather than creating duplicate research_sources identities.

| Record | Purpose / fields | Relationships / constraints | Provenance / retention / unresolved |
|---|---|---|---|
| ResearchRequest | Approved immutable brief/revision, logical key, scope, limits, state | One request:N run attempts; unique logical key; immutable digest | Approval/decision evidence; explicit expiry/retention; actual owners/limits pending |
| ResearchRun | Attempt, lease owner/expiry, provider/correlation ID, costs, errors | Request 1:N runs; atomic claims; one active per issue | Adapter version and permission at dispatch; honor request retention; DB leases unimplemented |
| ResearchReport | Versioned content/hash, cutoff, allowed_use | Run 1:N report versions; no operational ingestion relationship | Claim-to-evidence mapping, restricted internal use; delete/expire with governing rights; report storage pending |
| ResearchEvidence | Source reference, URL, passage/endpoint, dates, limits | Report M:N evidence through explicit links; reuse Source/SourcePermission identities | Record origin, permission and effective dates; no indefinite payload copies; exact terms pending |
| ResearchApproval | Actor, kind, bound digest/target/report, expiry, consumption | Request/report 1:N approvals; execution and publication separate | Authenticated audit trail, expiry/revocation and minimum permitted tombstones; identity service pending |
| ResearchWriteback | Exact target/body, approval, delivery state, receipt | Report 1:N proposed deliveries; unique publication key, conditional state | No silent retries after uncertain results; retention covers body/receipt; adapter deferred |

Retain enough permitted non-content identity/tombstone state to prevent reruns after content expiry; determine actual duration before activation. Audit IDs must not retain prohibited content. Report expiry/revocation suppresses pending review/publication and propagates deletion to derived copies as required.

## 8. Implementation, validation and activation evidence

Runnable now (Python 3.11+, no dependencies):

```bash
python3 -m unittest discover -s tests -v
python3 -m jobs.linear_research --fixture tests/fixtures/research/hourly.json
python3 -m compileall -q adapters jobs services tests
```

These are offline contract checks and a synthetic selection plan. No live Linear/Perplexity, durable Postgres, real authentication, provider retry or delivery validation is claimed. Legacy network entry points fail closed, and the webhook module registers no HTTP route. Original branch behavior remains retrievable at 1f3071ee8f8442447eb2537f4c2d336dc782676b.

Activation requires a separate reviewed implementation: confirm workspace/team/project and database association; current provider API/terms; actual approved cost/retention limits; authenticated execution/review; durable jobs/budget ledger; source permission checks; provider cancellation/reconciliation; lease/restart/failure integration tests; then scheduler configuration. Publication additionally requires exact approvals and outbox receipt/reconciliation tests. No merge, deployment, paid call, production resource or live database change is part of this amendment.

First acceptance assignment: detailed-offer-provider comparison with coverage, seat/party-size and fee semantics, historical depth, access/cost, retention/derived/training/testing rights, termination effects and unresolved vendor questions. Discovery remains the first consumer release and does not wait for research automation.
