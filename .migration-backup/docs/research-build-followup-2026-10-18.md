# Research-to-build follow-up - 2026-10-18

Traces to SS-ADR-002/003/004. This is implementation evidence and proposed follow-up,
not approval of new source rights or a replacement of the Notion decision register.

## Verified engineering baseline

The research review identified 18 proposed tasks. Read-only inspection found work
already covering several of them; the dated attachments must not be used to infer
that current development is still documentation-only.

- PR #14, head `814fce5737d7ae13056ea207eadf2714fbba2091`, has successful GitHub
  Actions run `39150271949`: API contracts, Web PWA, Database permissions and
  Research contract all succeeded. Its Python/runtime-development and full npm
  dependency audits passed. This is dated zero-known-advisory evidence, not a
  guarantee that vulnerabilities do not exist.
- PR #13, head `e986d7f585e9036070fef053b5e433279e0e7dbd`, has run
  `39150535050` concluded `action_required` at inspection. That conclusion is not
  a passing or a code-failure result. Its branch also overlaps discovery/API/CI
  paths; passing PR #14 does not validate a combined tree.
- PR #15 was a draft targeting the earlier PR #13 head, with zero changed files
  at inspection. Do not assume it already resolves current checks.
- The clean local PostgreSQL worktree at `ceff903` includes transactional storage,
  observation-level credits, replay digests, rollback/concurrency/restart evidence,
  current-permission projection and locked dependency scans. This follow-up uses
  an isolated worktree and does not modify the original branches.

References:
- https://github.com/timrking11-blip/Sweet-Seats/pull/14
- https://github.com/timrking11-blip/Sweet-Seats/actions/runs/39150271949
- https://github.com/timrking11-blip/Sweet-Seats/pull/13
- https://github.com/timrking11-blip/Sweet-Seats/actions/runs/39150535050

## Smallest implemented gap: cache reuse after a rights change

The backend rechecks permission on each read, and the existing client fetch uses
`cache: "no-store"`. The API itself previously omitted cache directives. The
consumer's fetch option is not a response policy for other clients or intermediaries.

The API now prevents storage of list/detail responses, including handled 404, 405,
422 and 503 errors. It sets private/no-store controls for browsers and shared caches.
Conditional requests still project current data and never return 304 for an older
allowed response. No dependency, framework, schema, provider or frontend change is
required.

Regression coverage first obtains permitted content, then revokes all source
permissions or advances the read clock exactly to expiry. Both the JSON and actual
PostgreSQL adapters must return a blocked empty list and a withheld-detail 404,
with cache controls on both success and denial. Permission-only revisions contain
no batches: immutable collected runs are not replayed as newly skipped payloads.

## Validation of this follow-up

- Hash-locked Python 3.12 development environment installed from the existing
  `services/api/requirements-dev.lock`; no dependency resolution change.
- `SWEET_SEATS_TEST_DATABASE_URL=<disposable loopback DSN> PYTHONPATH=services/api
  python -m pytest services/api/tests -q --tb=short`: **77 passed, zero skipped**.
  Includes PostgreSQL persistence, replay, rollback, current-permission and API tests.
- `python -m unittest discover -s tests -q`: **55 passed, one skipped** (56 total).
  The built-client secret check skips because this isolated worktree has no web build;
  no frontend files changed. The base PR's Web PWA build passed separately.
- Ruff, Python compilation and `git diff --check`: passed.
- Existing Starlette/httpx deprecation warning remains. No warning suppression added.

The local PostgreSQL 16.15 test engine uses the existing process-local OS identity
shim required by this root-only environment, as documented in the PostgreSQL
validation report. Tests use a fresh disposable cluster and per-test databases.
The server and tests run in the same tool network namespace. An earlier attempt
to connect from a separate isolated command failed before database acceptance;
the successful 77-test run used the shared namespace. No hosted database was used.

## Research backlog reconciliation

| Research task | Evidence/status after inspection | Next acceptance gap |
| --- | --- | --- |
| BUILD-01 baseline | Current PR heads and CI inspected | Combined-tree validation after overlap resolution |
| BUILD-02 entitlements | Existing per-use source checks | Live field scope, inference and external-AI disclosure entitlements |
| BUILD-03 lifecycle | Read-time suppression exists; HTTP caching now addressed | Retention deletion/quarantine, descendants, cache invalidation and restored backups |
| BUILD-04 persistence | Covered by PR #14 and 77-test local acceptance | Preserve PR #13 unresolved state when reconciling branches |
| BUILD-05 collection | Offline Ticketmaster transport contract exists | Authorized provider-to-database bridge, complete paging, durable quotas |
| BUILD-06 time/identity | Existing tests and overlapping PR #13 | Combined PostgreSQL unresolved-review state; explicit field authority |
| BUILD-07 delivery | No product delivery active | Transactional outbox, consent-at-send, timeout reconciliation and recovery |
| BUILD-08 isolation/recovery | Local RLS and failure tests exist | User scope, hosted environment ownership and actual backup restoration |
| BUILD-09 source experiment | Protocol prepared | Approved sources, frozen roster and matched observations |
| BUILD-10 offer RFI | Questionnaire prepared; not sent | Vendor response, entitled samples and applicable written rights |
| BUILD-11 order prices | Deferred | All-in party-size eligibility and versioned cohorts |
| BUILD-12 pricing pilot | Proposed protocol only | Rights-cleared observations and powered forward holdout |
| BUILD-13 identity access | Core/hosted distinction documented | Owner-selected access method and permitted-field resolver |
| BUILD-14 travel | No transit adapter active | Service area, PATH/NJ Transit/MTA rights and route semantics |
| BUILD-15 mobile beta | Synthetic feed exists; PR #13 adds render states | Actual device/hydration behavior, follows and consented user actions |
| BUILD-16 dependency audit | PR #14 audit gates passed | Check exact combined/follow-up head; maintain dated advisory evidence |
| BUILD-17 competition | Corrected primary-source feature evidence | Dated consumer workflow, eligibility and pricing walkthrough |
| BUILD-18 costs | Workload arithmetic and partial price anchors documented | Real listing/page volumes, service sizing and vendor quotes |

## Remaining lifecycle boundary

No-store cannot erase an already rendered tab, user screenshot or previously saved
response. The current UI retains data until a subsequent fetch. Before a live-source
beta, define a maximum permitted display/revalidation interval and fail-closed client
behavior when that interval or source permission expires. Validate any proxy/CDN/service
worker behavior in the actual deployment.

Suppression is also not deletion. Observation payloads, derived canonical columns,
mapping tables, source metadata, backups and later feature/model artifacts need a
rights-aware retention policy and lineage-driven cleanup. Avoid a generic purge
that silently deletes shared identities or preserves forbidden derived facts.

Next recommended implementation is branch reconciliation plus a bounded durable
product-collection contract; live activation remains gated by source terms. A
research-agent queue must not silently become the product ingestion queue.
