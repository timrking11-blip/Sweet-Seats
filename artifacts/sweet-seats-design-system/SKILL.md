# Sweet Seats Design System

This package is a standalone, source-backed system for Sweet Seats. It does
not change or replace any existing app screen.

## Source precedence

1. The current user-supplied Sweet Seats brand and UI specification.
2. `lib/sweet-seats-brand/tokens.css` and `controls.css`, the active shared
   foundation and control styles.
3. Active discovery and coming-soon call sites for usage and semantics.
4. The uploaded logo image, retained at
   `docs/references/logos/sweet-seats-music-fan-logo.png`.

The former `docs/brand-ui-proposal.md` is superseded and is not a source for
these tokens. Stock shadcn modules in the app artifacts are not included:
product screens do not consume them; the active shared source is the
framework-neutral Sweet Seats foundation.

## Theme and tokens

- Midnight Session is the canonical theme: navy `#031126`, cream `#FFF1DD`,
  coral `#FF624D`, and teal `#67BCAF`.
- The light theme in `tokens.json` is a derived preview companion. It is not
  approved for product use. Keep that distinction visible wherever it appears.
- `tokens.json` is the only token source. Edit it, then run `pnpm tokens`;
  never hand-edit generated theme files.
- Use the system sans stack. Do not load a remote font or use a serif display
  treatment.
- Use 4px spacing increments, 12px controls, 16px independent cards, visible
  focus, and at least 44px interactive targets.
- Contrast evidence and limits are documented in
  `docs/references/contrast-checks.md`. The light theme has selected computed
  pairs, not a full accessibility audit.

## Components and content

- Keep product-agnostic controls here. Page layouts, navigation, discovery
  states, event data, and feature behavior remain in their app.
- Preserve native links, buttons, labels, inputs, and live-region semantics.
- Do not show a working-looking action for a feature that does not exist.
- Keep event status separate from source health. A fetch failure or stale
  observation does not mean canceled or sold out.
- Do not imply that a refresh creates a new observation time.
- Prefer specific, familiar words such as show, artist, venue, source, and
  checked. Avoid coverage guarantees, artificial urgency, guaranteed savings,
  and unvalidated predictions.
- The stories are static design references, not connected product controls.

## Logo

Keep the supplied raster artwork proportional on a quiet, solid background.
It is a reviewable image, not an editable vector master. Do not shrink the
detailed stacked mark into a favicon or claim that production logo variants
are complete.

The family inventory and source references are in
`docs/references/component-inventory.md` and
`docs/references/components/`.

The web component stories are web-only. The generated token object is portable
for other platforms; no native components have been added and the Expo app is
unchanged.
