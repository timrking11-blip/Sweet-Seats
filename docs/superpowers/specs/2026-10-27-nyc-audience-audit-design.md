# NYC audience observations and audit — design (SS-AUDIENCE-0.1)

Status: **design for review**, 27 October 2026. Base: `main` at `710003c`.
Owner: Timothy King. Scope: specification only; implementation follows review of this document.

This is an implementation proposal under SS-DATA-0.1 and SS-ADR-002/003/004. It is not an
approved Notion definition, a provider selection, a SourcePermission or an activation. It
uses synthetic fixtures only. No provider is integrated, called or paid for.

## 1. Purpose and scope

Sweet Seats needs a defensible measure of how popular an artist is **in New York**. It is
the first demand input to the later price-forecast work, and each forecast driver must be
traceable to evidence. This increment builds the storage contract for that evidence and a
deterministic audit that proves which readings are usable, plus an advisory auditor agent
that explains the audit.

In scope:

- A provider-neutral **audience observation** contract, schema and synthetic ingest.
- A **geography contract** shared by audience data and, later, location services.
- The NYC beta **event catchment** and the tracked-artist priority rule.
- The `audience-audit` v0.1 rule engine, its verified result ledger and the feature-read gate.
- An advisory **auditor agent** role with read-only database access.
- Retention: read denial, batched purge and cleanup of derived artifacts.

Out of scope (separate sub-projects, each with its own spec): vendor adapters
(Soundcharts, Chartmetric, Viberate), scheduling, user follows, Google Routes travel time,
and the price forecast with evidence claims.

### Sub-project order

1. NYC audience observations and audit (this document).
2. User-to-venue travel reachability through Google Routes, server-side only.
3. Price forecast with economically decomposed evidence claims, gated on a licensed
   offer source (governance gate 4).

## 2. Three geography facts

Each fact has its own source, contract and provenance. None is inferred from another.

| Fact | Meaning | Owner |
| --- | --- | --- |
| Audience geography | Where a vendor reports listeners or followers | This spec |
| Venue location | Where a venue is (existing `venues` coordinates plus a reviewed geography mapping) | This spec (mapping only) |
| Travel reachability | How long a user takes to reach a venue | Sub-project 2 |

A vendor's "New York" label establishes neither metro coverage nor concert reachability.

### 2.1 Geography contract

- `geographies`: canonical areas. Columns: `geography_id`, `slug`, `kind`
  (`city`, `county`, `metro`, `catchment`), `definition_version`, `definition_text`,
  `components` (for unions), `created_at`. Rows are immutable; a change is a new version.
- `geography_mapping_versions`: immutable links from a vendor location to a canonical area.
  Columns: `mapping_version_id`, `source_id`, `vendor_location_id` (nullable),
  `vendor_location_label` (raw), `geography_id` (nullable: unresolved is allowed),
  `version`, `review_status` (`unreviewed`, `reviewed`, `rejected`), `reviewed_by`,
  `reviewed_at`, `evidence_note`, `supersedes_mapping_version_id`.
- `venue_geography_versions`: immutable reviewed links from a venue to a canonical area,
  with the same review, provenance and version columns.

Resolving or changing a mapping inserts a new version. Observations, audits and snapshots
reference the exact version they used, so later resolution never rewrites history.

### 2.2 Canonical areas for v1

| Slug | Version | Definition |
| --- | --- | --- |
| `nyc_city` | 1 | The five boroughs: Bronx, Brooklyn (Kings), Manhattan (New York), Queens and Staten Island (Richmond) counties |
| `hudson_county_nj` | 1 | Hudson County, New Jersey, explicitly including Jersey City and Hoboken |
| `nyc-beta-catchment` | 1 | Union of `nyc_city` v1 and `hudson_county_nj` v1 |
| `nyc_metro` | 1 | Placeholder for vendor-reported metro areas; never counted as `nyc_city` |

`nyc-beta-catchment` is the **event** catchment. The eligible **audience** geography for
v1 is `nyc_city`. They are deliberately different and are never substituted for each other.

## 3. Artist identity mapping

