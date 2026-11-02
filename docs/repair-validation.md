# Sweet Seats minimal repair evidence

Inspection/validation date: 2026-11-02.

## Original repair starting state and boundaries

- These statements describe the original repair pass before the follow-on design-system application below.
- Started from clean `main` at `18d83764dfd12292bdcd9b0bb7590dfbd0df53f7`. The same HEAD remained at the final concurrency check; only the repair's frontend, test, script, and documentation edits were visible.
- Discovery remains at `/`, the one-time Lovable import remains at `/coming-soon/`.
- No backend/API implementation, dependencies/lockfile, original imported source, logo, or artwork changed.
- No secret values were read, database writes/migrations performed, providers/auth activated, purchases made, GitHub pushes made, or publishing performed. Only the two frontend development workflows were restarted.

## Changed areas

- Discovery `App.tsx` and `pages/not-found.tsx`: explicit root and event routes, dedicated accessible unknown-page fallback, native return-home link.
- Discovery `app/page.tsx`, `events/event-page.tsx`, `demo-notice.tsx`: visible brand navigation and explicit missing account/ticketing capabilities.
- Discovery `app/discovery.tsx`: refresh help text linked with `aria-describedby`; page-only search and existing stale/timestamp behavior retained.
- Discovery CSS: small navigation wrapping and refresh-help layout additions using existing colors/styles.
- Coming-soon `src/pages/home.tsx`: real demo CTA and “No connected waitlist” disclosure; original assets and visual treatment retained.
- Frontend regression tests and `scripts/sweet-seats-smoke.mjs`: routing, disclosures, navigation and data-honesty coverage.
- `replit.md`: active runtime, imports/provenance, safety constraints and launch prerequisites.
- `docs/brand-ui-proposal.md`: two-direction inventory and proposed shared specification, for review only.

## Actual results

| Check | Result |
|---|---|
| Discovery frontend Node tests | PASS — 10/10, including root versus unknown routes, event route matching, search/refresh wording and stale timestamp retention |
| Coming-soon frontend Node tests | PASS — 2/2, including demo CTA/no waitlist and existing scoped 404 |
| Discovery TypeScript | PASS |
| Coming-soon TypeScript | PASS |
| Both Vite production builds | PASS with each artifact's declared `PORT` and `BASE_PATH` supplied |
| Interactive Chromium, desktop 1280×900 | PASS |
| Interactive Chromium, mobile 390×844 | PASS |
| Screenshot checks | PASS — mobile discovery and desktop coming-soon retained their existing visual directions |
| Workflow/browser logs | Frontends running cleanly; no browser exceptions in smoke checks |
| `git diff --check` | PASS |

Interactive checks exercised reciprocal navigation from home and event detail, visible scope/feature disclosures, missing discovery URLs (`/inspection-unknown-route`, `/events`, `/events/one/extra`), coming-soon unknown URL, valid event deep-link reload, absent-event recovery, matching/no-match search, refresh, stale warnings, disabled ticket action, unavailable-source messaging, HTTP 503/retry recovery, and horizontal overflow at both viewport sizes.

Refresh assertions compared original `observed_at`, `available_at`, `fresh_until`, stale flags and source records before/after, plus displayed time attributes. The existing synthetic feed had three stale events. Unavailable/503 scenarios used browser-local response interception, not modified server state. No server data mutations were issued.

