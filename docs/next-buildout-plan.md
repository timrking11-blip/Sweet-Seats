# Sweet Seats: next buildout plan

Planning review, 2026-11-02, revised after owner feedback. Increment A is the only approved execution scope; B–E remain roadmap items. See `docs/foundation-review.md` for actual increment A implementation and acceptance evidence. This document does not authorize publishing.

## Recommendation: the smallest useful next increment

**Build a shared web visual foundation first, not another app or a full-page regeneration.** Use the supplied SS-BRAND-UI-1.1 specification and tokens to establish one canonical CSS token file, a small brand/navigation/control layer, and a development-only living style guide. Both existing web frontends should consume it. Keep discovery at `/` and promotional content at `/coming-soon/`.

Do not combine this with new search APIs, account setup, database work, live providers, forms or alerts. Review the foundation before adapting the marketing and discovery layouts.

The uploaded package supersedes `docs/brand-ui-proposal.md` for visual direction. First look for the previously created “Flat Sweet Seats logo in navy.png” in existing project materials. It was not found in the inspected materials and is not in the ZIP; its README explicitly says the image was saved separately. Request a transfer before drawing/exporting production logo variants. Tokens, shared controls and the guide may proceed with the existing explicitly provisional marks. Final logo production is separate from A's completion.

The new Expo companion is already merged. Preserve it and its API contracts; do not build another native app as part of this website plan.

## 1. Verified current state

### Revision and concurrent work

- Local `main`, inspected HEAD `849ca2d2fa1b5197913056fa7296939ffb024f2a`.
- Commit: “Build Sweet Seats Expo companion with shared discovery API, honest demo states and source provenance.”
- Git origin is the Replit GitHub proxy for `timrking11-blip/Sweet-Seats`. No fetch/push was performed; upstream freshness is not established.
- The working tree was clean at the start and during baseline checks. Only planning documents/memory are being added by this request.
- Existing queued work covers shared visual styling and proper HTTP missing-page status codes; a promo-video task is also in progress/waiting for input. Do not start duplicate implementations or assume these are assigned here. Before approving work, ensure the style task uses the newly supplied specification, not the older proposal. Coordinate video branding before generating replacement media.

### Evidence matrix

