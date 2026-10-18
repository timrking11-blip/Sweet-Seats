# Sweet Seats — dependency and API gap audit

Date: 2026-10-18. Scope: PostgreSQL discovery amendment based on upstream `da735d5`.
This is an implementation/security review, not approval to launch or activate providers.

## Resolved dependency findings

| Finding | Change | Verification |
| --- | --- | --- |
| Unpatched `braces` in Next's dev-only glob chain | Replace only the pinned Next lint plugin's directory glob dependency with a private, narrow `tinyglobby@0.2.17` adapter | Actual Next utility tested with string/array/brace/absolute/default/missing paths; directory filtering; Next rules retained; npm audit zero findings |
| Existing pytest `<9` range selects vulnerable 8.4.2 | Require pytest `>=9.0.3,<10`; dev lock resolves 9.1.1 | Full API and PostgreSQL suite passes; Python dev audit zero findings |
| Previously audited Python resolution was not reproducible | Add universal Python 3.12 runtime and dev hash locks; install locks before `--no-deps` editable API | Isolated environment installed from dev lock; runtime/dev scans zero findings |
| Web development audit was report-only | Make full npm audit block at low severity; retain production audit | Local full scan zero; CI enforces same command |
| Inherited `PGHOSTADDR` could redirect a localhost DSN | Pass an explicit loopback address to the driver | Regression test covers IPv4/IPv6 while nonlocal `PGHOSTADDR` is set |

No advisory ignore list, audit suppression, forced framework downgrade, disabled Next
rules or fake patched version is used. The private package named `fast-glob` is
explicitly documented as an application-owned compatibility adapter, not the upstream
package. Its implementation does not contain braces/micromatch. It rejects unsupported
calls and must be reviewed if the pinned Next plugin changes. Remove the adapter when
the upstream chain is fixed. Next 15.5.28, React 19.1.1 and TypeScript remain unchanged.

Primary references checked:
- https://github.com/advisories/GHSA-vfj7-8cjw-p6xm (no upstream patched braces release)
- https://docs.pytest.org/en/stable/announce/release-9.0.3.html
- https://pytest.org/en/latest/changelog.html (9.0.3 fixes CVE-2025-71176)
- https://github.com/SuperchupuDev/tinyglobby (glob API)
- Installed `@next/eslint-plugin-next@15.5.28/dist/utils/get-root-dirs.js` (sole glob call)

## Local acceptance and review

- 71 API/PostgreSQL tests passed, zero skipped, on the hash-locked isolated environment.
- 56 root unittest tests passed, zero skipped.
- Two Node compatibility tests passed; full web lint, typecheck and build passed.
- Full web audit reports zero vulnerabilities, including development dependencies.
- API runtime and development lock audits report no known vulnerabilities.
- Earlier SQL checks passed with all 12 deliberately broken negative controls caught.
- Earlier actual PostgreSQL server restart preserved exact feed/provenance/digest parity.
- `ruff`, compilation and diff whitespace checks passed.

The same author performed this code review; this is not an independent human approval.
Review examined transaction boundaries, failure redaction, current permission reads,
replay uniqueness, lineage, concurrent writers, synthetic/live boundaries and dependency
replacement behavior. The inherited-host override finding was fixed and regression-tested.
The dedicated database/full-state scan/global writer lock are acceptable local-slice
limits and are not production-scale design claims. The OS identity shim limitation of
local PostgreSQL tests is documented in the original validation report; GitHub CI uses
the ordinary PostgreSQL 16 container.

## Current API dependency inventory

