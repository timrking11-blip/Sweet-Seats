# Sweet Seats

NYC-area live music discovery with source provenance, migrated from the imported Next.js/Python project to a pnpm workspace.

## Run and verify

- Frontend managed workflow: `artifacts/sweet-seats: web`.
- Backend managed workflow: `artifacts/api-server: API Server`.
- `pnpm --filter @workspace/sweet-seats test` checks the original discovery UI states.
- `pnpm --filter @workspace/scripts run test:sweet-seats http://localhost:80 [chromium-executable]` runs the browser smoke checks; omit the executable when Playwright browsers are installed. Screenshots go to ignored `generated-artifacts/migration/`.
- `uv run --frozen python -m pytest services/api/tests tests -q` checks the original Python suite. Database-dependent tests require an explicitly configured disposable local PostgreSQL database and otherwise skip.
- `pnpm --filter @workspace/sweet-seats run typecheck` and `pnpm --filter @workspace/api-server run typecheck` check artifact types.
- API probes go through the shared proxy: `http://localhost:80/api/discovery/events`.
- Run workflows, not a workspace-root development command. Managed workflows provide `PORT` and `BASE_PATH`.

## Structure

- `artifacts/sweet-seats`: Vite + React app; original CSS and components in `src/app`. Routes `/` and `/events/:eventId`.
- `artifacts/sweet-seats-coming-soon`: separately imported Lovable landing site at `/coming-soon/`; see its `IMPORT.md`. Its branding is preserved independently of the discovery demo.
- `artifacts/api-server`: Express entry point. Forwards `/api/discovery/*` to the original Python `/v1/*`, and `/api/v1/*` to `/v1/*`, using a private Unix socket.
- `services/api`: preserved FastAPI application and Python domain logic. `replit_server.py` starts it and initializes the original synthetic fixture only if no JSON store exists and no database is configured.
- `tests/fixtures/discovery/nyc.json`: original invented event data.
- `supabase`, `db`, `jobs`, `adapters`, `docs`: preserved original migrations, backend logic and governance documents.
- `.migration-backup`: original imported tree, retained for reference and excluded from publishing.

## Migration decisions and limits
- Keep the Lovable coming-soon site separate from the discovery app.
  **Why:** importing another version must not overwrite the working discovery experience or redesign either source.

- Preserve the Python service rather than translate its identity reconciliation, permissions, authentication and persistence rules into TypeScript.
  **Why:** a rewrite would risk changing the imported product's safety and data contracts. Express owns the managed API port and supervises the Python process; build installs Python dependencies from `uv.lock`.
- Keep the existing JSON demo mode unless the owner explicitly configures original PostgreSQL storage. Never connect, replace or migrate an external database automatically, and never silently fall back from a configured database.
  **Why:** the import's local preview is fixture-backed; database provisioning and hosted services were not activated.
- No live source, paid research call, user notification, predictive advice or new authentication provider was activated by the migration. Existing Supabase token verification remains unchanged and unavailable without its original configuration.
  **Why:** the imported product explicitly gates provider use, permissions, consent and production infrastructure behind owner approvals.
- Synthetic observations keep their original dates and freshness evidence. Refreshing the feed does not fabricate fresh observations.
- JSON state under `.local/discovery.json` is a single-writer local demo, not production persistence. Do not publish it as a live multi-user service without separately provisioning approved durable storage.

See `README.md` and `docs/contracts/` for original product scope and contracts; references to Next.js/Vercel in those historical documents describe the imported stack, not the active Replit frontend.
