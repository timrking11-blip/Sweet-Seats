# Fixture-to-feed increment — validation, 18 October 2026

Base inspected: private `main` at `da735d525e1ef3a27a6544e2a058b06782084b97`.
Reference attachments were treated as dated design context. Current repository source
and tests govern implementation facts. No open issues or PRs were returned at inspection.
The `copilot/run-picard-script-options` branch points to historical merge `633309d`;
the inspected main tree contains no `run_picard.py`. No separate agent-session transcript
was available; branch names do not establish delivered code. PRs #3–7, #10–12 already
contain the fixture foundation, conflict handling, disabled Discovery adapter and
release fixes. This change extends those capabilities instead of rebuilding them.

| Check | Actual local result |
| --- | --- |
| `python -m unittest discover -s tests -q` | 65 passed, zero skipped, including post-build client-bundle boundary |
| `.venv/bin/python -m pytest -q services/api/tests` | 42 passed; upstream Starlette/httpx deprecation warning |
| `.venv/bin/ruff check services/api` | Passed with Ruff 0.8.6 (within existing supported range). Latest downloaded executable was truncated/unusable locally; repository dependency ranges unchanged. |
| `python -m compileall -q adapters jobs services tests` | Passed |
| `npm test` in `apps/web` | 6 rendered-state tests passed using Node/React/TypeScript; no new package |
| `npm run typecheck`, `npm run lint` | Passed |
| `npm run build` | Passed on Next.js 15.5.28. Initial uncached build reported existing CSS alignment compatibility warnings. |
| `npm audit --omit=dev --audit-level=high` | Zero production vulnerabilities |
| Edge fixture ingestion twice | Both: 3 canonical events, 5 source observations, 1 unresolved identity, zero provider calls; exact persistent-state replay also tested |
| Local integrated read | Started API and production web locally; read persisted events through `/api/discovery/events`, then rendered the actual `DiscoveryFeedView` from that response: 3 cards, rescheduled status and unresolved review shown |
| Interactive browser / phone viewport | Not completed: Chromium absent and browser download returned truncated archives. HTTP and React render evidence do not establish hydration, visual layout, keyboard navigation or device behavior. |
| PostgreSQL/RLS | Not rerun locally; no schema changes. Existing disposable CI database job remains enabled. No remote migration applied. |

Tests cover invalid observations, identifier reconciliation, same-name/different-ID
artists, ambiguous occurrence review, reviewed crosswalk protection, atomic rejection,
duplicate prevention, reopen/replay, DST/date agreement, TBA, cancellation/rescheduling,
permission-filtered unresolved summaries, pagination and feed loading/error/empty/
partial/blocked states. Inventory boundary is disabled and has no transport.

Limitations: the existing JSON store is single-writer development persistence;
PostgreSQL source-observation schema, transactional recovery and production read model
remain future work. No MusicBrainz adapter, live collection, audience integration,
maps, pricing, notifications, deployment, paid resource or production release is included.

Next smallest production-oriented increment: define and test the PostgreSQL
SourceEventRecord/unresolved-review persistence adapter against the existing source,
permission and canonical tables, using disposable local/CI PostgreSQL. Verify replay,
failure rollback and permission-filtered projections before applying remote migrations.