`source_entity_mappings` (base schema) holds one mutable row per vendor ID and has no
review fields. This increment adds `artist_mapping_versions`: immutable rows with
`mapping_version_id`, `mapping_id` (FK), `source_id`, `vendor_artist_id`, `artist_id`,
`version`, `review_status`, `reviewed_by`, `reviewed_at`, `evidence_note` and
`supersedes_mapping_version_id`. Names are never identity keys.

Ordinary `CHECK` constraints cannot read another row, so eligibility is enforced in two
layers: composite foreign keys for identity and source consistency, and the controlled
ingest function plus a trigger that rejects a mapping version unless it is `reviewed` and
belongs to the observation's source.

## 4. Audience observation contract

### 4.1 `audience_observations`

One row per reading revision. Rows are append-only within the permitted retention period.

| Group | Columns | Rules |
| --- | --- | --- |
| Identity | `observation_id`, `observation_key`, `revision`, `content_hash` | Unique `(observation_key, revision)`; see 4.2 |
| Artist | `artist_id`, `artist_mapping_version_id`, `vendor_artist_id` | Mapping version must be reviewed and from the same source |
| Metric | `metric_definition_id` → `platform`, `metric_key`, `unit`, `window_kind` (`rolling`, `point`), `window_days`, `definition_version`, `expected_cadence` (nullable), `period_timezone` (IANA name or `unknown`), `jump_abs_floor` | Definitions are immutable versioned rows |
| Geography | `vendor_location_id` (nullable), `vendor_location_label`, `geography_mapping_version_id` (nullable) | Raw vendor values are always kept |
| Value | `value` (numeric ≥ 0, nullable), `missing_reason` | `missing_reason` in (`not_reported`, `outside_top_locations`, `provider_error`) is required exactly when `value` is null; zero is a real zero |
| Method | `measurement_method` (`measured`, `estimated`, `unknown`), `imputation_status` (`not_imputed`, `imputed`, `unknown`) | Both default to `unknown`; `not_imputed` only with evidence |
| Period | `measured_from`, `measured_to` (dates in `period_timezone`) | `measured_from ≤ measured_to` |
| Time | `provider_published_at` (nullable), `retrieved_at`, `ingested_at` | See 4.3 |
| Publication | `publication_id` (nullable until published), `published_at` | Assigned only by the publish function |
| Lineage | `source_id`, `collection_run_id`, `permission_id`, `payload_hash`, `corrects_observation_id` | Source, run and permission must agree |

Raw provider payloads are never stored; only `payload_hash` is kept.

### 4.2 Replay and correction identity

A **reading** is one value for one series and one measured period. Its revisions are
the original value and every later correction of it.

- `observation_key` identifies the reading, not a revision. The collector derives it
  from the source, vendor artist, metric definition, vendor location, `measured_from`
  and `measured_to`. Every revision of a reading shares the same `observation_key`.
- `revision` is assigned by the ingest function, never by the collector. The first
  accepted value is revision 1. Each correction is the current head's revision plus 1.
  `(observation_key, revision)` is unique.
- `content_hash` covers the value, `missing_reason`, method, imputation and time fields
  of one revision.

Ingest decides under a transaction-level advisory lock on `observation_key`, so
concurrent writers of the same reading serialize:

| Incoming row | Existing revisions of the key | Result |
| --- | --- | --- |
| Any | None | Accepted as revision 1 |
| `content_hash` equals any existing revision | Any | No-op (replay of that revision) |
| New `content_hash`, no correction target | One or more | Rejected: `changed_content_at_same_key` |
| New `content_hash`, `corrects_observation_id` = current head, head published | One or more | Accepted as head revision + 1 |
| New `content_hash`, target is not the head | One or more | Rejected: `correction_target_not_head` |
| New `content_hash`, head not yet published | One or more | Rejected: `correction_target_unpublished` |
| Target belongs to a different `observation_key` | Any | Rejected: `cross_reading_correction` |

So when the source, artist, metric, location and measured period are all unchanged, the
key stays the same and only the revision moves. Each revision has its own
`observation_id`. The collector cannot choose a revision number, skip one or fork a
chain. `corrects_observation_id` is unique and must name the head of the same key, so
chains are linear and cannot branch or loop.

