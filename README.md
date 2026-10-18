# Sweet Seats

NYC-area live music discovery and, once licensed comparable offer history supports it, personalized ticket buy/wait recommendations.

## Current state — 2026-10-18

The repository is private. Main at `e28959e77408fbab397347e0d16614de80d59971` includes the merged SS-RESEARCH-0.2 offline contract; its provider calls, scheduler, webhook and publication path remain disabled. The discovery foundation is now proposed in a separate PR: a synthetic-data PWA, local FastAPI discovery contract, Supabase migration ledger and CI checks. None is deployed; the migration is not applied; no product provider, validated forecast model, paid research execution or notification delivery is active.

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

The selected stack is Next.js/TypeScript PWA on Vercel, Supabase PostgreSQL/Auth, Render API/workers, and Cloudflare R2 when its storage gate opens. Review the discovery-foundation PR and CI evidence; then confirm the first artist/venue sample, NYC catchment and notification channel. Provider activation and runtime provisioning remain separate owner approvals.

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
