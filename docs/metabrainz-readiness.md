# MetaBrainz readiness: field/use matrix and open questions

Status: **preparation only.** Nothing here grants a permission, activates collection or
accepts terms. MusicBrainz stays `planned` in `public.sources`, and every use stays denied
until the owner records an approved `source_permissions` row with evidence, terms version
and validity window (SS-ADR-004).

The owner reports applying for the MetaBrainz **Stealth Start-Up** tier. That is an
application in progress, not verified approval, unlimited access or blanket commercial
rights.

## Primary sources (read 2026-10-29)

| Source | What it establishes |
|---|---|
| [Stealth Start-Up tier](https://metabrainz.org/supporters/tiers/7) | MetaBrainz contacts the applicant about data plans and sets "a reasonable fee" for development and testing; the company moves to a support tier when it launches. Fees, volume and terms are negotiated, not published. |
| [Data License](https://musicbrainz.org/doc/About/Data_License) (rev. 68951) | Core data is CC0. Supplementary data is CC BY-NC-SA 3.0. Live Data Feed packets are CC BY-NC-SA 3.0. Documentation is CC BY-NC-SA 3.0. Cover art is a separate dataset (Cover Art Archive). |
| [MusicBrainz Database](https://musicbrainz.org/doc/MusicBrainz_Database) (rev. 78416) | Artist core data: name, sort name, areas, IPI, ISNI, aliases, type, dates, disambiguation, MBID; relationships and URLs; genre entities (name, aliases, disambiguation, MBID). Supplementary: annotations, **tags (including genre associations)**, ratings, derived statistics, **search indexes**, edit history. All data is available for commercial licensing. |
| [API FAQ](https://musicbrainz.org/doc/MusicBrainz_API/FAQ) | Non-commercial use of the web service is free; commercial use needs a commercial plan or contact. No API key; a meaningful User-Agent is required. |
| [Rate limiting](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting) (rev. 78895) | About 1 request/second per source IP "unless you have agreed otherwise"; exceeding it blocks all requests until the rate drops. Avoid fixed-time batch wake-ups and do not poll for changes. |

## Five things to keep separate

1. **Core metadata licence (CC0).** Supports display, retention and derived use of core
   fields however they were obtained. It says nothing about using the hosted service.
2. **Supplementary metadata licence (CC BY-NC-SA 3.0).** Non-commercial with attribution
   and share-alike. Needs a commercial licence for Sweet Seats.
3. **Hosted web service access.** Commercial use needs a plan, and the service has rate
   limits. CC0 does not make the hosted API free for commercial use.
4. **Dumps and the Live Data Feed.** Core-data dumps are CC0. The Live Data Feed is
   CC BY-NC-SA and needs sign-up.
5. **Sweet Seats' actual agreement.** None verified. Its terms decide items 2–4.

## Field/use matrix (only fields Sweet Seats needs)

Uses follow `app/discovery.py` `USES`. "Allowed by licence" is evidence for an owner
decision, not an approval. Every row's current status is **denied (no approved
SourcePermission)**.

| Field | Category (evidence) | Collection via hosted API | Display | Retention | Derived use (reconciliation, alerts) | Feature / train / test | Obligations | Need |
|---|---|---|---|---|---|---|---|---|
| MBID | Core, CC0 | Needs agreement (commercial service) | Allowed by licence | `derived_retention`: allowed by licence | Allowed by licence | Allowed by licence; Phase 5+ only | None from CC0; agreement may add | **Required** (identity) |
| Artist name | Core, CC0 | Needs agreement | Allowed by licence | Allowed by licence | Allowed by licence | Allowed by licence; later | As above | **Required** |
| Disambiguation | Core, CC0 | Needs agreement | Allowed by licence | Allowed by licence | Allowed by licence (namesake review) | Not planned | As above | **Required** |
| Aliases | Core, CC0 | Needs agreement; requires `inc=aliases` | Not planned | Allowed by licence | Proposed: improves name matching | Not planned | As above | Proposed, not built |
| Artist–URL relationships (official site, socials) | Core, CC0 | Needs agreement; requires `inc=url-rels` | Not planned | Allowed by licence | Proposed: discover official calendars for monitoring | Not planned | As above. Each discovered site is its **own source** needing its own permission | Proposed, not built |
| Genre entities (name, MBID) | Core, CC0 | Needs agreement | Not planned | Allowed by licence | Not planned | Not planned | As above | Not needed |
| Genre associations and tags on artists | **Supplementary, CC BY-NC-SA** | Needs agreement **and** a commercial licence | **Denied** | **Denied** | **Denied** | **Denied** | Attribution, NC, SA unless licensed | Not needed; never request |
| Ratings, annotations | Supplementary | As above | Denied | Denied | Denied | Denied | As above | Not needed |
| Search `score` | Search index output (supplementary) | Needs agreement | Not shown | **Not retained** (transient) | **Pending agreement**: today it is only the transient exact-match test (`score == 100`); the stored confidence 0.9 is a Sweet Seats constant, not the score | Denied | Whatever the agreement says | Used transiently; ask MetaBrainz (Q2) |
| Cover art | Separate dataset (Cover Art Archive) | Out of scope | Denied | Denied | Denied | Denied | Separate terms | Not needed |

### Enforcement today

- `MusicBrainzClient` requests artist search and lookup **without `inc`**: no tags,
  genres, ratings, aliases or relationships are asked for. `ArtistCandidate` keeps only
  MBID, name, disambiguation and the transient score. The cache RPC receives MBID, name,
  disambiguation, confidence, method and run ID, and stores the first five; the run ID is
  only checked (a succeeded run must exist), not recorded on the mapping. That lineage
  gap is G-08. Pinned by
  `test_only_core_identity_fields_are_requested_or_kept` and
  `test_the_cache_write_carries_no_score_or_supplementary_field`.
- Every request opens a `collection_runs` row capturing the `collect` permission first;
  cache writes need `derived_retention` and a finalized, succeeded run (unchanged).
- Adding aliases or URL relationships later changes the request (`inc=`) and these tests.
  It must update this matrix and the recorded permission scope in the same change.

## Throttling

The client throttles to 1 request/second **per client instance**; `from_env` builds one
per process, so today that is one per process. That is enough only for a single collector
process per egress IP. `Retry-After` given as an HTTP date is ignored (falls back to
exponential backoff). Before a second collector, a scheduled worker
plus a manual CLI on the same host, or any host sharing an egress IP, add a shared
limiter. A PostgreSQL-held token per source is the smallest option. Alternatively, record
an agreed higher rate from MetaBrainz. Schedule lookups at spread intervals; resolve
artists when a user follows them and cache the MBID rather than polling for changes.
(G-10 in the [gap register](phase-assessment.md).)

## Questions for MetaBrainz

1. **Access method:** hosted web service, core-data dumps, or the Live Data Feed for
   development, testing and launch? Is a replicated mirror expected at our volume?
2. **Fields:** confirm the use of core artist fields (MBID, name, disambiguation;
   later aliases and URL relationships) under CC0 with service access under the tier.
   Does the agreement cover using the search service's relevance `score` as a transient
   match signal? Is any supplementary data included if we later want it?
3. **Volume and rate:** expected volume = distinct artists followed in the pilot ×
   (1 search + 1 lookup) at first follow, plus occasional re-resolution; the owner
   supplies the panel size. Is a rate above 1 request/second per IP agreed, and is the
   limit per IP or per account?
4. **Development and testing:** the fee and duration for the stealth phase, and whether
   CI may use recorded fixtures only (our plan).
5. **Commercial launch:** which tier applies, what triggers the move, and the attribution
   or listing obligations.
6. **Retention:** any obligation on cached core data or derived mappings after the
   agreement ends, or on data obtained during stealth.
7. **Future model use:** whether core fields may be features in later recommendation
   models, and whether any agreement term narrows CC0 use.
8. **User-Agent and contact:** the account identity to use in the User-Agent.

## To activate later (owner, not this branch)

Record the agreement and terms version; insert `source_permissions` rows for `collect`
and `derived_retention` (and `display` if names from MusicBrainz are shown) with
evidence and validity; set `access_status` to `approved`; then run the CLI against a
small panel. Keep `inc` parameters unchanged unless this matrix is updated first.
