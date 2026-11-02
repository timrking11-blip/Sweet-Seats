# Audience provider decision proposal — 18 October 2026

Recommendation: evaluate **Soundcharts first**, subject to owner approval and a
written agreement covering Sweet Seats. This is an evaluation preference, not a
procurement decision or activation approval. Neither provider is integrated.

| Criterion | Chartmetric | Soundcharts |
| --- | --- | --- |
| NYC relevance / coverage | City/country listener series, up to 50 locations; presence of NYC for the intended artist sample is untested. | Top-50-city observations; NYC/metro coverage for the same sample is untested. Neither establishes complete metro audience. |
| Identity | Cross-platform ID endpoint accepts Spotify and other platform identifiers [1]. | Artist-by-platform-ID returns vendor UUID and metadata [2]. Both can support reviewed canonical crosswalks; names alone remain insufficient. |
| Measurement / freshness | City listener counts after 2024-08-12 are estimates; model fills missing days. Preserve `is_estimate` and `includeEstimates`; endpoint does not establish a collection SLA [3]. | Global monthly listeners updated daily, top cities weekly; missing API dates may be interpolated in the UI. Current city counts' measured/estimated methodology remains unknown [4]. |
| API / operational burden | REST, historical windows, location pagination; preserve estimate flags and source dates [3]. | REST, date windows, pagination; separate vendor UUID lookup [2,4]. Both require server-side credentials, budgets, retry/backoff, missing-data handling and contract validation. No benchmark was run. |
| Published cost | Fixed-rate API from $350/month; pricing page also advertises usage-based access from $0.01/credit with $5 trial credit. Route costs and required endpoint entitlement need confirmation [5,6]. | Starter $50/month / 10,000 requests; Developer $250/month / 500,000 requests. Both exclude premium endpoints. Startup $500/month includes premium endpoints. Required endpoint access must be confirmed before budgeting [7]. |
| Rights | General terms restrict copying, storage and redistribution despite API product marketing. An API subscription alone is insufficient evidence for the proposed retained product dataset [8]. | General terms require consent for copying/distributing and prior written authorization for commercial use. Confirm API-specific agreement and allowed derived uses [9]. |

The preference is an engineering judgment: platform-ID resolution plus documented
city cadence gives a useful evaluation path. It is **not** evidence that Soundcharts
has superior NYC coverage, directly measured city counts, cheaper required endpoint
access, or adequate rights. Chartmetric's usage-based plan could be cheaper at small
volumes, and its explicit estimate flags are useful. Reverse this preference if the
sample test or written terms favor Chartmetric.

Before integration, compare the same approved artist/Spotify-ID sample for NYC
coverage, match failures, historical depth, actual freshness, missingness, methodology,
endpoint entitlements, total route cost and licensing. Obtain explicit storage,
retention/deletion, caching, attribution, public display, derived features, testing,
modeling and termination permissions. No account entitlement or agreement was inspected.

The storage and audit contract for these observations is specified in the
[NYC audience observation and audit design](superpowers/specs/2026-10-27-nyc-audience-audit-design.md)
(SS-AUDIENCE-0.1, under review). Viberate is an additional sample-test candidate there.

Future observation fields: provider, vendor/canonical artist IDs, metric definition,
rolling window, geography, observed/retrieved timestamps, measurement method,
estimate/imputation flags (unknown stays unknown), permission reference. Label changes
as **change in rolling 28-day monthly listeners**, not streaming growth. Compare only
compatible definitions/methods; leave missing observations missing.

Official sources inspected 2026-10-18 (provider-reported claims, not reproduced):

1. https://apidocs.chartmetric.com/reference/tag/artist/get/api/artist/type/id/get-ids
2. https://developers.soundcharts.com/api/reference/artist/get-artist-by-platform-id
3. https://apidocs.chartmetric.com/reference/tag/artist/get/api/artist/id/where-people-listen
4. https://developers.soundcharts.com/api/reference/artist/get-local-streaming-audience
5. https://chartmetric.com/plans/api
6. https://chartmetric.com/pricing
7. https://developers.soundcharts.com/pricing
8. https://chartmetric.com/terms-of-service
9. https://soundcharts.com/en/terms
