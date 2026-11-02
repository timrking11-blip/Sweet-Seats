# Lovable import

Imported from `https://github.com/timrking11-blip/sweet-seats-coming-soon.git`.

This is a one-time source import, not a live Lovable or GitHub synchronization.
The Windows ZIP path supplied in chat was not an uploaded attachment and was not imported.

## Run and check

- Preview: `/coming-soon/`
- Managed workflow: `artifacts/sweet-seats-coming-soon: web`
- Tests: `pnpm --filter @workspace/sweet-seats-coming-soon test`
- Types: `pnpm --filter @workspace/sweet-seats-coming-soon run typecheck`

## Preservation

The original landing-page copy, artwork, logo, styles and founder links are retained.
The static landing page no longer depends on TanStack Start, Lovable-hosted error reporting or a server runtime.
Routes, home links and public assets honor the `/coming-soon/` preview prefix.
No database, authentication or backend integration was present or added.

`imported-src/` retains the original source for comparison and is not part of the active app.
`IMPORTED-README.md` retains the repository README.
A full original repository source archive is retained locally at
`generated-artifacts/imports/sweet-seats-coming-soon-original.tar.gz` (outside Git and published output).