| Capability | Classification and evidence | Next action |
|---|---|---|
| Public website | Imported and runtime verified. `artifacts/sweet-seats-coming-soon/src/pages/home.tsx` renders the preserved Lovable artwork/copy and working demo CTA. `/coming-soon/` returns 200; no connected waitlist. | Adapt, do not regenerate. |
| Web discovery | Implemented synthetic demo, runtime verified. `artifacts/sweet-seats/src/App.tsx: AppRoutes`; `app/page.tsx`; `app/discovery.tsx: DiscoveryFeed`, `DiscoveryFeedView`, `useDiscovery`. API returns 3 synthetic events, all stale. | Preserve behavior and trust disclosures. |
| Search/pagination | Implemented page-scoped text filtering, up to 100 loaded events, with previous/next API pagination. `DiscoveryFeedView` filters title, artists, venue and neighborhood; it is not whole-catalog search. | Add date/location scope deliberately in increment C. |
| Detail/provenance | Implemented demo. `app/events/event-page.tsx`, `EventDetail`, `eventTime`, `observedTime`. Real detail route and API returned 200. Missing event, timezone, source trail, TBA and stale warnings exist. | Retain event identifiers and evidence fields. |
| Unknown URLs / navigation | Repaired. `pages/not-found.tsx` has a named main landmark and return-home action. Both sites link to each other; refresh and absent account/ticketing capabilities are disclosed. | Do not reimplement the repair. True HTTP 404 remains separate. |
| Mobile companion | Expo/React Native/Expo Router source present. `artifacts/sweet-seats-mobile/app/index.tsx`, `app/events/[id].tsx`, `_layout.tsx`, `components/discovery-ui.tsx`; uses shared generated discovery client and the original API, not a duplicate fixture store. | Preserve. Existing typecheck failure needs narrow follow-up, not a new app. Physical-device behavior not inspected. |
| Follows | Backend code present; no operational Replit UI verified. `services/api/app/me.py: follow`, `unfollow`; account-scoped PostgreSQL access and verified identity required. | Device-local demo first only if approved; account integration later. |
| Saved events | Planned/missing in the inspected Replit UI and user API. Base44 public Saved screen exists, but its mutations/persistence have not been verified here. | Separate event saves from artist follows. |
| Accounts | Code present, not established as configured. `services/api/app/auth.py: configured`, `verify`, `bearer`; `me.py: current_user`, `user_store`, `user_session`. Supabase HS256 token verification and PostgreSQL RLS, not a working sign-in frontend. | Preserve original boundaries; no new auth provider during branding. |
| Consent/alerts | Code/contracts present, not live delivery. `me.py: revoke`, `request_deletion`; `services/api/app/alerts.py: dispatch_due`, `tick`, `_consented` and related worker logic. No live account/channel/delivery verification performed. | Separate later readiness work; following is never consent. |
| Data storage | `discovery_postgres.py: configured_store` chooses configured PostgreSQL or default `discovery.py: FixtureStore`; default local JSON is single-writer demo persistence. `replit_server.py` only seeds when no database/store is configured. | Never migrate or replace a database merely to restyle. Active connection was not inspected. |
| Providers | `ticketmaster.py`, `official_feeds.py`, `musicbrainz.py`, `source_registry.py` contain adapter/permission/identity logic. `/api/v1/discovery/mode` currently reports synthetic. | Code presence is not approved licensing or active collection. |
| Travel | No operational travel UI/API established in this inspection. The brand spec treats it as conditional, with approximate origin and request-only/no-cache restrictions subject to verification. | Deferred; inspect approved contract/provider before implementation. |
| Ticketing/pricing | No working purchases/live ticket links; detail button disabled. | Deferred beyond discovery; licensed price history and prediction validation are separate. |

### Backend and source boundaries

`artifacts/api-server/src/app.ts` forwards `/api/discovery/*` and `/api/v1/*`; `src/lib/discovery-service.ts: startDiscoveryService`, `discoveryProxy` supervise/proxy the preserved FastAPI process over a private Unix socket. `services/api/app/main.py: events`, `event_detail`, `discovery_mode` own the discovery contract.

The active web runtime is React/TypeScript/Vite/Wouter. TanStack Start is Lovable source history; Next.js is discovery source history. Neither should be restored merely for visual reuse. `lib/api-spec/openapi.yaml` and generated shared clients now also support mobile.

### Existing visual directions versus the new target

| Direction | Actual current implementation | Reuse |
|---|---|---|
| Discovery | Night/violet/gold custom CSS, cream text, Georgia editorial headings/wordmark, coral supporting accent, orb/ticket artwork. `src/app/globals.css`. | Keep layout/state components and original artwork until explicitly replaced; map semantics, not arbitrary hex replacements. |
| Lovable public page | Charcoal/cream/coral Tailwind styling, bold sans-serif display, imported SVG wordmark and concert-poster illustration. `src/styles.css`, `pages/home.tsx`, `public/`. | Keep structure, copy, poster and assets. The existing SVG is not the newly requested headphone-and-seat logo. |
| New working target | Supplied SS-BRAND-UI-1.1: background `#031126`, cream `#FFF1DD`, coral primary `#FF624D` with navy text, teal `#67BCAF`; system sans-serif, flat headphone/seat/music-note identity. | Use the attached semantic CSS source as the starting point; latest logo image and production exports remain absent. |

The supplied contrast table is evidence about specified opaque color pairs only, not rendered accessibility conformance. The prose calls for retiring discovery's serif display treatment; some typography-table rows still mention serif alternatives. Recommended resolution: use the explicit bold, friendly sans-serif direction, subject to foundation review.

## 2. Import map and external comparison

