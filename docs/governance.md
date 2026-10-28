# Build governance

Sweet Seats follows the approved authority map.

| System | Authority | Build rule |
| --- | --- | --- |
| Notion | Product definitions, decisions, rights, metrics and acceptance criteria | A change in behavior must trace to an approved decision or be marked proposed. |
| GitHub | Executable code, migrations, tests and release evidence | Every change is tested and reviewed before merge. |
| Supabase PostgreSQL | Operational canonical records | The migration ledger is the only supported schema-change path. |
| Object storage | Permitted raw payloads, manifests and model artifacts | No raw provider payload is retained until its SourcePermission permits it. |

## Non-negotiable gates

1. Unknown source rights deny collection, storage, display, feature creation, training and evaluation.
2. Provider credentials remain server-side. They never enter the web bundle, fixtures or Git history.
3. A source record never silently becomes a canonical event; reconciliation preserves provenance and confidence.
4. Price or buy/wait advice stays disabled until the licensed-offer, historical-rights and evaluation gates are satisfied.
5. A multi-agent audit is evidence-led, not majority-led. Auditors can flag issues; the release gate passes only when code, tests, schema and documented decisions agree.

## AI auditor roles

| Role | Focus | Required evidence |
| --- | --- | --- |
| Architecture | Schema, boundaries, ADR traceability | Decision IDs, migration diff, contract tests |
| Source and rights | Provider terms and permitted use | SourcePermission record and terms version |
| Security and privacy | RLS, secrets, PII and isolation | Policy tests, secret scan, threat review |
| Product quality | User path, accessibility and honest labels | UI test or screenshot review, copy audit |
| Release | Final independent reconciliation | Passing checks, commit SHA, unresolved-risk list |

The proposed Claude Code agents for these roles, and the builder agents, are listed in
[agents.md](agents.md).

The build owner prepares the release evidence and makes the final merge recommendation. Production deployment, paid provider activation and public launch remain explicit owner approvals.