| Capability | Present implementation | Dependency status |
| --- | --- | --- |
| HTTP routes and errors | FastAPI list/detail, permission-aware states | Present and locked |
| Request/model validation | Pydantic plus shared fixture validation | Present and locked |
| API server | Uvicorn with existing standard extras | Present and locked |
| Relational persistence | One psycopg driver, explicit local URL, transactions | Present; `psycopg[binary]==3.2.13` |
| API/integration tests | pytest, httpx, Ruff | Present; locked and audited |
| Provider HTTP | Ticketmaster adapter uses Python standard-library transport, limits, redaction, offline fixtures | No additional SDK required for its current contract |
| Synthetic reconciliation | Reviewed typed mappings and exact-occurrence matching | Present; no vendor dependency |

No missing Python package blocks the verified synthetic discovery increment. The next
blockers are integration contracts, permissions and operating behavior; installing
provider SDKs alone would not solve them.

## Remaining API work in order

| Priority | Missing or incomplete capability | Smallest implementation target | Dependency decision |
| --- | --- | --- | --- |
| P0 integration | Provider-to-database ingestion bridge | A separate rights-aware ingestion contract for approved provider observations; persist source/permission/run lineage and mapping review | Reuse current driver and transport first; synthetic-only `.invalid` URL checks must not simply be relaxed |
| P0 integration | Unknown/ambiguous identities | Review queue and persistent unresolved observations before real collection | Coordinate with open draft PR #13; its JSON-state additions need explicit PostgreSQL schema/adapter reconciliation |
| P0 provider gate | Live source permission/retention enforcement | Approved provider metadata, field/use scope, expiry/revocation and removal workflow | No new package needed; source registry/code alone do not establish rights |
| P1 discovery | MusicBrainz identity resolution | Fixture-tested resolver, typed mappings, ambiguity/review rules and permitted-field boundary | HTTP client can be reused or promoted from dev if justified; no SDK assumed necessary |
| P1 reliability | Scheduled collection and shared quota/retry state | Durable jobs, idempotency keys, shared budgets, bounded retry/backoff and collection outcomes | Choose scheduler/queue from actual runtime; do not connect the separate research job store to product ingestion by default |
| P1 delivery | Deployment connectivity and recovery | HTTPS API origin, separately scoped DB role, health/readiness, backups/restore exercise | Hosted database URL support is intentionally not part of the loopback-only adapter; approve a separate production adapter/configuration change |
| Before user records | Auth and authorization | Verify Supabase-issued identity on protected API paths, user ownership policies, cross-user negative tests | Choose JWT verification or supported Supabase client then; neither is required for the current synthetic read-only feed |
| Before public traffic | Bounds and operational visibility | Pagination/query bounds, request/body/time limits, shared rate limiting, structured redacted logs and monitoring | PR #13 has pagination work; assess pooling/tracing libraries after measurements, not by default |
| Later | Inventory, audience, geography, prices and notifications | Separate source-specific contracts and tests after access/rights approval | No Inventory Status, MusicBrainz, Soundcharts, Chartmetric, maps or notification SDK added by this PR |

An API key, successful request or installed client does not authorize source use.
Forecasting, price-history collection and user notification delivery remain separate gates.

## Concurrent PR and merge coordination

At inspection, draft PR #13 (`feat/fixture-feed-completion`, head `9f8bbcf`) targets the
same upstream base and changes reconciliation, API pagination and frontend states.
This PR does not overwrite, close or merge it. Before both are merged, reconcile the
shared discovery/API/README/workflow edits and extend PostgreSQL storage to preserve
any newly approved unresolved-identity state. A green CI run for either branch alone
is not evidence that their combined tree works. Run the combined-tree suite after
resolving the overlap. No independent reviewer was named or approval fabricated.

## Publication authorization

The initial publication attempt was blocked by automatic approval review before any
upload completed. On 2026-10-18 the owner explicitly authorized disclosing the reviewed
source changes to `timrking11-blip/Sweet-Seats`, opening a PR and running GitHub CI.
That authorization permits the retry. Publication/CI evidence belongs to the resulting
PR checks; local validation alone is not evidence of passing GitHub CI. No merge,
deployment, hosted migration or provider activation is included in this authorization.
