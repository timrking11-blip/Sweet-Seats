# Form field

## Source

- Shared classes: `.ss-label`, `.ss-control`, and `.ss-help` in
  `lib/sweet-seats-brand/controls.css`.
- Active usage: discovery page search and the shared style-guide examples.

## Preserved behavior

- Native labels and inputs, with explicit `htmlFor`/`id` associations.
- Optional help text connected using `aria-describedby`.
- Visible focus, a minimum 44px control height, and an invalid state that can
  be described in text.

The story is disconnected by design; it is not a waitlist or submission form.
