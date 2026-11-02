# Sweet Seats shared brand/UI proposal — review required

Status: proposed only. No shared tokens, framework changes, assets, or visual redesign have been applied.

## Existing directions

| Area | Discovery demo | Imported Lovable brand page |
|---|---|---|
| Background / text | Night `#100c19`, secondary `#191124`, cream `#f6f1eb` | Ink `#15161a`, charcoal `#1f2026`, cream `#f3f0e8` |
| Accents | Violet `#a97cff`, coral `#ff8568`, gold `#f7ca70` | Coral `#ff8968`, muted `#b9b5ab`, rule `#34353c` |
| Typography | Georgia editorial headings and wordmark; sans-serif UI | Heavy sans-serif display headings and sans-serif UI |
| Assets / layout | Orb and ticket artwork, provenance-rich event cards | Imported SVG logo and concert-poster artwork, spacious landing sections |
| Purpose | Explore clearly synthetic event observations and their evidence | Explain the future product and link to the demo |

These are two implemented visual directions, not evidence of an approved shared specification.

## Proposed shared specification

- Brand promise: NYC-area live music discovery with clear sources. Never imply ticket inventory, personal accounts, or notifications are active when they are not.
- Candidate shared palette: the brand page's ink, cream, and coral as primary colors; retain discovery gold for caution/staleness and violet as an optional supporting accent. Review contrast before adopting any pairing.
- Candidate typography: keep the imported logo; use one sans-serif family for navigation, controls, and body text. Decide whether Georgia remains an editorial discovery accent or headings become consistently sans-serif. No new font dependency is proposed for the repair.
- Navigation: permanent, visible links between brand and demo at desktop and mobile sizes; native links rather than hidden or nonfunctional controls.
- Component rules: consistent spacing, focus outlines, buttons versus links, comfortable touch targets, and mobile wrapping. Preserve semantic landmarks, one page heading, visible form labels, and understandable error recovery.
- Data language: label synthetic data, show original observed timestamps and stale warnings, distinguish empty/blocked/error states, and explain that refresh only rereads stored observations.
- Scope language: page-scoped search; no connected waitlist; explicitly list unavailable account and ticketing features. Avoid optimistic “join,” “buy,” or “follow” buttons until connected behavior exists.
- Required states: loading, ready, empty, partial/unavailable, permission-blocked, missing event, unknown page, and retry. Do not use a source failure as proof of sold-out tickets or no events.

## Decisions needed before design implementation

Approve or amend the primary palette, heading typography, logo usage, and shared navigation wording. Then scope a targeted visual alignment pass rather than replacing either working build.