**Lovable:** `artifacts/sweet-seats-coming-soon/IMPORT.md`, `imported-src/`, `IMPORTED-README.md`, public assets and local original archive establish a one-time source import. The active port differs intentionally in routing/runtime and now has the repaired demo CTA/no-waitlist wording. Keep reference files read-only. The Lovable editor URL currently returns “You don't have access”; current upstream drift cannot be established. No continuous sync is verified.

**Base44:** no local import/SDK/source lineage was identified. The public preview at `https://sweet-seat-sync.base44.app` is readable. It shows an 11-show synthetic listing, date/neighborhood filters, partial-source, cancelled/rescheduled/postponed, stale and TBA examples. Public `/following`, `/saved`, `/account` show empty follows/saves, no sign-in, a demo clock and clearly non-delivering alert previews. This is useful screen/copy reference, not proof of internal state implementation or production accounts.

The supplied handoff reports React/TanStack source under `src/components/sweetseats/`, `src/features/demo/`, `src/routes/_app/`, versioned device storage, action-scoped rollback, per-item queues and reset fencing. **Those are reported external findings, not source verified in this Replit session.** No authorized Base44 source connection/export is available here.

Minimum export for source-level comparison:

- `package.json`, relevant route and CSS/token files (to identify dependencies, not import the entire runtime).
- Event/artist schemas, stable IDs, identity/crosswalk logic and fixtures.
- `src/features/demo/` service, storage/versioning, mutation queue, reset/failure behavior and their tests.
- Referenced follow/save controls and Following/Saved/Account/artist/detail routes in `src/components/sweetseats/` and `src/routes/_app/`.
- Needed local imports/assets and any demo-clock/filter utilities, with provenance/rights notes.

No credentials, customer records, account exports, or entire hosted backend are needed. No transfer of existing localStorage between unrelated origins is proposed.

## 3. Proposed navigation and route map

| Route | Status | Role |
|---|---|---|
| `/` | Existing; keep | Discover; initially honest page-scoped search |
| `/events/:eventId` | Existing; keep | Show detail, evidence and later Save |
| `/coming-soon/` | Existing; keep | Public explanation and real demo CTA |
| Unmatched discovery paths | Existing repaired screen | Dedicated not-found; true server HTTP 404 is separately queued |
| `/style-guide` | Proposed development-only | Foundation examples/states, not a public feature or account flow |
| `/artists/:artistId` | Proposed in D | Stable artist detail/disambiguation and Follow |
| `/following` | Proposed in D | Artist interests, no implicit notification consent |
| `/saved` | Proposed in D | Event shortlist retaining current cancellation/postponement status |
| `/account` | Proposed later | Initially honest device/demo scope if needed; sign-in only in E |
| Optional setup | Deferred | Add only when useful preferences and skip behavior exist |

Today retain visible brand↔demo links. Add Discover/Following/Saved navigation only when those routes work. Future mobile navigation may include Account only when its actual settings surface exists; do not ship decorative tabs. Existing Expo routes remain independent; no web URL move to `/app`.

## 4. Implementation increments, file sequence and acceptance

File paths below describe the implementation sequence; A's actual paths/results are recorded in the foundation review. Each subsequent increment needs separate approval and a fresh concurrency check.

### A — Shared visual foundation (recommended first)

1. Preserve ZIP/reference assets; search existing materials for the flat navy logo, requesting transfer only if unavailable. Do not regenerate the logo from prose or block the token/control/guide work on final asset production.
2. Add `lib/sweet-seats-brand/tokens.css` as the single semantic source, based on supplied CSS. Scope with `data-ss-brand="midnight-session"`; do not duplicate hex palettes in both apps.
3. Establish shared consumption **before** expanding primitives: both existing `src/main.tsx` entry points directly import `../../../lib/sweet-seats-brand/foundation` and `tokens.css`. Vite already handles workspace source imports; both leaf TypeScript checks include the imported source. Framework-neutral TypeScript plus native semantic markup/shared CSS avoids React module-resolution and new packaging infrastructure. Verify both typechecks and builds at this point.
4. Add a small shared web layer (`controls.css` and shared navigation metadata): provisional brand lockup treatment, native link/button styles, labeled form examples and focus/status patterns. Map existing discovery variables/Tailwind semantic aliases to the canonical source. No duplicated palette, new registry, Storybook, package or backend/mobile CSS coupling.
5. Add `artifacts/sweet-seats/src/pages/style-guide.tsx` and a development-only route in `App.tsx`. Extend the current test harness to handle the development flag and verify production excludes this route.
6. Deliver a review artifact: screenshots of both frontends and the development guide, a short list of intentional typography/color/control changes, actual checks and unresolved issues. Final logo production is a separate later item after the reference is supplied: stacked/horizontal, optical symbol, PNG/SVG/monochrome/favicon/app-icon variants. It does not gate A acceptance.

