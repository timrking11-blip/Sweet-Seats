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
- Accept only declared record fields. Unknown identifiers are rejected; no name matching.
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
review count, and event projections. `GET /v1/events/{UUID}` returns the same event with
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

## Remaining gates

Reconcile the stale local checkout with remote main before any commit. Agree on the
single migration ledger and SourceEventRecord implementation. Add disposable local
PostgreSQL tests for real constraints, transactional replay and recovery, followed by
auth/RLS and cross-user denial tests before adding user data. Approve provider-specific
rights, field precedence, retention/deletion and production freshness thresholds before
live collection. Research reports cannot enter this fixture or normalization path.