Initial validation found a case-sensitive render-test expectation (`datetime` versus React's serialized `dateTime`) and a shell build invocation missing required artifact environment. The test expectation was corrected; builds were rerun with the existing declared settings. Final relevant tests/builds pass; no framework or configuration change was needed.

## Reproduce with existing tooling

```sh
pnpm --filter @workspace/sweet-seats test
pnpm --filter @workspace/sweet-seats-coming-soon test
pnpm --filter @workspace/sweet-seats run typecheck
pnpm --filter @workspace/sweet-seats-coming-soon run typecheck
PORT=24689 BASE_PATH=/ pnpm --filter @workspace/sweet-seats build
PORT=18185 BASE_PATH=/coming-soon/ pnpm --filter @workspace/sweet-seats-coming-soon build
pnpm --filter @workspace/scripts run test:sweet-seats "https://$REPLIT_DEV_DOMAIN" [existing-chromium-executable]
```

Omit the executable argument when Playwright already has its own Chromium. This pass used the existing system Chromium without installing anything. Browser screenshots are in ignored `generated-artifacts/migration/{desktop,mobile}-{brand,feed}.png`.

## Limits and outstanding prerequisites

- This is a client-side not-found screen. The SPA host can still return HTTP 200 for an unknown URL's HTML shell; server-side HTTP 404 semantics were not changed.
- The mobile result is a Chromium viewport check, not a physical phone or full accessibility audit.
- Production builds were compiled, but no production deployment or production data was inspected.
- Existing backend unit/DB suites were not rerun: no backend behavior changed, and the interactive run exercised its existing read-only event endpoints. Real authentication, account writes, purchases, alerts and live providers were neither activated nor tested.
- Base44 origin remains unverified; no Base44 source import, SDK or reference was found. Lovable is a one-time source import, not account-wide or continuous synchronization.
- The shared web style is now user-approved and applied to the discovery screens. There is no connected waitlist.
- Live-user launch still requires approved durable storage/migrations, verified auth/account UI and authorization, permitted live data and freshness controls, saved/follow/alert implementations with consent, approved ticket functionality, and operational/privacy/security/device/accessibility review. This repair does not establish live-user readiness.

## Follow-on approved design-system application (2026-11-02)

- Linked the existing canonical-dark design-system package to the discovery web artifact and used its exported tokens, buttons, links, fields, and status messages on discovery, event-detail, not-found, and development-guide screens.
- Re-homed the selected three-column canvas mockup under the design-system entry and removed the old component after confirming the canvas frame pointed to the new entry. The supplied Music Fan logo is included as a shared package asset; the original uploaded image remains preserved.
- The `/` discovery route, `/coming-soon/` brand page, event routes, backend/API behavior, and synthetic-data boundaries remain intact. The coming-soon and mobile artifacts were not changed; no provider, authentication, database migration, purchase flow, GitHub push, or publish was performed.
- Updated the shared brand/UI specification from proposal status to the user-approved web scope. The active runtime, one-time Lovable import, unverified Base44 provenance, and launch prerequisites remain documented in `replit.md`.

| Follow-on check | Result |
|---|---|
| Sweet Seats frontend tests | PASS — 13/13, including missing/error/empty/partial/blocked feeds, page-scoped search copy, refresh limitation, stale timestamps, route fallback, and design-system consumption |
| Sweet Seats, mockup sandbox, and design-system typechecks | PASS |
| Production builds for Sweet Seats, mockup sandbox, and design system | PASS with each artifact's declared `PORT` and `BASE_PATH` supplied |
| Interactive Chromium smoke, desktop 1440×900 and mobile 402×874 | PASS — reciprocal navigation, loaded-page search, stored-feed refresh, unchanged observation timestamps, event detail, stale warning, disabled ticket action, unknown URL, disclosure visibility, and no mobile horizontal overflow |
| Feed error/unavailable states | PASS — covered by existing frontend render tests; no live provider was activated |
| Screenshot checks | PASS — discovery desktop/mobile, event detail, not-found, development guide, and re-homed mockup |
| Browser exceptions and `git diff --check` | PASS — no uncaught browser errors; no whitespace errors |

The design-system build first stopped because `PORT` and `BASE_PATH` were omitted from the shell invocation; it passed on rerun with the configured artifact values. No workflow or application configuration was changed to address that invocation issue.

### Current limits

- The shared design system is applied to the discovery web screens only. The imported coming-soon page and the separate Expo app retain their existing designs.
- The mobile result is a Chromium viewport check, not a physical-phone test or full accessibility audit.
- The discovery is still a synthetic demo and is not live-user ready. Launch still requires approved durable storage and migrations; verified authentication and authorization; permitted live data and freshness controls; saved events, follows, and consent-based alerts; approved ticket-link behavior; and operational, privacy, security, device, accessibility, and production-readiness review.
- There is no connected waitlist, live event source, live ticket link, or purchase flow. Base44 provenance remains unverified, and Lovable is a one-time source import rather than ongoing synchronization.