Acceptance: both web frontends consume one token source; navy/cream/coral/teal and sans-serif direction are reviewable in the guide; no glow; coral buttons use tested navy labels; normal/error/warning/focus/disabled states are visually distinct and text-labeled. Existing page content, API contract, routes, reciprocal links, search, timestamps and demo limitations remain intact. Keep page-layout regeneration out of this increment.

Verify: both existing frontend tests/typechecks/builds; targeted guide/nav/semantic-token checks; one visual pass across 320/390/768/1024/1440 widths, keyboard focus, long strings, contrast and reduced-motion preference. Reuse solid-color calculations but test rendered states. Shared typography/colors may change intentionally; do not change discovery logic.

Dependency: logo approval blocks final logo assets only; web foundation can proceed with the existing explicitly temporary mark. Mobile uses React Native styles, not CSS: defer matching native constants until a later targeted alignment, without inventing automatic CSS sharing. Existing mobile typecheck and managed-workflow failures have separate maintenance ownership and release gates, recorded in the review; passing A's web checks does not mean the repository or deployment is healthy.

### B — Public website

Adapt `artifacts/sweet-seats-coming-soon/src/pages/home.tsx`, `src/styles.css`, `index.html`, and approved `public/` logo variants to the foundation. Reuse imported structure/copy/artwork; retain source references. Explain product, illustrative synthetic preview and truthful development status. One primary “Explore the demo” action goes to `/`; secondary content links may remain.

Acceptance: meaningful descriptor near logo, responsive hierarchy, working CTA and reciprocal navigation, no fake testimonials/launch dates/savings claims/email fields. No beta CTA until submission, consent, approved storage destination and success/error handling are separately implemented.

Verify: existing two route tests extended for the approved branding/CTA, typecheck/build, one desktop/mobile check including keyboard, image semantics and overflow. No backend or form dependencies.

### C — Discovery and filters

Adapt `artifacts/sweet-seats/src/app/page.tsx`, `discovery.tsx`, `events/event-page.tsx`, `demo-notice.tsx` and `globals.css` using A. Split the large discovery file into focused feed/detail/filter modules only as touched, retaining existing exports/tests or intentionally updating imports.

Start with date/location filters over loaded results, explicitly page-scoped. Display “Filtering this page’s N events,” retain pagination while filters are active, and use “No matches on this page” rather than implying an empty catalog. Explain that another page may contain matches. Extract a pure filter helper such as `src/app/discovery-filters.ts`; preserve timezone/DST/TBA. If whole-feed search is wanted, plan a separate contract change in `services/api/app/main.py: events`, `lib/api-spec/openapi.yaml`, generated client and all consumers. Do not silently change pagination totals or call page filtering global search.

Acceptance: useful no-match/clear-filter recovery; cancellation, source health, stale evidence and sold-out remain separate; long names wrap; unknown times stay TBA; identities under review remain explicit. Refresh does not change observed timestamps. Preserve loading, empty, partial, unavailable, blocked and missing-event behavior.

Verify: pure filter tests for date boundaries/DST/TBA and combinations, active-filter pagination and predictable reset/preservation when changing pages, existing render tests and browser smoke (`scripts/sweet-seats-smoke.mjs`) extended with filters/clear. Only rerun Python/API contract tests if those contracts change.