A different measured period, metric definition, vendor location or vendor artist is a
different reading with a new key, never a correction.

The **effective** reading of a key at a watermark is its highest revision with
`publication_id ≤ watermark`. Audit inputs and feature eligibility always name the exact
`(observation_key, revision, content_hash)`.

### 4.3 Timestamp semantics

| Column | Meaning |
| --- | --- |
| `measured_from`, `measured_to` | Calendar dates the value describes, in `period_timezone` |
| `provider_published_at` | When the vendor says it published the value; null means unknown |
| `retrieved_at` | When the collector received the response |
| `ingested_at` | Transaction start of the ingest (server default); informational only |
| `published_at` | Statement time stamped by the publish function; informational only |

Neither `ingested_at` nor `published_at` is a commit time. **The authoritative as-of
boundary is the publication watermark (4.4).** When `period_timezone` is `unknown`, the
value stays unknown. UTC may be used only as an explicitly labeled computational
assumption and is never recorded as a provider fact.

### 4.4 Publication and snapshots

- Ingest writes rows with `publication_id` null. Unpublished rows are invisible to every
  read, audit and snapshot.
- `audience_publish_run(run_id)` takes an exclusive transaction-level advisory lock.
  Under the lock it rechecks the permission (`collect`, `derived_retention`) and the
  mapping eligibility of every row, then assigns a `publication_id` from a sequence.
  IDs increase monotonically because only one publish holds the lock at a time.
- Permission revocation and mapping-version changes go through functions that take the
  same exclusive lock, so they serialize with publication.
- `audience_take_snapshot()` runs at read-committed isolation. One statement acquires
  the shared lock; the next statement reads the highest committed `publication_id` and so
  sees every commit completed before the lock was granted. It stores an immutable
  `audience_snapshots` row: `snapshot_id`, `requested_at`, `watermark`.
- A snapshot's contents are the effective readings with `publication_id ≤ watermark`.
  Rebuilds always use the stored watermark. **`requested_at` is the time of the request,
  not an exact historical availability cutoff.**

## 5. Permissions

The existing `source_permissions` uses stay as they are. This increment adds
`internal_audit_allowed boolean not null default false` (deny by default) and adds
`internal_audit` to `USES` and to `source_use_is_permitted`.

| Operation | Required uses, checked at the moment of use |
| --- | --- |
| Ingest | `collect` and `derived_retention` |
| Publish | `collect` and `derived_retention`, rechecked under the lock |
| Value-bearing audit computation | `internal_audit` and `derived_retention` |
| Metadata-only inspection | Separate function grant; returns no values |
| Feature series | `feature` and `derived_retention` |
| Training / testing reads | `train` or `test`, and `derived_retention` |
| Report with values | `internal_audit`, rechecked when the report is generated |

The observation's `permission_id` must equal its run's `permission_id`, and both must
belong to the observation's `source_id` (composite foreign keys). Reads are denied as
soon as a permission is missing, expired, revoked or not yet approved; purge (8) follows.

## 6. Database roles and function security

| Role | May do |
| --- | --- |
| Migration owner | Owns tables and `SECURITY DEFINER` functions |
| `audience_writer` | Execute ingest, publish, failure-record and audit-proposal functions only |
| `audience_verifier` | Execute snapshot read and verified-audit record functions only; used only by the verifier worker (7.5) |
| `audience_auditor` | Execute snapshot read, metadata inspection and audit-run read functions only |
| `anon`, `authenticated`, `PUBLIC` | Nothing on these tables or functions |

- All audience tables: `revoke all ... from public, anon, authenticated, audience_writer,
  audience_auditor`; row-level security enabled with no permissive policies.
- Every function: `revoke execute ... from public`, explicit grants per role,
  `security definer`, `set search_path = pg_catalog, public`, and fully qualified names.
- Function arguments select scope only (run, snapshot, spec IDs). No argument can widen
  a use, skip a permission check or name a table.
- The writer cannot call read functions; the auditor cannot call write functions.
- Only `audience_verifier` can execute `audience_record_verified_audit`. The writer, the
  auditor, the audit CLI and the agent never hold that role's credential.

