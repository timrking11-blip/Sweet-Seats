# SS-RESEARCH-0.3: Claude research provider amendment

Decision: proposed amendment to SS-ADR-007. Owner: Timothy King. Status: **proposed, not approved**. It takes effect only when recorded in the [Notion decision register](https://app.notion.com/p/3f57ecee36a98119aff6f8b3496376f6). Until then [SS-RESEARCH-0.2](research-v0.2.md) governs. Production activation stays blocked.

This amendment replaces the research provider. It does not rewrite the workflow. Everything in SS-RESEARCH-0.2 still applies unless a section below changes it: authority and isolation, the hourly candidate contract, request identity, approvals, deduplication, lifecycle, the evidence model, review export and publication, persistence and activation gates.

## 1. Scope

In scope:

- Claude replaces Perplexity as the internal research processor.
- The approval binds an execution profile.
- The budget covers the whole Claude execution.
- Claude responses are normalized and fully validated.
- Offline: synthetic request, approval, budget reservation, mocked Claude response, evidence validation and saved review export.

Deferred:

- Webhook receiver. A webhook speeds up request arrival but does not solve execution durability or authorization. `LINEAR_WEBHOOK_SECRET` is added with the receiver, not before.
- Deep mode and precedence between competing labels. With quick-only scope, precedence is unnecessary. If modes are added later, ambiguous labels block selection unless the approved request resolves the mode.
- Publication and Linear writeback.
- A general multi-provider framework.

Out of scope: Perplexity Computer and consumer Perplexity conversations are outside this workflow. Their integration is not carried forward.

## 2. Execution interface

| Interface | Role |
|---|---|
| Claude API (Messages API with server-side `web_search` and `web_fetch` tools) | Backend research execution. Requests, tool use and costs are recorded. This is the only interface the runner uses. |
| Claude Code | Implementing and testing the integration. Running it as an operator workflow would need its own separate governance; it is not covered here. |
| Claude chat | Manual exploration. Its output enters the project only as a reviewed external contribution (section 7). |

Changing the model provider alone does not give the runner web research. The profile has to declare the web tools explicitly. Fetch citations are enabled explicitly on the fetch tool. The research role gets only `web_search` and `web_fetch`. It has no tool that could approve its own findings, change source permissions, merge code, publish or activate integrations. This holds even when Claude is also the coding assistant on the repository.

## 3. Execution profile

An execution profile is an immutable, closed-field JSON object. It sets:

- provider and interface (`anthropic`, `claude_api`)
- model and effort
- tool types and versions, `max_uses`, domain controls, fetch citations and `max_content_tokens`
- prompt version
- `max_tokens` and permitted `pause_turn` continuations
- SDK `max_retries`, which must be 0
- a pricing snapshot with its verification date

Its identity is the SHA-256 profile digest, using the SS-RESEARCH-0.2 canonical JSON encoding.

The request adds one field, `execution_profile_digest`, and its version becomes `SS-RESEARCH-0.3`. The approval digest covers the whole request, so it binds the profile digest too. Changing the provider, model, tool set or tool version, limits, prompt version or pricing changes the profile digest. That invalidates the approval, and a new approval is required. A profile must also be registered in protected policy (`approved_profiles`) before a request can use it.

Historical Perplexity records keep their original provenance (`provider: perplexity`, contract SS-RESEARCH-0.2). They are not relabelled or migrated.

## 4. Budget

A reservation must cover the worst case of the whole request:

- model input and output tokens across every permitted continuation
- web search uses
- fetched content (`max_uses` × `max_content_tokens`)
- an explicit assumed prompt size and per-search result size

Runner retries reuse the same reservation and never create a new one.

Provider-side limits complement the application ledger and do not replace it. The provider-side limits are `max_uses`, `max_content_tokens`, `max_tokens` and the continuation limit.

The ledger enforces three limits: the request's own `budget_cents`, an hourly aggregate and a daily aggregate.

After each run, the actual cost comes from `usage`. That includes input, output and cache tokens, and `server_tool_use.web_search_requests`. The actual cost is persisted and settled against the reservation. A run that ends without a usage record leaves the charge unresolved. Further execution of that request is blocked until a person reconciles it.

The SDK retries by default. Automatic retries could repeat a billable call outside the reservation, so the profile requires `max_retries: 0`. The runner owns every retry.

The pricing snapshot in the synthetic profile is unverified and is not a spending authorization. The actual budget is still undecided.

## 5. Response normalization and validation

Claude output goes through four stages.

1. **Normalization.** Evidence comes from this run's `web_search_tool_result` and `web_fetch_tool_result` blocks, not from URLs the model asserts. Text citations attach cited passages to that evidence. Claims, alternatives, risks and next actions come from the final JSON report the prompt asks for. A claim that cites a URL not retrieved in this run is rejected. Tool error results are recorded as errors, never as evidence.
2. **Complete schema validation.** Field sets are closed, and enumerations and identities are checked. Confidence must be low, medium or high, and unknown claims must be low. Every evidence `rights_context` is `unverified`; the normalizer cannot set anything else. Run validation also checks continuation and stop-reason limits.
3. **SS-RESEARCH-0.2 `validate_report`.** This remains the minimum linkage check.
4. **Human evidence review.** The export is saved as `pending_human_review`, and every claim is marked unverified.

Validation does not prove that:

- a source supports the claim,
- confidence is justified,
- the source grants retention or reuse rights.

Citations are evidence pointers, not verification.

## 6. Identity and deduplication

Unique constraints were not the mistake. The mistake was using "one active job per issue" as the entire deduplication model. The durable runner keeps database uniqueness for:

- logical request identity
- attempt identity
- reservation identity
- future publication identity

Each identity stays separate from the others.

## 7. Manually launched tools

A person pressing Enter does not remove disclosure, spending or replay concerns.

- **Repository research commands:** a repository command that calls a paid research provider uses the same approved request, budget accounting and provenance requirements whether a person or a scheduler launches it. There is no blanket exemption for human-operated CLIs.
- **Independent manual research** (for example Claude chat): may stay outside the runner. It enters the project as an explicitly reviewed external contribution. It cannot create an execution approval and is never published automatically.

## 8. Status of earlier alternatives

PR #1's scaffold and the original PR #2 worker are **superseded**. Webhooks, deep mode, MCP and publication are **deferred**, not rejected. "Rejected" is reserved for alternatives a recorded decision explicitly rejects.

## 9. Implementation evidence

Runnable offline, with Python 3.11+ and no dependencies:

```bash
python -m unittest discover -s tests -v
python -m jobs.research_pipeline --fixture tests/fixtures/research/claude-v0.3.json --export-dir .local/research-export
```

What the offline run covers:

- the approval store and its single-use execution approvals
- the in-memory budget ledger
- normalization of mocked Claude messages, including a `pause_turn` continuation
- full validation
- the saved JSON and Markdown review export

`adapters/claude_research.py` builds Messages API parameters but refuses execution, so it makes no network calls.

What the offline run does not cover:

- real authentication
- durable PostgreSQL state
- a live Claude call
- verified pricing
- a scheduler
- publication

Next, after this amendment is approved:

1. A separately authorized, bounded live evaluation, with the detailed-offer-provider comparison as its acceptance assignment.
2. The durable runner.

All other SS-RESEARCH-0.2 section 8 activation gates still apply.
