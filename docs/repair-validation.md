# Sweet Seats minimal repair evidence

Inspection/validation date: 2026-11-02.

## Starting state and boundaries

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
- Shared branding requires review/approval before implementation. There is no connected waitlist.
- Live-user launch still requires approved durable storage/migrations, verified auth/account UI and authorization, permitted live data and freshness controls, saved/follow/alert implementations with consent, approved ticket functionality, and operational/privacy/security/device/accessibility review. This repair does not establish live-user readiness.