## 7. Audit

### 7.1 Tracked artists (v1)

The tracked set is the union of:

1. An explicit synthetic tracked-artist fixture (versioned list).
2. Artists credited on an **upcoming catchment show**: the venue's current reviewed
   `venue_geography_versions` row is inside `nyc-beta-catchment` v1; the event status is
   `scheduled`, or `postponed` with a confirmed replacement date; and the event's local
   date is within 0–180 days inclusive of the evaluation date, both computed in
   `America/New_York`. Date-only shows qualify. Cancelled, completed, `unknown`-status
   and postponed-without-date events are excluded. A venue without a reviewed geography is
   excluded.

Priority: ascending days until the earliest qualifying show, then the fixture list. User
follows are a later dependency.

### 7.2 Input manifest

Each audit run binds an immutable manifest of everything its result depends on:

- `snapshot_id` and `watermark`, and an explicit `evaluation_time`.
- `rule_set_version` (`audience-audit` v0.1) and `threshold_set_version`
  (`audience-thresholds` v0.1).
- Metric definition, artist-mapping, geography-mapping and venue-geography version IDs.
- Tracked-artist list version and catchment version.
- Event state and permission/source state, copied at audit time into immutable
  `audit_input_versions` rows and referenced by ID.
- Per reading: `observation_key`, `revision`, `content_hash` and mapping version IDs.

Hashes identify inputs; the version rows make them reconstructable. If a purge later
removes a required input, the run is marked `replay_unavailable`. The ability to replay a
historical result never grants access to its evidence now.

### 7.3 Rules — `audience-audit` v0.1

Two categories. **Hard controls** make evidence unusable; read and assembly functions deny
them directly, whatever the audit says, and they can never be waived. **Investigate**
rules mark a change or gap that deserves attention; the data stays usable.

| Rule | Category | Fires when |
| --- | --- | --- |
| `PERM-001` | Hard | A published reading's permission no longer allows derived retention (purge pending). Detected through metadata inspection; no values are read. |
| `PERM-002` | Hard | Source, run and permission disagree (backstop for a bypassed constraint) |
| `MAP-001` | Hard | The linked artist-mapping version is not `reviewed` |
| `TIME-001` | Hard | The local date of `retrieved_at` in `period_timezone` is before `measured_to`; or `provider_published_at` is after `retrieved_at`. Unknown zone or unknown publication time makes the affected check `unassessed`, not passed. |
| `DEF-001` | Hard | A registered feature-series spec would admit rows with different platform, unit, window, definition version or a disallowed method. Independent series may coexist. |
| `GEO-001` | Investigate | A tracked artist's reading has an unresolved geography mapping |
| `COV-001` | Investigate | A tracked artist with an upcoming catchment show has no usable reading in the eligible audience geography (`nyc_city` v1). Lowered to `info` only when a fresh reading with a matching definition records `outside_top_locations`. |
| `FRESH-001` | Investigate | `period_age` (evaluation date minus `measured_to`) exceeds twice `expected_cadence`. Reports `period_age` and `retrieval_age`; re-fetching an old value does not make it fresh. |
| `CFG-001` | Investigate | A metric definition in use has no `expected_cadence` or no `jump_abs_floor` |
| `JUMP-001` | Investigate | Two consecutive effective compatible readings change by ≥ 50% **and** by ≥ the definition's `jump_abs_floor`. Previous value zero: only the absolute floor applies. Either value missing: pair skipped and counted in `MISS-001`. |
| `CORR-001` | Investigate | A chain has more than two corrections, or a correction changes the value by ≥ 25% of the original (original zero: only `jump_abs_floor` applies) |
| `MISS-001` | Info | Missing-value rate by provider, metric and `missing_reason` |

Ordering for consecutive readings: `(measured_to, measured_from, observation_key)`, using each key's effective revision.
Thresholds in `audience-thresholds` v0.1 are **provisional** and need backtesting before
any user-facing use.

### 7.4 Issues, occurrences and lifecycle