Spec tension to resolve: Base44 uses a fixed demo clock; Replit currently evaluates real observation freshness against the current clock. Default: retain true current-clock stale behavior. Any fixed illustrative clock must be explicit and separate, not reset old observation timestamps.

### D — Following and Saved (separate opt-in demo increment)

First compare the Base44 export. Adapt proven service behavior if available; otherwise build only the small behavior needed, not its TanStack/Base44 runtime. Proposed seam: `src/features/demo/{types,service,storage,identity}.ts`, a provider/hook, and new artist/Following/Saved pages wired into `AppRoutes`.

Follow keys canonical artist IDs; Save keys canonical event IDs. Require reviewed explicit mapping from Base44 fixture IDs; no artist-name merge. Store event references and overlay refreshed event state rather than freezing old “scheduled” snapshots. Keep unavailable/suppressed records withheld while retaining permitted shortlist intent; do not leak data after a permission change.

Default: labeled browser/device-local synthetic persistence with a versioned namespace, no cross-origin transfer and no account-sync claim. Use per-item queues, action-scoped optimistic rollback and reset fencing only where justified; storage exceptions must disclose memory-only behavior.

Acceptance: save/follow then reload; remove then reload; counts consistent across pages; failed writes restore only that action, not an unrelated success; concurrent unrelated actions remain independent; same-item conflicting writes cannot reorder; reset cannot be overwritten by late writes. Saved cancelled/postponed shows keep updated status. Ambiguous identities block Follow. Following never subscribes to alerts.

Verify: service/storage unit tests including denied/quota/corrupt storage and restart/reset; one focused interactive pass for save/remove/reload, rollback/concurrency and current status retention. Keep all sample data labeled. No server account writes or notification permissions.

### E — Independently scoped live-readiness increments

These are separate deliverables, not one chain and not an extension of a style change:

| Increment | Files/seams and dependencies | Acceptance and verification |
|---|---|---|
| E1 Account persistence | Review `auth.py`, `me.py`, Supabase signing/RLS, approved durable storage/migrations, deletion and explicit device-demo→account import semantics. Event saves require additional schema/API work. No auth-provider substitution. | Verified sign-in/session expiry, isolated users, account-backed follow/save persistence, failed-mutation recovery and deletion; disposable PostgreSQL/RLS tests and targeted authenticated UI pass. No cross-user data access. |
| E2 Permitted live discovery | Existing source registry/adapters, stable identities, approved collect/display/retain rights, server-side configuration and operational scheduling. Does not require E1 for public discovery if permission permits. | Correct provenance/freshness, expiry/revocation withholding, distinct source errors and cancellation states; adapter/permission tests and approved-environment recovery checks. A key or pending license is insufficient. |
| E3 Notification delivery | Review `alerts.py` and durable eligibility/outbox/leases/retries; requires verified recipient identity, channel-specific consent, revocation/quiet hours and permitted event evidence. Account integration normally depends on E1; live messages depend on E2 or another explicitly permitted data source. | No delivery from Follow alone, correct consent/revocation/deletion, idempotent durable sends and recovery, queued distinct from delivered; transport mocks first and separately authorized live tests only. |
| E4 Optional beta intake | Approved storage destination, privacy/retention notice, consent scope, server validation/rate limits and success/error handling. Can be delivered independently of E1–E3; it need not wait for alert delivery. | Real submission recorded once, invalid/failed submissions recover truthfully, deletion/retention behavior verified, no automatic alert subscription or fake success state. Focused endpoint/form tests. |

Each needs separate owner approval and operational review. No production migration or real send merely to demonstrate readiness; no successful anonymous GET is “account readiness.”

## 5. Baseline results from this planning pass

