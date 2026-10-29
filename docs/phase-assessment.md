# Phase assessment and gap register

Status: engineering assessment, **not an approval**. Inspected 2026-10-29 at `main`
`e55f6e0` (PR #27 merged; Verify run 40835575908 green) plus branch
`feat/phase2-auth-closure`. Decision IDs come from the Notion
[decision register](https://app.notion.com/p/3f57ecee36a98119aff6f8b3496376f6)
(SS-ADR-001 to 007, read 2026-10-29, last edited 2026-10-15). Phase gates come from
[04 — Sequenced Roadmap](https://app.notion.com/p/3f57ecee36a9818b8582c09658e0d046).
No register entry covers authentication, consent semantics or alert eligibility, so every
rule this branch adds is **proposed**.

Nothing is deployed. No provider is activated. No notification reaches a person.

## Evidence levels

S specified · I implemented · L locally verified · C verified in CI · D deployed ·
O operationally demonstrated · B business validated. A level is claimed only with the
evidence named. CI levels for this branch are pending its draft PR checks.

## Phase verdict

**No phase has a fully evidenced exit.** Phase 0 documentation is complete (Notion 04
says so), but its owner product choices are still open; it is complete enough to build on.
**Phase 1** meets its enforcement gate in code and CI, but two gate items have no
recorded approval. **Phase 2** is the active phase and
cannot exit: environments, secrets, scheduling, monitoring and a restore exercise do not
exist. Later phases have isolated, disabled parts only. No completion percentage is
given: the planned entity and integration counts are not a defensible denominator.

| Phase | Required outcome | Existing implementation | Missing enforcement | Verification evidence | Exit status | Next dependency |
|---|---|---|---|---|---|---|
| 0 | Scope, definitions, promises, success conditions | Notion 00–05; README; contracts | Owner choices: catchment, first sample, budget, channel, PWA confirmation | S (Notion) | Exited for build; decisions open | Owner decisions |
| 1 | Identity, schema, permissions, source contracts | Foundation schema; `source_use_is_permitted`; reconciliation with provenance; unresolved review queue; MusicBrainz run ledger | Field-level licence provenance and matching review policy not recorded as approved; no purge on permission expiry/revocation, and cached mappings do not record the run or permission that authorized them (G-08) | I L C on `main`: `supabase/tests/*.sql`, the source-permission and MusicBrainz negative controls (28 controls on `main` in all), discovery/MusicBrainz pytest | Closure candidate | Owner records policy; G-08 |
| 2 | Runtime, auth, secrets, durable work, budgets, recovery, privacy | Durable jobs and fenced outbox (PR #27); send-time eligibility, consent integrity and user API (this branch) | Separate environments, secret manager, scheduler, logging/alerting, budget monitor, shared provider limits (G-10), restore procedure (G-11); asymmetric JWT keys (G-05) | I L for this branch: see [Verification](#verification-on-this-branch); C for PR #27 | **Blocked** | SS-ADR-006 provisioning approval; restore exercise |
| 3 | Concert discovery + announcement/status/on-sale alerts | Fixture discovery API and PWA page; Ticketmaster, official-calendar and MusicBrainz adapters (all disabled); alert planning/dispatch with non-sending `LogTransport` | No activated source; no notification channel; no follow/consent UI; synthetic-only observation guard | I L C (fixtures, mocked transport) | Not started operationally | Phase 2; source approvals; channel decision |
| 4 | Licensed comparable offer history | `InventoryStatusAdapter` raises; `priceRanges` display-only | Everything; no licensed offer source | S | Not started | Detailed-offer licence |
| 5 | Reproducible demand/geography/eligibility features | SS-AUDIENCE-0.1 spec (main); travel spec on an unpushed local branch | Everything | S | Not started | Phases 3–4 |
| 6 | Forecast evaluation, calibration, shadow release | None | Everything | — | Not started | Phase 4 history |
| 7 | Phone experience and operational hardening | Next.js discovery page; web manifest | No service worker, icons, push, install, quiet hours, monitoring | I (manifest only) | Not started | Phases 2–3 |
| 8 | Evidence-led expansion | — | — | — | Not started | Pilot evidence |

### Capability levels

| Capability | S | I | L | C | D | O | B |
|---|---|---|---|---|---|---|---|
| Deny-by-default source permissions | ✓ | ✓ | ✓ | ✓ | – | – | – |
| Canonical identity with provenance, unresolved review | ✓ | ✓ | ✓ | ✓ | – | – | – |
| Durable jobs, fenced alert outbox, delivery intent | ✓ | ✓ | ✓ | ✓ | – | – | – |
| Send-time trigger, follow and consent re-check | ✓ | ✓ | ✓ | pending | – | – | – |
| Supabase token verification, RLS-scoped user API | ✓ | ✓ | ✓ | pending | – | – | – |
| Consent evidence written by the server | ✓ | ✓ | ✓ | pending | – | – | – |
| Live source collection | ✓ | adapters | mocked | mocked | – | – | – |
| Notification delivery | ✓ | log only | ✓ | ✓ | – | – | – |
| Backup and restore | ✓ | – | – | – | – | – | – |
| Installable PWA | ✓ | manifest | – | – | – | – | – |

An RLS policy is not a user journey. An adapter is not an activated source. A manifest is
not an operational PWA.

## Gap register

Priority: P0 blocks any real user; P1 blocks the Phase 2/3 exit; P2 before scale or later
phases. "Proposed" means no Notion decision records it yet.

| ID | Risk | Decision | Required invariant | Enforcement | Acceptance test | Evidence now | Blocker | Priority |
|---|---|---|---|---|---|---|---|---|
| G-01 | A cancelled show is announced; an on-sale alert fires at an obsolete time | Proposed (under SS-ADR-004 display gate) | An alert sends only while the current projection still makes its trigger due | `alerts._reason` via `_due`, before every send | `test_a_cancellation_after_planning_*`, `test_a_moved_onsale_time_*`, `test_a_cancellation_between_subscriptions_*` | **Fixed here**, L | — | P0 |
| G-02 | An unfollowed artist still notifies | Proposed | A send needs a current, enabled follow of a performer | `alerts._following`, FOR SHARE in the intent transaction | `test_an_unfollow_*` (2) and `test_unfollowing_suppresses_queued_alerts` | **Fixed here**, L | — | P0 |
| G-03 | A worker that outlived its lease records a job result | Proposed | Job results are accepted only on a live lease on a fresh clock; side effects are idempotent or fenced on their own | `run_job(clock=)`, `_close_job`; per-alert claim tokens | `test_a_completion_after_the_lease_expired_*`, PR #27 takeover tests | **Fixed here**, L | — | P1 |
| G-04 | A signed-in user forges consent: any endpoint (including another person's), back-dated consent, reversed revocation, or deleting the profile row to cascade away consent and delivery evidence | Proposed | Only the server creates subscriptions; user revocation and outcome consent are DB-stamped (a new version re-stamps); no direct profile delete; nothing changes after a deletion request | `20261029100000_user_consent_integrity.sql` (grants, triggers) | `user_isolation_test.sql` consent block; 9 new negative controls | **Fixed here**, L; reproduced before the fix. Consent *versions* are still client-chosen strings with no history (G-15) | — | P0 |
| G-05 | No authenticated workflow; a client-supplied user id could be trusted | Proposed | Identity is only a verified Supabase token subject; ownership is RLS under the `authenticated` role | `app/auth.py`, `app/me.py` | `test_auth.py` (33), `test_me_api.py` (9), including an RLS-dependency control | **Fixed here** (HS256 only), L | Signing key type: owner (G-05a) | P0 |
| G-06 | A deletion request leaves data in place indefinitely | Proposed | A request stops planning, sending, outcome recording and account changes at once (done); a purge covering `auth.users`, the endpoint secret store, backups and logs follows within an approved period | Done: `tick` plan query, `_consented`, outcome policy, profile/follow triggers. Purge: future job | `test_planning_skips_users_who_requested_deletion`, `test_a_deletion_request_stops_*`, `test_after_a_deletion_request_*` | Partial. Deleting the account in Supabase Auth (an admin action) still cascades away consent and delivery evidence; suppressions caused by a deletion request are recorded as `no_current_consent` | Retention period and deadline: owner and counsel | P1 |
| G-07 | Duplicate or lost sends with a real vendor | PR #27 protocol | Stable idempotency key; reconcile before any retry; never claim exactly-once | `Transport.idempotent` / `reconcile` | PR #27 tests | Protocol only, `LogTransport` | Vendor and channel: owner | P1 |
| G-08 | Data kept after a permission expires or is revoked | SS-ADR-004 | Expiry/revocation stops use at once and purges retained derived data on schedule; each retained mapping names the run and permission that authorized it | None yet; `source_use_is_permitted` stops new use only. MusicBrainz mappings do not store the run ID, and any succeeded run can authorize a write for any MBID | Purge job test per source/use; mapping-to-run lineage test | **Open** | Retention durations: owner | P1 before any live source |
| G-09 | Synthetic-only guard lifted casually | SS-ADR-004 | `source_event_records` accepts only reserved `.invalid` URLs until a recorded decision | Migration check | Existing SQL test | Holds | Decision before first live source | P1 |
| G-10 | Several workers exceed provider limits (MusicBrainz ~1 req/s per IP; Ticketmaster default 5,000/day, 5/s) | Proposed | One shared, durable budget per source/credential/egress IP | Today: a throttle per client instance (`from_env` builds one per process); `Retry-After` dates are ignored | Two-process test against one limiter | **Open** | Worker topology | P1 before >1 collector |
| G-11 | No recovery evidence | Notion 04 Phase 2 gate | Restore from backup exercised, with RPO/RTO measured | Runbook and a timed exercise | Restore drill record | **Open** | SS-ADR-006 provisioning | P1 |
| G-12 | Namesakes or two same-day shows merged or split wrongly | SS-ADR-003 | Ambiguity stays reviewable and suppresses alerts | Reconciliation and review queue | Fixture cases for name collision and two same-day shows at one venue | Cancellation, reschedule and conflict fixtures exist; collision and same-day cases **not found** | — | P1 |
| G-13 | Price ranges presented as offers | SS-ADR-005 | No price advice without licensed, comparable, total-cost offers | Inventory adapter raises; prediction absent | Existing adapter test | Holds (disabled) | Licensed offer source | P2 |
| G-15 | Consent cannot be proven later | Proposed | Each consent and withdrawal is a versioned, append-only record tied to the exact copy shown | Today: latest values on the row; versions are client-chosen strings | Consent-history test | **Open** | Consent copy: owner and counsel | P1 before real users |
| G-16 | A stolen token takes irreversible account actions | Proposed | Deletion and similar actions need a recent sign-in; sign-out revokes sessions | Today: any unexpired token; no session-revocation check | Token-age test | **Open** | Supabase session settings | P1 before real users |
| G-14 | Future predictions not reproducible | SS-ADR-005 | Each fact keeps effective, observed/available and recorded times plus parser, normalizer and reconciler versions | `observed_at`, `available_at`, `adapter_version` exist; reconciliation version absent | Version-pinned replay test | Partial | Before Phase 5 | P2 |

### The authorization boundary (G-01, G-02, G-04)

Immediately before each send, the worker reads a fresh clock and the event's current
permission-filtered projection, re-derives the alert's trigger from it, and then, in the
transaction that commits the send intent, checks that subscription's consent and the
user's follow, holding both rows `FOR SHARE`. A revocation or unfollow that commits first
is seen; one that commits after the intent is seen on the next send, not this one. A source
change recorded after the projection read is likewise seen next time. No local check makes
the external send atomic with a concurrent change.

## Economics and pilot (proposed thresholds, none approved)

Keep five questions separate: discovery feasibility, incremental value of official-source
monitoring, engagement and willingness to pay, pricing-data feasibility, and predictive
value. The discovery beta depends on none of audience data, pricing or forecasting.

**Pilot.** One fixed panel of followed artists and NYC venues (size set by the owner),
for 6–8 weeks. Baseline: Ticketmaster Discovery alone, once approved. Treatment: baseline
plus approved official calendars.

| Measure | Numerator / denominator | Evidence |
|---|---|---|
| Incremental coverage | Panel shows first seen only in treatment / all panel shows | Canonical events by source first-seen |
| Lead time | Median (treatment first-seen − baseline first-seen) on shows both found | Observation `available_at` |
| Source health | Failed or stale collection runs / scheduled runs, per source | `collection_runs` |
| Review rate | Records sent to unresolved review / records collected | Review queue |
| Alert quality | Duplicate, obsolete (`trigger_obsolete`) or missed alerts / alerts sent | Outbox plus manual audit of a sample |
| Engagement | Opens and clicks / delivered alerts, from consented users only | `outcome_events` |
| Purchases | `purchase_confirmed` only; a click is never a purchase | `outcome_events` |
| Cost per useful alert | Collection + delivery + operating cost / alerts opened or clicked | Workload model below |

**Workload model** (variables, not prices; verify current pricing before quoting any):
collection calls = monitored units × collections per day × pages per collection ×
(1 + bounded retry rate); delivery = alerts × subscriptions × (1 + retry rate).
Fixed: database plan, API and worker hosting, scheduler, domain, monitoring, staging.
Usage: delivery vendor, storage. Licensed: provider fees (MetaBrainz tier; later offers).
Operating: review-queue minutes per week plus incident time. The $41/month figure in
Notion 05 is a dated illustration, not a forecast. R2 stays deferred until a retained
permitted object exists.

## Owner decisions needed

1. Supabase JWT signing: legacy HS256 secret, or asymmetric keys. Asymmetric keys need a reviewed crypto dependency in the lock (G-05a).
2. Notification vendor and channel, including idempotency and reconciliation support (G-07).
3. Retention periods: account deletion purge, delivery evidence, derived source data (G-06, G-08).
4. Whether a user may cancel a deletion request (an operator flow), and whether anonymous sign-ins may follow artists (both currently denied). Counsel: deletion deadlines, and evidence retention after withdrawal or deletion.
5. SS-ADR-006 provisioning and a restore target to exercise (G-11).
6. MetaBrainz field/use approvals ([readiness](metabrainz-readiness.md)).
7. Record the matching review policy and field-level provenance to close Phase 1.

## Verification on this branch

Session observations, 2026-10-29, on a disposable PostgreSQL 16.15 (loopback) with
Python 3.13 (CI uses 3.12): all five SQL suites pass; every pytest passes with none
skipped; every negative control is caught (37 on this branch, 28 on `main`); eight
mutation checks of the new safeguards each make a test fail. The pull request lists the
exact commands and counts. CI on this branch is the independent check.