- **Issue**: stable `issue_key = hash(rule_id, rule_version, scope)`. The scope is the
  reading identity where one exists, or keys such as artist, metric definition and
  geography for coverage findings. Tracks `first_seen_run`, `last_seen_run`, `status`.
- **Occurrence**: immutable per-run evidence for an issue.
- Status values: `open`, `unassessed`, `resolved`, `waived`, `closed_by_purge`.
  - `resolved` only when a succeeded run's manifest re-covers the issue's scope and the
    rule does not fire. Absence is not proof of resolution.
  - A failed run, or a run that lacks the scope's inputs, sets `unassessed` and keeps the
    issue open.
  - `waived` only for Investigate rules, recorded by the owner with a reason and expiry.
    Attempting to waive a Hard control is rejected. The agent can never waive.
  - `closed_by_purge` is recorded separately when the evidence is purged.

### 7.5 Verified result submission

Submitted findings are an untrusted proposal. Only the verifier's independent result
counts, and the database rejects any verified result it can disprove.

1. **Proposal.** The audit CLI (`python -m app.audience_audit --snapshot <id>`) builds
   the manifest, evaluates the rules and calls `audience_propose_audit` as
   `audience_writer`. This stores the run as `proposed` with its findings document. A
   proposed run grants nothing: it cannot resolve issues and cannot make inputs eligible.
2. **Trusted recomputation.** A separate verifier worker
   (`python -m app.audience_verify`) runs server-side with the `audience_verifier`
   credential. It does not read the proposal's inputs. Instead it:
   - rebuilds the manifest from the stored snapshot through the read functions;
   - evaluates the rules with the rule engine pinned by `rule_set_version`;
   - compares its findings with the proposal, finding by finding, including passes.

   Any difference records the run as `failed (result_mismatch)`. The rule engine is a pure
   module with no network or filesystem access. Its source hash is registered against the
   rule-set version in `audit_rule_implementations` by migration, and the worker refuses
   to run if its loaded code does not match.
3. **Database checks on record.** `audience_record_verified_audit` (verifier only)
   rejects the result unless all of these hold:
   - **Same manifest.** The manifest hash equals the hash the function computes in SQL
     from the stored snapshot, watermark and version rows.
   - **Complete inputs.** The assessed-input set equals the snapshot's full set of
     effective `(observation_key, revision, content_hash)` for the tracked artists.
     Nothing may be omitted or added.
   - **Complete results.** Every rule in the rule set has exactly one result (`pass`,
     `fire` or `unassessed`) for every scope it covers.
   - **Matching Hard controls.** The function recomputes PERM-001, PERM-002, MAP-001 and
     TIME-001 in SQL, from the same rows, and they must match the submitted results.
   - **Current versions.** The rule-set and threshold-set versions are the current ones.
4. **Store.** On success, the run becomes `succeeded` and the function stores its issues,
   occurrences and one `audit_assessed_inputs` row per reading (`observation_key`,
   `revision`, `content_hash`, mapping versions, metric definition version, threshold set,
   feature-spec version, assessment result). Only `succeeded` runs count in 7.4 and 7.6.

**Residual trust.** A compromised verifier could still misreport an Investigate rule, but
it cannot:
- hide an input, because the input set is completeness-checked;
- clear a Hard control, because those are recomputed in SQL and are also enforced
  directly by the read functions;
- record a result for a manifest the database did not derive.

The agent's narrative is never compared or trusted.

### 7.6 Feature eligibility

`audience_feature_series(spec_id, snapshot_id)` returns a reading only when all hold:

1. Hard controls pass now, including a fresh permission check for `feature` (or `train` /
   `test` for those reads).
2. The exact `observation_key`, `revision` and `content_hash` appear in
   `audit_assessed_inputs` of a **succeeded** (verifier-recorded, 7.5) run whose rule set, threshold set, metric
   definition version, mapping versions and feature-spec version all equal the current
   ones. A watermark alone is not sufficient; an `unassessed` result grants nothing.
3. The row fits the spec (`DEF-001`).

Rows published after the last successful audit wait for the next one.

## 8. Retention and purge

