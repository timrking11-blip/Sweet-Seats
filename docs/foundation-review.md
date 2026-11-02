# Increment A: shared web foundation review

Scope: shared tokens, native control/navigation/status styling and a development style guide only. B–E remain roadmap scope. No application/API/data/auth/provider or deployment changes are authorized by this review.

## Scope and integration

- Starting revision: `abcb128` on `main`, initially clean. No overlapping local edits were present before this pass.
- Searched existing project assets for “Flat Sweet Seats logo in navy.png” and other flat/navy/logo files. Only the original imported SVG was found; the supplied ZIP explicitly omits generated logo images. Existing marks remain provisional. Final logo production and the export catalog are separate and do not gate foundation acceptance.
- Canonical source: `lib/sweet-seats-brand/tokens.css`, based on the supplied specification.
- Shared framework-neutral TypeScript: `lib/sweet-seats-brand/foundation.ts`; native semantic markup and common CSS primitives avoid new package infrastructure.
- Both entry points directly import `../../../lib/sweet-seats-brand/foundation` and `tokens.css`. `applyBrandFoundation` scopes tokens on the document root. Existing Vite/workspace resolution and leaf TypeScript compilation include these sources.
- **Early integration proof:** both web typechecks and production builds passed immediately after adding these shared imports, before expanding the control/guide layer.
- No registry dependencies, package installation, new framework, or new artifact were required.

## Intentional changes for review

- Shared navy background, cream text, coral action fill with navy labels, teal supporting/focus color and semantic warning/error/success colors.
- Friendly sans-serif typography replaces discovery's serif foundation treatment; no new fonts are downloaded.
- Shared native link/button/input/status treatments and visible focus; minimum target size and reduced-motion handling.
- Existing page layouts, copy, demo limitations, reciprocal navigation and original illustrations/reference assets remain. This is not the public-site or discovery-layout redesign.
- Development-only `/style-guide` provides reviewable tokens, provisional mark treatments, typography, navigation, controls, status examples and disabled/form examples. Examples do not submit or pretend to be working accounts/waitlists.

## Separate existing failures and ownership

| Area | Baseline and evidence | Ownership and release implication |
|---|---|---|
| Mobile/shared declaration lifecycle | Initial mobile typecheck reproduced 15 errors in 3 files. Generated source had discovery exports, but referenced declaration output was stale. Running existing `pnpm run typecheck:libs` as standard shared-source validation regenerated declaration output; mobile typecheck then passed without source edits. | Separate build/merge-maintenance follow-up: make required shared declarations reproducible after merges. No Expo code/dependency changes belong to A. This is not a physical-device or mobile-release acceptance result. |
| Managed discovery service | Previously failed with port 24689 already occupied while the proxy still served discovery. No unrelated process was killed or port/workflow configuration changed. | Separate runtime-workflow follow-up: establish one managed server owner. Web foundation checks cannot establish workflow or deployment health. |

No full-repository or deployment-readiness claim follows from passing the web checks. Provider permissions, live-user auth/storage, notifications, physical devices, final logo assets and production readiness remain separate.

## Final evidence

