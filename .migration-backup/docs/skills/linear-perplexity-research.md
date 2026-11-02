# Linear + Perplexity research standard

Version SS-RESEARCH-0.2. Decision SS-ADR-007. This document replaces the earlier competing label/marker/approval/queue standards; earlier versions remain in Git history.

The single normative definition is [research-v0.2](../contracts/research-v0.2.md). This is a repository standard, not a claim that an agent skill is installed.

- Hourly candidate check; only research-quick / quick mode; one approved pending request per tick.
- Labels route work; authenticated exact-request approval authorizes it. No configured budget means no paid execution.
- Versioned request identity survives hourly ticks and completed runs. Reruns require a newly approved revision.
- Save cited reports for review; no automatic external publication.
- Canonical marker: `<!-- sweet-seats:research-report -->`.
- Execution and exact-target/body publication approvals are separate.
- Notion governs approved intent; Linear tracks execution only when configured.
- Internal research cannot directly feed product records or model inputs.
- No webhook/MCP activation, live DB migration or paid provider call in this slice.

See the contract for data fields, hashing, lifecycle, entity mapping, gates and runnable synthetic validation.