- Read denial is immediate when a permission becomes invalid (5).
- `audience_purge_invalid(batch_size)` is idempotent and retryable. Each batch is one
  transaction: it deletes the invalid readings, redacts values in occurrence evidence,
  findings documents and manifests (keeping IDs and hashes where retention allows), marks
  dependent audits `replay_unavailable`, sets affected issues `closed_by_purge` and writes
  deletion evidence containing only permitted metadata (IDs, permission, reason, time). A
  failed batch rolls back; completed batches stay complete.
- **Files**: PostgreSQL cannot roll back filesystem changes. Each batch enqueues rows in a
  durable `artifact_cleanup_queue` (path, action `delete` or `redact`, status, attempts).
  A separate retryable worker processes the queue against `.local/audit-reports`. Purge is
  reported as **pending** until both the database batch and its file cleanup finish.
- Historical snapshots are reproducible only while their inputs remain lawfully retained.

## 9. Failure handling

- **Ingest** runs in one transaction. Any failure rolls back everything; nothing is
  published.
- **Failure records** are written afterwards in a separate transaction (attempt, fixed
  error code, no payload). If that write fails, the CLI exits non-zero with
  `failure_not_recorded` and claims no durable record.
- **Audit failure** follows the same pattern and leaves issue status unchanged.
- Error codes are fixed strings; messages never echo payloads or credentials.

## 10. Auditor agent

Defined in `docs/skills/audience-auditor.md`. It runs as `audience_auditor`, reads the
stored audit run through the read functions, and writes an advisory Markdown report to
`.local/audit-reports/<run_id>.md` (ignored by Git). The report:

- groups findings by category (Hard, Investigate, Info) and then by artist;
- cites issue keys and evidence rows;
- quotes values only where the row's permission allows `internal_audit`, rechecked at
  generation time; otherwise shows IDs and redacted evidence;
- labels any suggested cause as a hypothesis;
- distinguishes "this evidence cannot be used" from "this change deserves investigation".

It cannot write to the database, change readings, permissions, mappings or approvals, or
waive findings. The existing research agent (SS-RESEARCH-0.2/0.3) remains the scouting
path for sources and terms.

## 11. Files

| Path | Purpose |
| --- | --- |
| `docs/contracts/audience-observation-v0.1.md` | Contract summary for collectors |
| `docs/skills/audience-auditor.md` | Auditor agent role |
| `services/api/app/audience.py` | Fixture validation, ingest, publish and snapshot clients |
| `services/api/app/audience_audit.py` | Pure rule engine and audit (proposal) CLI |
| `services/api/app/audience_verify.py` | Verifier worker: trusted recomputation and record |
| `supabase/migrations/<timestamp>_audience_observations.sql` | Tables, roles, functions, grants |
| `supabase/tests/audience_*.sql` | Database contract tests |
| `services/api/tests/test_audience*.py` | Python and PostgreSQL acceptance tests |
| `tests/fixtures/audience/nyc.json` | Synthetic fixture |

## 12. Acceptance tests

All tests use synthetic fixtures. Concurrency tests use connection barriers and bounded
timeouts.

