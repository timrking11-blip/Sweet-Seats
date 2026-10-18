# SS-DISCOVERY-DEMO-0.1 — local implementation contract

Scope: reversible synthetic development under the owner's 2026-10-18 instruction.
This is an implementation proposal, not a new approved Notion definition or production gate.
Traces to SS-DATA-0.1 and SS-ADR-002/003/004. Research remains isolated under SS-ADR-007.

The existing Next.js/TypeScript app calls the existing Python/FastAPI service.
The local adapter uses `psycopg[binary]==3.2.13` and PostgreSQL 16.
`SWEET_SEATS_LOCAL_DATABASE_URL` selects it explicitly; only loopback hosts are accepted.
There is no schema creation/migration on application startup. Configured database
failures produce 503, never fallback. Without the variable, `.local/discovery.json`
remains a legacy demo adapter. `ingest()` and `project_feed()` are shared storage-independent
functions; neither depends on the database driver.

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

The foundation migration remains unchanged. The additive
`supabase/migrations/20261018170819_discovery_observations.sql` creates
`source_event_records`, `source_event_performers` and a singleton seed marker;
adds replay digests, event match keys and synthetic source configuration; and adds
composite FKs enforcing observation → source/permission/run/event-mapping lineage.
An observation's permission must equal its run's permission. Typed artist/venue/event
mappings are persisted. Current grants are read from `source_permissions` on every read.
PostgreSQL is the store, not a mirror of a JSON snapshot. The research ledger is unchanged.

Observation timestamps retain zoned ISO source strings for exact API parity; SQL
checks their ordering and shared normalization rejects naive times. Collection timestamps
render in UTC. Observation credits are projected after permission checks; the canonical
`event_performers` table is not populated with an unconditional union. Canonical schedule
columns are provisional cached facts; API reads always reproject eligible observations.
Migrations were tested only on disposable local PostgreSQL; no remote schema was changed.

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
- PostgreSQL seed writes validate the fixture and persist all rows in one transaction.
  A transaction-scoped advisory lock serializes writers across processes; unique
  source/logical keys and SHA-256 digests provide durable replay checks. Database failures
  roll back all writes. Reads use one repeatable-read transaction. The seed marker
  distinguishes an unseeded database from a successfully empty collection.
- The legacy JSON adapter retains its exclusive lock and atomic file replacement.
- Known starts must agree with the NYC local date. Existing typed vendor mapping
  targets cannot be silently reassigned; identity amendments require separate review.
- No ingestion endpoint, durable queue or production recovery system is introduced.

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

The implementation baseline is upstream `da735d5`; this amendment is local work.
`supabase/migrations` is the discovery schema ledger. CI must pass disposable
PostgreSQL 16 acceptance, permission/RLS and negative-control checks before integration.
User auth and cross-user denial tests precede adding user data. Approve provider-specific
rights, field precedence, retention/deletion and production freshness before live collection.
Research reports cannot enter this fixture or normalization path.
