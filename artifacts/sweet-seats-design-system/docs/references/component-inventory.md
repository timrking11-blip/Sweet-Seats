# Sweet Seats component inventory

## Source scope

The component source is the active, framework-neutral
`lib/sweet-seats-brand/controls.css`, used by the discovery UI and coming-soon
page. The app artifacts also contain generic shadcn scaffold files, but the
active screens do not import those modules. They are not part of this branded
component inventory.

Source usage was checked in the active page files. The inventory ranks the
families by the number of active screen or reference-page files using them.

| Rank | Family | Active source usage | Reference |
|---|---|---:|---|
| 1 | Button | 5 files; 7 matched occurrences | [Button](components/button.md) |
| 2 | Link | 3 files; 4 matched occurrences | [Link](components/link.md) |
| 3 | Field | 2 files; label/control/help parts | [Field](components/field.md) |
| 4 | Status message | 2 files; multiple freshness/source states | [Status](components/status.md) |

The implementation preserves native HTML semantics and the shared visual
rules. The preview contains one family story for each inventory entry.

## Source files

- `lib/sweet-seats-brand/controls.css` — shared link, button, field, status,
  focus, and reduced-motion rules.
- `artifacts/sweet-seats/src/app/discovery.tsx` — discovery search, refresh,
  collection status, and disabled ticket action examples.
- `artifacts/sweet-seats/src/app/page.tsx` and
  `artifacts/sweet-seats/src/pages/not-found.tsx` — discovery calls to action.
- `artifacts/sweet-seats/src/pages/style-guide.tsx` — documented shared
  control and state examples.
- `artifacts/sweet-seats-coming-soon/src/pages/home.tsx` — brand-page links
  and call to action.

## Two existing visual contexts

See [visual directions](visual-directions.md). The component library contains
shared visual primitives, not the product-specific page compositions.
