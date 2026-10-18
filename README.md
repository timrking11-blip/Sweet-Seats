# Sweet Seats

NYC-area live music discovery and, once licensed comparable offer history supports it, personalized ticket buy/wait recommendations.

## Current state — 2026-10-18

The repository is private. Verified base `da735d5` includes the merged offline research
contract, fixture-backed discovery feed/API, disabled Discovery adapter, permission/RLS
tests and dependency fixes through PR #12. This branch completes unresolved-identity
review, date/status validation, pagination and rendered feed tests. The current
amendment adds transactional local PostgreSQL persistence; it does not apply remote
migrations. Nothing is deployed and no provider is activated.

Run the [fixture-to-feed quickstart](docs/contracts/discovery-demo-v0.1.md#run-locally).
See the [audience-provider evaluation](docs/audience-provider-evaluation.md); the
Soundcharts-first evaluation recommendation is pending approval. Neither audience
provider is integrated.

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

## Proposed technology

Next.js/TypeScript PWA; Vercel frontend hosting; Python FastAPI and workers on Render; Supabase PostgreSQL/Auth; Cloudflare R2 private S3-compatible storage when its permission gate opens.

These are recommendations, not provisioned resources. Proposed low-volume base infrastructure estimate: about $41/month before licensed data, training overages, storage/notifications/domain and extra environments. Recheck provider pricing before provisioning.

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

## Next iteration

The selected stack is Next.js/TypeScript PWA on Vercel, Supabase PostgreSQL/Auth, Render API/workers, and Cloudflare R2 when its storage gate opens. Review the local PostgreSQL amendment and validation evidence, including transactional replay/recovery, before connecting production storage. Confirm the first artist/venue sample, NYC catchment and notification channel. Provider activation and runtime provisioning remain separate owner approvals.

Current product layout: `apps/web`, `services/api`, `supabase/migrations`, `tests/fixtures`, `jobs`, `adapters` and `docs`. Future delivery adds provider adapters, durable jobs, model evaluation and infrastructure manifests only as their gates open.

Reference Notion decision IDs in pull requests. Keep credentials, private user records, licensed payloads and trained artifacts out of Git. Publish no open-source license until the owner decides.

## Open decisions

Budget; precise catchment and first sample; PWA confirmation; notification vendor/channel; detailed-offer source and contract; audience vendor; retention durations; evaluation/promotion thresholds; price-alert thresholds; accounts and restoration targets.


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
schema on startup and accepts only an explicit loopback database host. For example:

```bash
docker run --name sweet-seats-local -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=sweet_seats -p 127.0.0.1:5432:5432 -d postgres:16
export SWEET_SEATS_LOCAL_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/sweet_seats
python -m pip install --require-hashes -r services/api/requirements-dev.lock
python -m pip install --no-deps -e ./services/api
# Run once in this NEW database, in filename order. Never target a shared/hosted DB.
# The two emulation scripts stand in for Supabase's API roles and Auth (auth.uid()).
psql "$SWEET_SEATS_LOCAL_DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/ci/emulate_supabase_roles.sql
psql "$SWEET_SEATS_LOCAL_DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/ci/emulate_supabase_auth.sql
for f in supabase/migrations/*.sql; do
  psql "$SWEET_SEATS_LOCAL_DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f" || break
done
python -m services.api.app.discovery
python -m uvicorn app.main:app --app-dir services/api --host 127.0.0.1 --port 8000
# Separate terminal, after exporting SWEET_SEATS_API_ORIGIN=http://127.0.0.1:8000:
cd apps/web
npm ci
npm run dev
```

Open `http://localhost:3000`. The CLI prints source/logical-key replay digests,
collection outcomes and canonical/observation counts. Re-running the same fixture
preserves IDs/counts. If PostgreSQL is configured but unavailable, the API returns
503; it never silently serves the JSON store. Without the variable, the legacy
single-writer `.local/discovery.json` demo remains available. `--store PATH` explicitly
selects that legacy adapter. Existing JSON data is not automatically imported.

Database acceptance uses a local administrative account able to create/drop throwaway
test databases. Never use a hosted/shared database. Tests apply all migrations only
inside uniquely named test databases and drop those databases afterward:

```bash
export SWEET_SEATS_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/postgres
python -m pytest services/api/tests -q
python -m unittest discover -s tests -v
```

The CI PostgreSQL 16 job also exercises Supabase-style default grants, RLS denial,
source-permission boundaries and deliberately broken negative controls. PostgreSQL
integration tests skip explicitly when the test URL is absent; that is not a database
validation pass. Keep both database URLs server-side.

## Dependency verification

CI installs the hashed Python 3.12 runtime/development dependency graph from
`services/api/requirements-dev.lock`; production-only installs use
`services/api/requirements-runtime.lock`. Install the local API with `--no-deps -e`
after the lock. Use `npm ci` for the web lock. Both full npm audits (including dev)
and the Python dev/runtime audit block CI on any reported advisory; there are no
advisory ignore lists or report-only audit steps.

The pinned Next ESLint package's directory-only glob call uses a small private
compatibility adapter backed by `tinyglobby`, replacing the unpatched `braces` chain.
Next, React and the Next lint rules retain their versions. See
[dependency and API gap audit](docs/API-dependency-audit.md) for the exact scope,
compatibility evidence, review findings and remaining integration work.