| Check | Actual result |
|---|---|
| `pnpm run typecheck:libs` | PASS; regenerated existing workspace declarations |
| Mobile `pnpm --filter @workspace/sweet-seats-mobile run typecheck` before declarations | FAIL; same 15 stale shared-client declaration errors in 3 files |
| Mobile typecheck after `typecheck:libs` | PASS; no mobile source/dependency edits |
| Discovery frontend tests | PASS, 12/12 |
| Coming-soon frontend tests | PASS, 2/2 |
| Both web typechecks | PASS |
| Both Vite production builds with declared `PORT`/`BASE_PATH` | PASS |
| Production guide exclusion | PASS; built discovery JavaScript contains neither `/style-guide` route nor its development-guide marker |
| Foundation Chromium run | PASS, 15 page × viewport checks for 320, 390, 768, 1024 and 1440 px; includes canonical background/text/action tokens, sans-serif headings, action contrast/44 px target, swatch contrast and horizontal overflow |
| Focused guide rerun after swatch-contrast correction | PASS, 5 viewports; includes keyboard-visible focus, accessible labels/long field, disabled control, reduced-motion behavior, all swatch foreground/background contrast pairs ≥4.5:1, no browser exceptions |
| Existing discovery smoke | PASS, desktop 1280×900 and mobile 390×844: reciprocal links, exact-copy disclosures, unknown paths, event detail/deep link, page search, refresh preserving observations/freshness, stale/error/retry states and disabled ticket action |
| Managed discovery workflow | Initial managed workflow failure reported port 24689 busy; a subsequent single restart PASS and service stayed RUNNING in latest logs. No port/config/process changes made; do not infer permanent port ownership resolution. |
| Coming-soon workflow | PASS/restarted; stayed RUNNING with clean startup logs |
| Browser console | No JavaScript exceptions in either smoke run |
| `git diff --check` | PASS |

The first visual review caught low contrast for labels over teal and muted swatches. Their foreground was corrected to the supplied dark text color; the final guide smoke measured every swatch and passed. No color token or color value was changed.

Evidence screenshots, captured in Chromium at the listed CSS pixel width, are under `generated-artifacts/foundation/`:

- `public-1440.png`: entire promotional site.
- `discovery-390.png`: entire discovery page/mobile width.
- `guide-1440.png`: entire development style guide.
- `discovery-320.png`, `discovery-390.png`, `discovery-768.png`, `discovery-1024.png`, `discovery-1440.png`; corresponding `public-*` and `guide-*`: responsive visual test cases. The 390/1440 cases are full-page; other widths are viewport captures.
- `checks.json`, `guide-checks.json`: measured layout, contrast inputs, focus and reduced-motion evidence.

The web header uses the user-supplied Music Fan logo; final multi-format logo packaging remains separate. The development guide's example form does not submit. The old discovery orbs and the Lovable poster remain legacy illustrations, not substitutes for that supplied logo. This is not a full WCAG certification, physical-device check or deployment/release check.

Verification tooling:

```sh
pnpm run typecheck:libs
pnpm --filter @workspace/sweet-seats test
pnpm --filter @workspace/sweet-seats-coming-soon test
pnpm --filter @workspace/sweet-seats run typecheck
pnpm --filter @workspace/sweet-seats-coming-soon run typecheck
PORT=24689 BASE_PATH=/ pnpm --filter @workspace/sweet-seats build
PORT=18185 BASE_PATH=/coming-soon/ pnpm --filter @workspace/sweet-seats-coming-soon build
pnpm --filter @workspace/scripts run test:sweet-seats "https://$REPLIT_DEV_DOMAIN" [existing-chromium-executable]
pnpm --filter @workspace/scripts run test:sweet-seats-foundation "https://$REPLIT_DEV_DOMAIN" [existing-chromium-executable]
```

No backend/unit/DB suite is required for purely visual changes to an unchanged API. If scope changes, reassess verification rather than treating these commands as blanket acceptance. Mobile typecheck now passes after the standard declaration build, but physical-device readiness remains unverified. The workflow restarted and is running; long-term ownership of port 24689 remains outside A.

## Roadmap revisions, not implemented here

- Loaded-page filters in C must display the loaded page's event count, keep pagination available and distinguish “No matches on this page” from an empty catalog. Page changes need explicit filter reset/preservation tests.
- E is now split into independently approved account persistence, permitted live discovery, delivery and optional beta intake. Beta signup does not depend on alert delivery.
- Existing authoritative geography distinguishes five boroughs + Hudson County **event catchment** from NYC-only eligible **audience**. Carry those forward; re-ask only if records conflict or scope changes.
- A's shared source/style guide passed. New changes to the shared API client also need the composite declaration build; do not interpret a pre-build leaf typecheck as a mobile regression.