| Existing check | Actual result |
|---|---|
| `pnpm --filter @workspace/sweet-seats test` | PASS, 10/10 |
| `pnpm --filter @workspace/sweet-seats-coming-soon test` | PASS, 2/2 |
| Both web `run typecheck` | PASS |
| Both web production builds, artifact-declared PORT/BASE_PATH | PASS |
| `pnpm --filter @workspace/scripts exec node --import tsx --test ../lib/api-client-react/tests/custom-fetch.test.mjs` | PASS, 4/4 |
| `pnpm --filter @workspace/sweet-seats-mobile run typecheck` | FAIL, 15 errors in 3 files, starting with missing discovery exports as resolved from the shared API client |
| GET `/`, `/coming-soon/`, first `/events/:eventId`, discovery API | PASS, HTTP 200; 3 synthetic/stale events |
| Representative Chromium screenshots | Captured at 1280×900: public, discovery, detail and dedicated not-found; actual headings verified |
| Managed discovery workflow | FAILED with “Port 24689 is already in use,” despite the proxy page responding. No process killed or workflow/config repair performed. |

The mobile generated source contains discovery hooks/types, but the current `lib/api-client-react/dist/generated/*.d.ts` lacks them; the mobile TypeScript project references that package. Stale declaration output is a likely narrow explanation, not a confirmed code defect. First authorized follow-up should check/build the referenced declaration project and rerun mobile typecheck before editing components or reinstalling dependencies.

Screenshots: `generated-artifacts/planning/{public,discovery,event,not-found}.png` (ignored generated output). This pass captured/read pages only; it did not repeat the full interactive smoke suite, run mobile/native export/Expo Doctor, backend unit/DB suites, or production checks. The prior repair's interactive results are recorded separately in `docs/repair-validation.md`, not claimed as newly rerun here.

No provider credentials or private user records were inspected. No package installation, source/codegen change, application edit, workflow repair, data migration, deployment or live delivery occurred.

## 6. Effort and credit discipline

These are engineering effort bands, **not credit quotes, billing guarantees or delivery commitments**. One focused day means roughly 4–6 hours of engineering work; actual agent credit use varies with model, retries, media generation and browser runs.

| Increment | Rough effort band | Main cost/risk drivers |
|---|---|---|
| A: tokens, small shared layer, guide | 0.5–1.5 focused days; logo production separately 0.5–1 day after reference | Repeated logo generations/variant exploration; avoid until reference approved |
| B: public site adaptation | 0.5–1 day | Responsive refinement, accessible artwork, changed marketing copy |
| C: discovery UI + loaded-page filters | 1–2 days | State preservation, dates/DST, test coverage; global API search adds scope |
| D: device-local Follow/Save | 2–4 days after usable export; more if rebuilding | Identity mapping, rollback/races, storage failure and integration tests |
| E1: account persistence | 2–4+ days after infrastructure approval | Auth/RLS, migrations, isolation and deletion |
| E2: permitted live discovery | 2–4+ days per initial approved source | Rights, identity mapping, scheduling and recovery |
| E3: notification delivery | 2–4+ days after recipient/data/consent prerequisites | Durable delivery, revocation, retries and operational recovery |
| E4: optional beta intake | 0.5–1.5 days with an approved destination | Validation, scoped consent, retention and genuine success/error behavior |

Do one coherent change and verification pass per approved increment. Reuse current frameworks, components, artwork, fixtures, contracts and tests. Avoid parallel full-app rebuilds, whole Base44 runtime imports, new registries/Storybook, repeated broad browser tests, or generating media before logo approval. Recheck current failures and queued-agent work before spending on implementation.

## 7. Material decisions with recommended defaults