| # | Guarantee | Test |
| --- | --- | --- |
| T1 | Fixture contract | Unknown fields, unreviewed or stale mapping versions, null value without reason, and wrong unit are rejected with fixed codes |
| T2 | Replay and revisions | Identical replay of any revision is a no-op; same key with changed content and no target fails; a correction keeps the key, gets head revision + 1 and links to the head; a collector-supplied revision is ignored |
| T3 | Correction chains | Cross-reading, non-head (branching), looping and unpublished-target corrections are rejected with their fixed codes; two concurrent corrections of one head yield exactly one revision; equal-period ordering is deterministic |
| T4 | Atomic ingest and failure record | A mid-run failure leaves no rows and a separate failed-attempt record; a simulated recording failure yields `failure_not_recorded` |
| T5 | Publish revalidation and races | Revocation or mapping rejection between ingest and publish stops publication. Publication racing revocation: exactly one ordering wins and the result is consistent. Two writers submitting the same replay or the same correction: one succeeds, the other is a no-op or a fixed rejection. |
| T6 | Watermark | A publish holds the lock past the snapshot request; the snapshot waits and captures a watermark that includes it; a rebuild from the stored watermark is identical; publication IDs are monotonic |
| T7 | Privileges and function security | `anon`, `authenticated` and the auditor cannot select from tables; `PUBLIC` cannot execute privileged functions; the writer cannot call read functions; the auditor can call only read and metadata functions; only `audience_verifier` can call `audience_record_verified_audit`; arguments cannot widen scope; a caller-manipulated `search_path` (shadow objects in a caller-owned schema) cannot redirect a function |
| T8 | Permission gating | `collect`, `derived_retention`, `display`, `feature`, `train`, `test` and `internal_audit` are each denied independently when missing, expired, future or revoked; mismatched source, run and permission references are rejected |
| T9 | Rule engine | One fixture per rule fires exactly the expected issue keys, including: 0–180 local-date window edges, postponed with and without a date, cancelled, completed, date-only show, zero denominator, missing pair, unknown cadence, unknown zone |
| T10 | Determinism | The same manifest produces byte-identical findings across runs |
| T11 | Recompute check | A proposal with one finding removed, or one pass flipped, is recorded as `failed (result_mismatch)`; a proposed run grants no eligibility and resolves no issue |
| T12 | Coverage by membership | Rows below the watermark but absent from assessed inputs are not eligible. Changing the rule-set, metric-definition, mapping, threshold or feature-spec version each removes eligibility. An `unassessed` result grants nothing. |
| T13 | Issue lifecycle | A failed run leaves issues `open` or `unassessed`; a successful reassessment resolves them; purge gives `closed_by_purge`; waiving a Hard control is rejected |
| T14 | Purge and file cleanup | Batched purge redacts readings, evidence and manifests; a failed batch rolls back while earlier batches stay done; dependent audits become `replay_unavailable`. A crash between the database purge and file cleanup leaves queue rows that a retry completes; status stays pending until both finish. |
| T15 | Report redaction | Without `internal_audit` the report has IDs and redacted evidence only; permission is rechecked at generation |
| T16 | Catchment | Jersey City and Hoboken venues are inside; Newark is outside; a venue without a reviewed geography is excluded |
| T17 | Forged verified result | Calling `audience_record_verified_audit` as the writer or the auditor is denied. As the verifier, each of these is rejected: a mismatched manifest hash, an omitted or extra assessed input, a missing rule result, a Hard control result that differs from the SQL recomputation, and a stale rule-set version. A worker whose rule-engine hash differs from `audit_rule_implementations` refuses to run. |

## 13. Definition of done

- The existing Verify jobs pass, including the `database` job.
- PostgreSQL tests **execute**: in CI the `database` job sets `SWEET_SEATS_REQUIRE_DB=1`,
  which makes the database fixture fail instead of skip. A skipped database test does not
  satisfy acceptance.
- Product code and acceptance tests make **no external provider calls**. CI dependency
  installation and existing advisory checks keep their current network access.
- Negative controls in `supabase/ci/negative_controls.sh` are extended so that deliberately
  breaking a privilege, permission check or recompute step makes a test fail.
- README and contract links are updated. No remote migration, provider activation or
  deployment.

## 14. Open decisions for the owner

Implementation in this increment is synthetic-only, so none of these block it. Each one
blocks a later step, as shown.

| Decision | Blocks | Enforced by |
| --- | --- | --- |
| Audience provider, chosen after the sample test (Soundcharts, Chartmetric, Viberate), and its written terms, including the `internal_audit`, feature, training and testing rights | Any live collection | No approved `source_permissions` row exists for any audience provider, so ingest is denied (5) |
| Retention duration for each permission | Any live collection | Ingest for a non-synthetic source is rejected with `retention_undefined` until the permission records a duration |
| Expected cadence for each metric definition | Any live collection | Ingest for a non-synthetic source is rejected with `cadence_undefined` while the metric definition has no `expected_cadence`; CFG-001 also flags it |
| Backtested values for `audience-thresholds` (50% jump, 25% correction, absolute floors) | Any user-facing use of audit results or feature series | Threshold sets carry `status` (`provisional`, `validated`). v0.1 is `provisional`, and user-facing projections require `validated`, so none exist in this increment |
