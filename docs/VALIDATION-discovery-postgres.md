# Local PostgreSQL discovery validation — 2026-10-18

Historical first-pass results below. The subsequent [dependency/API audit](API-dependency-audit.md) supersedes the dependency exception and records the follow-up changes.

Baseline: private upstream `main` at `da735d525e1ef3a27a6544e2a058b06782084b97`.
The connected GitHub API supplied a pinned source snapshot because unauthenticated
Git cloning could not access the private repository. No pre-existing local checkout
or uncommitted application work existed in this workspace. Work is on local branch
`feature/local-postgres-discovery`. The local snapshot's Git parent is not the upstream
commit object; use the delivered patch against upstream rather than merging that parent.
No push, merge, deployment, hosted migration, paid resource or live provider activation occurred.

## Implemented

- One pinned driver: `psycopg[binary]==3.2.13`; no ORM or frontend changes.
- Shared `ingest()` reconciliation and `project_feed()` projection; JSON remains an
  explicit legacy demo adapter. The local environment variable selects PostgreSQL.
- Transaction-scoped advisory writer lock, atomic relational writes, durable logical
  keys/digests and repeatable-read projection. No automatic schema creation at startup.
- Additive migration: source observations, observation credits, seed marker, match keys,
  replay digest and composite source/permission/run/event-mapping lineage constraints.
- Current source permission changes are read from SQL each time. Revocation, expiry,
  unknown grants, retention restrictions and blocked details remain fail-closed.
- Fixture validation now rejects known-start/local-date mismatch, silently reassigned
  typed mappings and duplicate source permission identities. The supplied NYC fixture
  itself was consistent and remains unchanged. First-seen timestamps retain eligible
  historical evidence when newer observations arrive.
- Existing list/detail, empty, failed, blocked, withheld and missing semantics retained.
- README, implementation contract, environment example and PostgreSQL 16 CI updated.

## Results actually run locally

| Check | Result |
| --- | --- |
| `SWEET_SEATS_TEST_DATABASE_URL=… python -m pytest services/api/tests -q` | 70 passed; zero skipped |
| `python -m unittest discover -s tests -q` | 56 passed; zero skipped |
| Ruff, compileall, `git diff --check` | Passed |
| SQL source-permission and foundation RLS tests | Passed |
| Additive discovery catalog contract | Passed |
| SQL deliberately broken negative controls | 12 caught; zero missed |
| Separate-interpreter API projection restart | Exact JSON parity |
| Actual PostgreSQL fast stop/start and reseed | Exact feed/provenance parity; IDs/counts/digests unchanged |
| Web `npm run typecheck`, `npm run lint`, `npm run build` | Passed; frontend source unchanged |
| Web `npm audit --omit=dev --audit-level=high` | Zero vulnerabilities |
| API resolved runtime dependency graph, `pip-audit` | No known vulnerabilities |
| Full web development dependency audit | Existing dev-only advisory remains; see below |

Acceptance includes four observations → three canonical events, six observation credits,
two-source provenance, exact JSON/PostgreSQL feed parity, unchanged replay state,
changed-content rejection, invalid-batch rollback, injected SQL failure after writes,
four simultaneous replay writers, new-process reads, server restart, direct SQL
permission changes, distinct API states, TBA, cancellation, postponement, historical
first-seen, contemporaneous conflict withholding and failed-collection freshness.
Both `anon` and `authenticated` were denied SELECT, INSERT, UPDATE and DELETE on all
three new tables with Supabase-style default grants in effect. Cross-source lineage
corruption was rejected by a real foreign-key constraint.

The test runner used PostgreSQL 16.15 Ubuntu binaries in a disposable loopback-only
cluster. This environment exposes only a root UID mapping, so a process-local identity
shim was needed for PostgreSQL's OS-user/ownership startup checks; no application,
SQL engine, RLS implementation or repository dependency was modified for that shim.
The committed CI uses the ordinary `postgres:16` service without it. GitHub CI has
not been run for these local amendments; local results are not remote CI evidence.

## Replay digest report

The seed CLI now emits provider-network-call count, canonical/observation counts and
source/logical-key SHA-256 digest reports. The fixture yielded:

| Logical key | Digest | Items |
| --- | --- | --- |
| `demo-artist-20261018` | `86190132a0a1852cd01d785b777c67a64cdccb7b31bb753ac91e068ee424be26` | 2 |
| `demo-venue-20261018` | `e1b3521f0cb0dc80c0f304a1ff9bbeafddb1fb4b8dbbb3c9c3a839b955622286` | 2 |

Re-seeding after the actual server restart retained these digests, three event UUIDs,
four source observation UUIDs and the existing provenance.

## Audit exception and limits

The pre-existing `braces` advisory GHSA-vfj7-8cjw-p6xm remains in the development-only
ESLint chain (`braces → micromatch → fast-glob → @next/eslint-plugin-next → eslint-config-next`).
The full npm audit reports five high-severity affected packages from that chain.
The suggested forced remedy is a breaking downgrade to `eslint-config-next@14.2.35`.
No dependency overrides or frontend framework changes were made. This is a clean
production dependency audit, not an all-dependencies-clean claim.

The API test run emitted an existing-stack Starlette/httpx deprecation warning.
The web build emitted existing CSS autoprefixer start/end compatibility warnings.
Neither prevented checks from passing.

Runtime Python audit used a freshly resolved, version-pinned transitive graph from
`services/api/pyproject.toml`; existing broad runtime ranges remain broad, so future
resolutions can differ. This change pins the new PostgreSQL driver only.

This is a small local synthetic adapter, not production-scale ingestion: full-state
reads, a global writer lock, dedicated database ownership and provisional field
precedence remain explicit limits. No user data, auth, retention deletion workflow,
backups, production recovery targets or live-provider rights are established here.
