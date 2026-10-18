# SS-DISCOVERY-DEMO-0.1 — local implementation contract

Scope: reversible synthetic development under the owner's 2026-10-18 instruction.
This is an implementation proposal, not a new approved Notion definition or production gate.
Traces to SS-DATA-0.1 and SS-ADR-002/003/004. Research remains isolated under SS-ADR-007.

The existing Next.js/TypeScript app calls the existing Python/FastAPI service.
The `.local/discovery.json` snapshot is a disposable local persistence adapter. It is
not an operational database, production store, or substitute for PostgreSQL. There is
no SQLite database, cloud storage, database driver, provider SDK, or new dependency.

## Contracts and PostgreSQL correspondence

| Development record | Intended PostgreSQL semantics |
| --- | --- |
| `identities.artists`, `identities.venues` | Internal UUID identities; names are attributes, never unique keys |
| Source `artist_mappings`, `venue_mappings`; `mappings` | Typed vendor-to-artist/venue/event mappings with real target validation |
| `sources[].permission` | Separate collect/display/raw retention/derived retention/feature/train/test decisions |
| `events` | Canonical internal event UUID and provisional match identity |
| `records` | Append-only source facts, source/permission/run lineage, source URL, observation/availability timestamps, adapter version and payload hash |
| Source-record performer credits | Many-to-many event/artist/role credits; deduplicated by artist UUID and role at read time |
| `runs` | Source + logical request identity; succeeded, empty, failed or skipped outcome |

These are contract correspondences, not a claim that a PostgreSQL schema was created,
validated or applied. The existing `supabase/migrations/202610130001_phase_1_foundation.sql`
remains an unapplied draft; it lacks a SourceEventRecord table and needs review before use.
The research withdrawal marker in `db/migrations/0001_research_jobs.sql` is unrelated.

## Synthetic ingestion

- The versioned fixture must be explicitly synthetic. Source identities are synthetic,
  first-party records. URLs must use reserved `.invalid` hosts without query credentials.
- Accept only declared record fields. Valid observations with unknown typed identities
  are retained in `unresolved` with a fixed reason, source identity, permission and run
  lineage. They create no canonical event or artist. Invalid observations still reject
  the transaction. There is no name matching. Existing crosswalk reassignment requires review.
- Check collection plus raw and derived retention before reading a batch into the store.
  Display permission is independent and checked again on every product read. Unknown,
  false, future approval, expiry and revocation all deny the relevant use.
- Matching requires reviewed canonical venue/artist mappings, exact known start time,
  and the same headliner set. Different known start times remain separate. Date-only
  records have explicit `time_tba` and do not auto-merge. Names/dates alone never match.
- An existing source/vendor event mapping preserves identity on postponement. Internal
  UUIDs use a deterministic demo namespace for reproducibility; vendors are represented
  separately in typed mappings. Production issuance/matching review remains a later gate.
- A source/logical-key replay is a no-op. Changed content at the same key is rejected.
  New observations require a new logical key. Source facts remain independently stored.
- Seed writes are single-writer and atomic via an exclusive lock and same-directory
  file replacement. No public ingestion endpoint exists. A crashed writer can leave a
  lock requiring operator inspection; this is not a durable queue or recovery system.

## Product read model

`GET /v1/events` returns mode, collection status, collection outcomes, generation time,
review count, unresolved summaries and event projections. It accepts `limit` (1–100,
default 100) and `offset` (nonnegative), returning total and next offset. Ordering is
local date, start timestamp, then UUID; TBA sorts first within its date. Offset pages
are for a single-writer demo snapshot, not a consistent multi-page production cursor.
`GET /v1/events/{UUID}` returns the same event with
its provenance. The Next.js loopback rewrite forwards `/api/discovery/*` to the local
FastAPI `/v1/*` paths. No provider credential is required or exposed.

Only currently permitted source records contribute to events and credits. Keep the
latest observation per source/vendor occurrence. The latest available observation
supplies provisional schedule/status fields; this is a demo rule, not approved source
precedence. Contemporaneous conflicting venue/start/date/status facts are preserved
but withheld for review. Canonical field-level source authority remains unresolved.

Freshness is computed from observation time, not fetch/render time. The synthetic
24-hour rule is labeled as a demo rule. A failed collection cannot refresh an event,
mark it sold out, or erase prior facts. A successful empty collection is distinct from
a failure. Missing/corrupt stores return 503; absent/withheld event details return 404.

Ticket URLs are null in this demo. Reserved source URLs are shown as provenance text,
not represented as real announcements. There are no live ticket links, follows, saved
events, authentication, user data, notification timers, prediction or purchase flows.

`local_date` must equal the start instant's date in `America/New_York`; TBA has a
date and null start time. Zoned instants cover DST without guessing a local clock
offset. `rescheduled` is a supported status; a known source event ID retains the
canonical UUID across date/status changes. Multiple exact-match candidates remain
unresolved with `ambiguous_event_match`, rather than picking one or aborting the batch.

The mobile feed displays performers, venue, local date/time, status and provenance,
with loading, empty, failure, partial and unresolved states. Search is page-local.
Six render tests use the existing React/TypeScript packages with Node's built-in
test runner. CI checks the client secret boundary after building in the same job.

## Run locally

From the repository root (Python 3.12+, Node 22+):

```bash
python -m venv .venv
.venv/bin/python -m pip install -e './services/api[dev]'
python -m services.api.app.discovery --fixture tests/fixtures/discovery/edge-cases.json
# Re-run unchanged: 3 events, 5 observations, 1 unresolved identity; zero provider calls.
.venv/bin/python -m uvicorn app.main:app --app-dir services/api --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd apps/web
npm ci
npm run dev
```

Open http://localhost:3000. The web proxy reads http://127.0.0.1:8000/v1/events.
Persistent development state is `.local/discovery.json` at the repository root.
The original `nyc.json` and the edge fixture are alternative synthetic datasets;
use a fresh `--store` path if switching between them (same-key changed content denies).
On Windows use `.venv\Scripts\python` instead of `.venv/bin/python`.

Inventory Status has a separate, always-disabled boundary in `app/inventory.py`
with no HTTP transport. Discovery credentials cannot activate it. MusicBrainz and
curated official sources remain planned. The existing Discovery adapter remains
disabled; this command ingests only explicit synthetic fixtures.

## Remaining gates

Reconcile the stale local checkout with remote main before any commit. Agree on the
single migration ledger and SourceEventRecord implementation. Add disposable local
PostgreSQL tests for real constraints, transactional replay and recovery, followed by
auth/RLS and cross-user denial tests before adding user data. Approve provider-specific
rights, field precedence, retention/deletion and production freshness thresholds before
live collection. Research reports cannot enter this fixture or normalization path.

