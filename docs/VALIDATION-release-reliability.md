# Release reliability repair

Prepared against upstream `f5bcac4839a4a6fcdd184116dbcf4635db04302b`.
No provider activation, deployment, hosted database access, credentials or UI change.

## Repairs

- Backfill `legacy_delivery_failed` before validating the historical alert constraint.
  This intentionally repairs the existing migration: a later migration cannot run if
  an upgrade stops at this earlier constraint. Already-applied schemas need no new
  schema change, and no hosted migration was applied in this task.
- Retain the active socket independently of `HTTPConnection.sock`; support HTTP/1.0,
  explicit connection-close and EOF-delimited bodies without dereferencing a cleared
  connection socket or touching it after the response closed it.
- Register the TLS socket before handshake, shut down that socket on the deadline,
  close response/socket resources and join the watchdog during cleanup.
- Limit outstanding blocking resolver/transport operations to four per process. A
  resolver that cannot be cancelled retains its slot until it returns. Capacity
  exhaustion fails closed as `operation_capacity_exceeded`.

## Regression evidence

Before the repairs, the first regression run reproduced six failures: connection-close
body handling (three cases), real TLS slow-header deadlines (two cases), and unbounded
outstanding blocking operations. Tests were then expanded to cover TLS success and
slow-body cleanup as well as plain HTTP.

Final local checks (Python 3.12):

- `python -m pytest services/api/tests -q`: 246 passed, 107 skipped. Skips require a
  disposable PostgreSQL connection, including the new populated-upgrade regression.
- Official-feed plus reliability regressions: 100 passed, one database test skipped.
- `python -m ruff check services/api`: passed.
- Standard-library research suite: 86 tests, OK (the built-client test initially skips
  before the web build; the separate post-build boundary suite passes all four tests).
- `compileall`, web typecheck, lint, lint-glob tests, web tests and build: passed.
- Hashed Python dependency audit: no known vulnerabilities.
- Full npm dependency audit: zero vulnerabilities.

The new database regression creates the schema immediately before the reliability
migration, inserts pending/sending/sent/failed/suppressed alerts, applies the remaining
migrations and checks preserved IDs, statuses, lease owner/token, failure code and times.
It is part of the existing PostgreSQL CI acceptance suite; a clean-schema CI migration
alone does not substitute for this test.

## Remaining validation boundary

PostgreSQL binaries and a container runtime are unavailable in this environment.
Local database skips are not passes. PostgreSQL 16 acceptance, SQL permission/RLS
tests and the 37 existing negative controls remain required in CI before the
release gate can pass. The populated-upgrade regression runs in that acceptance job.
