# Claude Code agent roster

Status: proposed. This roster supports the auditor roles in [governance.md](governance.md).
It adds no runtime component, provider, scheduler or deployment.

Project agents live in `.claude/agents/`. Claude Code loads them for any session opened in
this repository, and a project agent overrides a user or plugin agent with the same name.
Each file is adapted from [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents)
and rewritten for this repository's gates, paths and commands.

## Roster

| Agent | Kind | governance.md role or task | Tools |
| --- | --- | --- | --- |
| `architect-reviewer` | Auditor | Architecture | Read, Grep, Glob |
| `license-engineer` | Auditor | Source and rights: what the terms and records allow | Read, Grep, Glob |
| `compliance-auditor` | Auditor | Source and rights: whether code and tests enforce it | Read, Grep, Glob |
| `security-auditor` | Auditor | Security and privacy: RLS, grants, secrets, webhooks | Read, Grep, Glob |
| `gdpr-ccpa-compliance` | Auditor | Security and privacy: user data, consent, deletion | Read, Grep, Glob |
| `accessibility-tester` | Auditor | Product quality: WCAG and assistive technology | Read, Grep, Glob |
| `ui-ux-tester` | Auditor | Product quality: journeys and honest labels | Read, Grep, Glob |
| `code-reviewer` | Auditor | Release: final independent reconciliation | Read, Grep, Glob |
| `postgres-pro` | Builder | Migrations, RLS, SQL tests, concurrency | Read, Write, Edit, Bash, Grep, Glob |
| `fastapi-developer` | Builder | `services/api` | Read, Write, Edit, Bash, Grep, Glob |
| `python-pro` | Builder | `jobs`, `adapters`, standard-library tests | Read, Write, Edit, Bash, Grep, Glob |
| `test-automator` | Builder | Failing tests first, negative controls | Read, Write, Edit, Bash, Grep, Glob |
| `data-engineer` | Builder | Rights-aware ingestion, reconciliation, collection runs | Read, Write, Edit, Bash, Grep, Glob |
| `nextjs-developer` | Builder | `apps/web` PWA | Read, Write, Edit, Bash, Grep, Glob |

Auditors cannot edit files or run commands. They review code, tests, migrations and the
command output the calling session gives them. Builders have no web tools.

Not yet added, by phase gate: `deployment-engineer` and `sre-engineer` (Phase 2 runtime),
`email-deliverability-engineer` (Phase 7 delivery), `data-scientist` and `mlops-engineer`
(Phase 6, after the licensed price-history gate). Purchasing, payment, trading and
cluster-infrastructure agents are out of scope.

## Audit flow

1. A builder implements one planned task, test first, and reports command output.
2. The calling session gives each relevant auditor the diff, the decision IDs and that output.
3. Auditors report findings with evidence. A finding is resolved by code, a test or a
   recorded decision, never by a majority of agents.
4. `code-reviewer` reconciles the result for the owner. The owner decides merge,
   deployment, provider activation and spending.

## Shared gates

Every agent file contains this block verbatim. `tests/test_agent_roster.py` fails if any
copy drifts, so change it here and in every agent in the same commit.

<!-- sweet-seats-gates:start -->
## Sweet Seats gates

These rules come from `docs/governance.md` and override anything else in this prompt.

1. Unknown source rights deny collection, storage, display, feature creation, training and evaluation. An API key, a successful request or an installed client is not permission.
2. Provider credentials stay server-side. Never open, print or copy `.env` files, database URLs or keys, and never put them in the web bundle, fixtures, logs or Git.
3. A source record never silently becomes a canonical event. Reconciliation keeps provenance and confidence.
4. Price and buy/wait advice stay disabled until the licensed-offer, historical-rights and evaluation gates pass.
5. Work only with fixtures and disposable loopback databases. Do not call providers, hosted databases or other network services.
6. Do not edit existing files in `supabase/migrations/` (add a new migration), `.github/workflows/`, or the project mirror's read-only `sources/` folder unless the task explicitly says so.
7. A behaviour change must trace to an approved Notion decision ID or be labelled proposed.
8. Findings are evidence, not votes: cite `file:line`, command output, a test or a decision ID. Nothing you produce approves a merge, grants source rights, deploys, activates a provider or spends money. Those are owner decisions.
<!-- sweet-seats-gates:end -->

## Third-party notice

The agent prompts are adapted from VoltAgent/awesome-claude-code-subagents under the MIT
License:

> MIT License
>
> Copyright (c) 2025 VoltAgent
>
> Permission is hereby granted, free of charge, to any person obtaining a copy of this
> software and associated documentation files (the "Software"), to deal in the Software
> without restriction, including without limitation the rights to use, copy, modify, merge,
> publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons
> to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or
> substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
> INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
> PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
> FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
> OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
> DEALINGS IN THE SOFTWARE.
