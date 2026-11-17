# Sweet Seats

NYC-area live music discovery and, once licensed comparable offer history supports it, personalized ticket buy/wait recommendations.

## Current state — 2026-11-17

`main` holds:
- **Discovery and sources:**
  - the fixture-backed discovery feed and API;
  - transactional PostgreSQL persistence;
  - deny-by-default source permissions, with RLS and negative controls;
  - the MusicBrainz identity resolver and its collection-run ledger;
  - disabled Ticketmaster and official-calendar adapters.
- **Alerts and accounts:**
  - durable jobs and the alert outbox, with send-time trigger, follow and consent re-checks;
  - Supabase-token-verified user workflows ([user API](docs/contracts/user-api-v0.1.md)).
- **Pilot foundation (PR #31):**
  - CI on every pull request, running every database test against a disposable PostgreSQL plus 46 negative controls;
  - the coming-soon waitlist with consent evidence and source attribution;
  - an append-only consent history tied to the exact copy shown;
  - a recent sign-in required before a deletion request;
  - the Postmark email transport and its bounce/complaint webhook;
  - a draft Render blueprint, a migration runner and a restore runbook.

**The stack.** It runs as a pnpm workspace, migrated on Replit on 2 Nov 2026:
- the Vite app in `artifacts/sweet-seats`;
- the coming-soon page in `artifacts/sweet-seats-coming-soon`;
- `artifacts/api-server` (Express), which proxies `/api` to the FastAPI service in `services/api`.

`replit.md` describes running it. References to `apps/web`, Next.js or Vercel in older documents describe the pre-migration stack.

**Nothing is deployed, no provider is activated and no notification reaches a person.**
- **Database:** the API can now use a hosted Supabase database, but only when it is explicitly opted in. See [Hosted database (Supabase)](#hosted-database-supabase).
- **Alerts:** the alert worker still sends through a logging transport.
- **Replit publishes:** the four "Published your App" commits of 2 Nov may have exposed the synthetic preview publicly. The owner should confirm what is reachable and unpublish or label it.

For phase status and open gaps see the
[phase assessment and gap register](docs/phase-assessment.md),
[MetaBrainz readiness](docs/metabrainz-readiness.md),
[asset inventory](docs/asset-inventory.md) and
[external research handoff](docs/research-handoff.md).

Run the [fixture-to-feed quickstart](docs/contracts/discovery-demo-v0.1.md#run-locally).
See the [audience-provider evaluation](docs/audience-provider-evaluation.md); the
Soundcharts-first evaluation recommendation is pending approval. Neither audience
provider is integrated. The [NYC audience observation and audit design](docs/superpowers/specs/2026-10-27-nyc-audience-audit-design.md)
(SS-AUDIENCE-0.1) is a specification under review; nothing in it is implemented.

- [Notion project and architecture index](https://app.notion.com/p/3f57ecee36a980dfbc14eb53a52e3d0f)
- [00 — Product Charter & Phase 0](https://app.notion.com/p/3f57ecee36a981d09ddfcb8d962654a4?pvs=204)
- [01 — Authority Map & Decision Register](https://app.notion.com/p/3f57ecee36a98119aff6f8b3496376f6?pvs=204)
- [02 — Entity Dictionary & Cardinalities](https://app.notion.com/p/3f57ecee36a9817e8091d685216f95e2?pvs=204)
- [03 — Source Registry & Permission Gates](https://app.notion.com/p/3f57ecee36a9813f8b9eeca6cabe6d78?pvs=204)
- [04 — Sequenced Roadmap & Next Build Backlog](https://app.notion.com/p/3f57ecee36a9818b8582c09658e0d046?pvs=204)
- [05 — Runtime, Forecasting & Price Safeguards](https://app.notion.com/p/3f57ecee36a981e7b0d4e3d70241a53c?pvs=204)
- [Miro architecture workspace](https://miro.com/app/board/uXjVEbowYB8=/)

## First release

Follow artists and receive source-backed official public announcement, on-sale and event-status alerts for reachable NYC-area concerts. An installable PWA is proposed. The server performs collection and delivery even when the browser is closed.

Predictive advice is a later gated release. Do not claim unannounced event access, whole-market cheapest prices or guaranteed savings. Sports, restaurants and automated purchases are deferred.

## Authority

| Component | Authority |
|---|---|
| Notion | Approved definitions, cardinalities, source policies, metrics, decisions and acceptance criteria |
| Miro | Derived visual architecture and explicitly labeled exploration |
| GitHub | Executable code, migrations, adapters, tests, models and deployment manifests |
| PostgreSQL | Operational canonical records and job/alert state |
| Object storage | Permitted payloads, dataset manifests and model artifacts |
| Runtime | Frontend, API, scheduler, workers, inference and delivery |
| Linear (when activated) | Execution task status; advisory research, no architecture or source-rights authority |
| Perplexity (when activated) | Internal research execution/evidence; no direct product/model ingestion |

Use internal UUIDs with typed vendor mappings. The SS-DATA-0.1 entity dictionary contains 29 initial entities; it is documentation, not deployed SQL.

## Technology

- **Web:** Vite/React web apps served as static sites.
- **API:** an Express front for `/api`, with the Python FastAPI API and the alert worker beside it, on Render (`render.yaml`, a draft).
- **Database and sign-in:** Supabase PostgreSQL and Auth.
- **Alert email:** Postmark.
- **Storage:** Cloudflare R2 private S3-compatible storage, when its permission gate opens.

These are recommendations, not provisioned resources. A 2026-10-10 planning illustration put the low-volume base at about $41/month before licensed data, training overages, storage/notifications/domain and extra environments; it is not a current forecast. Use the workload model in the [phase assessment](docs/phase-assessment.md#economics-and-pilot-proposed-thresholds-none-approved) and recheck provider pricing before provisioning.

## Data sources and access

Planned: permitted MusicBrainz identity fields, Ticketmaster Discovery, curated official monitors, one licensed detailed-offer provider, authorized aggregate inventory, one audience provider and rights-compatible geography/transit.

Product sources remain planned/disconnected in the inspected baseline. Internal research activation is separately gated by SS-ADR-007; no provider connection is activated by this branch. Unknown permissions deny collection/storage/display/training/testing as applicable. An API key or successful request does not grant indefinite historical retention or predictive-use rights.

Detailed offer access with retained-history and modeling rights is the pricing release's critical dependency.

## Prediction and price safeguards

1. Record collection outcomes and permission/provenance evidence.
2. Reconcile events and normalize eligible total-order offers for seat tier, party size, adjacency, fees/taxes and freshness.
3. Build as-of feature snapshots with availability-time cutoffs.
4. Run champion forecasts and persist model/version, interval, action, expiry and source coverage.
5. Independently assess steep price moves on each valid collection.
6. Produce opportunity/rising-price alerts when evidence is sound; revalidate out-of-range changes and invalidate stale advice.
7. Evaluate matured horizon labels using event-held-out chronological splits.
8. Retrain challengers on a controlled schedule; compare baselines/calibration; shadow, promote atomically and retain rollback.

A sharp rise alone is not a buy instruction. A click is not a purchase. Missing collection is not sold out. New observations do not automatically change production model weights.

Candidate thresholds (15% and $25 total-order change in 60 minutes) require backtesting; they are not validated launch settings.

## Roadmap

| Phase | Deliverable / gate |
|---|---|
| 0 | Scope, definitions, journeys, architecture and actionable backlog |
| 1 | Identity/schema contracts, permission enforcement and synthetic fixtures |
| 2 | Runtime, auth, secrets, durable jobs/outbox, backups and recovery |
| 3 | Concert discovery and status/on-sale alerts |
| 4 | Licensed comparable offer history and explicit historical/model-use permission |
| 5 | Demand/eligibility features with reproducible lineage |
| 6 | Forecast evaluation, calibrated uncertainty and shadow release |
| 7 | Operational phone PWA, reliable alerts and monitoring |
| 8 | Evidence-led native/provider/vertical expansion |

## Build scope: the Sweet Seats pilot

The current scope comes from the 16 Nov 2026 diagnostic. It is a pilot: about 10 invited users get source-backed alerts for a fixed panel of about 25 artists and 10 NYC venues. The work is ordered so the parts only Sweet Seats owns are built first and measured from day one:
- provenance on every event and alert;
- a first-seen lead-time dataset per source;
- an append-only, provable consent record;
- an owned waitlist with attribution.

Pricing advice (X2), mobile releases and design-system work are frozen until the pilot reports.

| Step | What | Status |
|---|---|---|
| 0 | CI with PostgreSQL, dependency advisories, docs | Done (PR #31) |
| 1 | Coming-soon waitlist with consent and `?src=` attribution | Done (PR #31) |
| 2 | Supabase and Render environment, migration runner, restore drill (G-11) | **Code done:** the hosted-database opt-in, a draft `render.yaml`, `scripts/apply-migrations.{sh,ps1}`. Accounts and the drill are the owner's |
| 3 | Sign-in screens; recent sign-in before deletion (G-16); JWT key type (G-05a) | The API check is done; screens and sign-out revocation are next |
| 4 | Consent-strict email alerts: consent history (G-15), Postmark, webhooks, account screens, purge (G-06) | History, transport and webhooks are done. Next are the screens, the endpoint store and the purge, plus a real email on staging |
| 5 | First live source (Ticketmaster), lineage and purge (G-08), shared rate budgets (G-10) | Waits on the terms review, the panel and lifting the `.invalid` URL guard (G-09) |
| 6 | Official-calendar lead-time dataset: an append-only `first_seen` and a weekly `pilot_metrics` | Waits on the venue calendar list |
| 7 | Invite 10 pilot users from the waitlist | After Steps 2–6 |

Reference Notion decision IDs in pull requests. Keep credentials, private user records, licensed payloads and trained artifacts out of Git. Publish no open-source license until the owner decides.

## Open decisions

These decisions belong to the owner:
- **Supabase and Render accounts**, plus the restore target and RPO/RTO.
- **Postmark:** an account and a sending domain (DKIM/SPF).
- **Endpoint store:** where alert email addresses are kept.
- **Consent and retention:** the consent wording and the purge and retention periods, with counsel.
- **Sign-in keys:** the JWT signing key type (G-05a).
- **First live source:** the Ticketmaster and MusicBrainz terms, the artist and venue panel, and the monthly budget cap.
- **Official calendars:** the venue calendar list.
- **Before public brand spend:** trademark clearance.
- **Later releases:** the detailed-offer source and contract, the audience vendor, evaluation and promotion thresholds, and price-alert thresholds.


## Internal research amendment — SS-ADR-007

[Contract SS-RESEARCH-0.2](docs/contracts/research-v0.2.md) is the single reconciliation of the earlier standards. Target: hourly scan of approved `research-quick` requests; reviewed report export only. Configuration is disabled; no scheduler, paid calls, webhook receiver, live migration or automatic Linear comment is activated. Labels do not authorize spending or publication. PR #2 is the merged reconciliation path; PR #1 is a historical alternative, not another contract to merge.

Offline demonstration (Python 3.11+, standard library only):

```bash
python3 -m unittest discover -s tests -v
python3 -m jobs.linear_research --fixture tests/fixtures/research/hourly.json
```

See [architecture reconciliation](docs/linear-research-agent.md) for verified branch facts, deferred integrations, source boundaries and activation gates. Discovery remains the first consumer milestone.

## Local PostgreSQL discovery

Use a dedicated disposable PostgreSQL 16 database. The application never creates a
schema on startup. A loopback database URL is always accepted; a hosted one only as
described below. For example:

```bash
docker run --name sweet-seats-local -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=sweet_seats -p 127.0.0.1:5432:5432 -d postgres:16
export SWEET_SEATS_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/sweet_seats
uv sync --frozen
# The two emulation scripts stand in for Supabase's API roles and Auth (auth.uid()).
psql "$SWEET_SEATS_DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/ci/emulate_supabase_roles.sql
psql "$SWEET_SEATS_DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/ci/emulate_supabase_auth.sql
SWEET_SEATS_MIGRATION_URL="$SWEET_SEATS_DATABASE_URL" scripts/apply-migrations.sh
uv run --frozen python -m services.api.app.discovery
pnpm install --frozen-lockfile
PORT=8080 pnpm --filter @workspace/api-server run dev   # API on :8080; see replit.md
```

The CLI prints source/logical-key replay digests, collection outcomes and
canonical/observation counts. Re-running the same fixture preserves IDs and counts. If
PostgreSQL is configured but unavailable, the API returns 503; it never silently serves
the JSON store. Without a database URL, the legacy single-writer `.local/discovery.json`
demo remains available. `SWEET_SEATS_LOCAL_DATABASE_URL`, the older name, is still read
when `SWEET_SEATS_DATABASE_URL` is unset.

### Hosted database (Supabase)

The API and the alert worker connect to a hosted database only when all of these hold.
Otherwise they refuse, and the error never includes the URL.
- `SWEET_SEATS_ALLOW_HOSTED_DATABASE=true` is set. It must be exactly `true`, and is checked again on every connection.
- The host is a Supabase host: `db.<ref>.supabase.co`, or the pooler at `*.pooler.supabase.com`.
- The connection uses TLS. `sslmode` defaults to `require`; `verify-full` is better where the CA is installed.
- Neither the URL nor the environment carries `hostaddr`, `PGHOSTADDR`, `PGSERVICE` or `PGSERVICEFILE`, any of which could redirect it.

Server-side prepared statements are off, so Supabase's transaction pooler (port 6543)
works.

The API's signed-in routes switch to the `authenticated` role. The database user must be
allowed to do that. Supabase's `postgres` user is, but check it on staging first.

Apply migrations to a Supabase project with `scripts/apply-migrations.sh`, or with
`scripts/apply-migrations.ps1` on Windows. Do not run the emulation scripts there:
Supabase provides those roles and Auth itself. Keep every database URL server-side and
out of Git.

### Database tests

Database acceptance uses a local administrative account able to create and drop
throwaway test databases. Never point tests at a hosted or shared database. Tests apply
all migrations only inside uniquely named test databases and drop them afterward:

```bash
export SWEET_SEATS_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/postgres
export PGPASSWORD=postgres
uv run --frozen python -m pytest services/api/tests tests -q
```

CI's PostgreSQL 16 job also exercises:
- Supabase-style default grants;
- RLS denial and source-permission boundaries;
- consent history;
- the deliberately broken negative controls.

It fails if any database test skips.

## Dependency verification

CI installs the hashed Python 3.12 runtime and development dependency graph from
`services/api/requirements-dev.lock`; production-only installs use
`services/api/requirements-runtime.lock`. Both Python locks are audited with pip-audit,
and the pnpm workspace is installed with `--frozen-lockfile` and audited with
`pnpm audit --prod`. Any reported advisory blocks CI. Development-only npm advisories
are not yet gated; see [dependency and API gap audit](docs/API-dependency-audit.md).