| Decision | Recommended default | Blocks |
|---|---|---|
| Authoritative visual target | SS-BRAND-UI-1.1, navy/cream/coral/teal, flat mark, sans-serif; old proposal superseded | Approval to implement A, not this plan |
| Missing logo | Upload latest flat navy reference; keep current mark explicitly provisional until approved | Final logo assets, not tokens/guide |
| Shared UI scope | Web first; native keeps working behavior and gets a later deliberate style mapping | No web block |
| Search scope | Loaded-page date/location filters first, clearly labeled | Whole-feed search only |
| Follow/Save persistence | Device-local synthetic mode first, no account or notification claim | Approval before D |
| Base44 source access | Upload the selective code/test export; do not assume public URL grants code access | Verbatim service reuse; not A–C |
| Beta geography | Carry forward five boroughs + Hudson County **event catchment** from the authoritative area's v1 table in `docs/superpowers/specs/2026-10-27-nyc-audience-audit-design.md`. That record separately limits eligible audience to NYC five boroughs. Do not conflate them or re-ask unless records conflict/scope changes. | New geographic enforcement only; not A |
| Demo clock | Keep current real-clock staleness; never make old evidence fresh | Optional new fixed-clock demo scenarios |
| Live accounts/providers/alerts | Separate approvals, original backend and licensed contracts first | E only |
| Pending style/video work | Align its brief to this package before implementation/media generation | Avoids conflicting branding and duplicate credit use |

## 8. Risks and rollback approach

- Recheck HEAD/status before each edit batch; preserve unrelated changes and synced reference source. Stop if another agent edits the same files.
- Keep foundation changes reviewable and separate from marketing/discovery behavior. Review a checkpoint/diff before the next increment; use checkpoints if a substantial rollback is needed rather than deleting others' work.
- Do not alter URL ownership, API envelopes, original event/artist IDs, observation clocks, permission rules or the existing database during visual work.
- Keep backend providers/secrets server-side. A key, pending license or sample preview is not permission to collect/display/store live content.
- Accessibility remains an acceptance process, not a label earned by the supplied contrast table. Validate keyboard, focus, reduced motion, mobile layout and actual rendered contrast.

## 9. Ready-to-use implementation prompt — increment A only

> Implement only the approved shared **web visual foundation** for the existing Sweet Seats discovery and coming-soon apps. First recheck Git state, queued styling/video work and overlapping edits; preserve all unrelated work. Use the uploaded SS-BRAND-UI-1.1 specification and semantic CSS tokens as the working direction: midnight navy, warm cream, coral actions with navy labels, teal supporting accents, bold friendly sans-serif and flat headphone/seat identity. The older `docs/brand-ui-proposal.md` is superseded. Do not claim the missing latest flat navy logo or vector variants exist: request the actual reference, keep the current mark provisional, and stop short of final logo exports until it is supplied/approved.
>
> Add one canonical scoped token source under `lib/sweet-seats-brand/`, minimal shared web brand/navigation/button/form/status primitives using existing tooling, and a compact development-only style guide. Have both current web frontends consume the same source; map existing CSS/Tailwind semantic aliases instead of copying palettes. Keep discovery `/`, details `/events/:eventId`, promotional `/coming-soon/`, dedicated accessible unknown-page handling, reciprocal links and the current API/backend behavior. Preserve original reference files/assets. Restrict changes to foundation styling/component wiring and guide/regressions—no wholesale page layouts or content regeneration.
>
> Retain page-scoped search, original timestamps/stale warnings, truthful refresh explanation, synthetic-demo disclosures, no-connected-waitlist wording and explicit missing account/ticketing capabilities. Do not add fake controls, live providers, forms, auth, persistence, schema changes, new registry dependencies, frameworks, another mobile app, pushes or publishing. Do not edit the merged Expo app or repair unrelated mobile/workflow issues without separate approval.
>
> First establish and verify direct shared TypeScript/CSS consumption through existing Vite/workspace source imports in both frontends before expanding primitives. Run both web frontend test suites, typechecks and builds with their declared artifact settings. Add focused assertions for shared source/guide production exclusion/navigation. Perform one visual/accessibility pass at 320/390/768/1024/1440 widths plus keyboard focus, reduced motion, long text and rendered contrast; extend existing smoke checks only for changed interactions. Record existing mobile typecheck and managed-workflow failures separately from new regressions, with separate maintenance follow-ups. Deliver the diff, actual check results, screenshots of both frontends and guide, intentional color/typography changes and unresolved logo/accessibility requirements. Passing web-foundation acceptance does not imply repository-wide or deployment readiness. Stop after A for review; final logo production and B–E are not part of A.
