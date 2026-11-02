# Sweet Seats shared brand/UI specification

Status: approved and applied to the Sweet Seats discovery web artifact using the existing `artifacts/sweet-seats-design-system` package. The coming-soon site and mobile artifact were not changed.

## Directions before the approved web pass

| Area | Discovery demo before redesign | Imported Lovable brand page, unchanged |
|---|---|---|
| Background / text | Night `#100c19`, secondary `#191124`, cream `#f6f1eb` | Ink `#15161a`, charcoal `#1f2026`, cream `#f3f0e8` |
| Accents | Violet `#a97cff`, coral `#ff8568`, gold `#f7ca70` | Coral `#ff8968`, muted `#b9b5ab`, rule `#34353c` |
| Typography | Georgia editorial headings and wordmark; sans-serif UI | Heavy sans-serif display headings and sans-serif UI |
| Assets / layout | Orb and ticket artwork, provenance-rich event cards | Imported SVG logo and concert-poster artwork, spacious landing sections |
| Purpose | Explore clearly synthetic event observations and their evidence | Explain the future product and link to the demo |

The Lovable page retains its original visual direction. The discovery web artifact now uses the approved shared system rather than the earlier discovery palette above.

## Approved shared specification

- Brand promise: NYC-area live music discovery with clear sources. Never imply ticket inventory, personal accounts, or notifications are active when they are not.
- Palette and typography: use only the canonical-dark tokens and typography exported by the shared design-system package.
- Logo: use the supplied Music Fan logo asset in the shared package; final multi-format logo packaging remains a separate deliverable.
- Navigation: permanent, visible links between brand and demo at desktop and mobile sizes; use native links rather than hidden or nonfunctional controls.
- Components: use the shared buttons, links, fields, and status messages; preserve semantic landmarks, visible form labels, focus outlines, touch targets, and mobile wrapping.
- Data language: label synthetic data, show original observed timestamps and stale warnings, distinguish empty/blocked/error states, and explain that refresh only rereads stored observations.
- Scope language: page-scoped search; no connected waitlist; explicitly list unavailable account and ticketing features. Avoid optimistic “join,” “buy,” or “follow” buttons until connected behavior exists.
- Required states: loading, ready, empty, partial/unavailable, permission-blocked, missing event, unknown page, and retry. Do not use a source failure as proof of sold-out tickets or no events.

## Applied scope

- The shared system is applied to discovery, event detail, not-found, and the development-only style guide screens.
- The selected three-column discovery direction is also re-homed under the design-system mockup entry.
- The coming-soon page, mobile screens, routes, and API behavior were left unchanged.
- No live providers, authentication, ticket purchases, or waitlist behavior were added.
