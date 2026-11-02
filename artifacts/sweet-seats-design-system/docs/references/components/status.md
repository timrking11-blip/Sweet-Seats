# Status message

## Source

- Shared class: `.ss-status` with `warning`, `error`, and `success` tones in
  `lib/sweet-seats-brand/controls.css`.
- Active usage: discovery partial/unavailable/permission-blocked states and
  shared style-guide examples.

## Preserved behavior

- Errors default to `role="alert"`; warnings and success messages default to
  `role="status"`.
- Event cancellation/sold-out state remains separate from source collection
  health and observation freshness.
- Existing observation times are not replaced by a feed refresh.

Examples in the design-system preview are static and are not live source
health checks.
