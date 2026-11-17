#!/usr/bin/env bash
# Apply supabase/migrations to one PostgreSQL database, in filename order, each file in
# its own transaction, recording what was applied so a re-run applies only new files.
#
#   SWEET_SEATS_MIGRATION_URL=postgresql://... scripts/apply-migrations.sh [--dry-run]
#
# The URL comes from the environment, never an argument (it would land in shell
# history). Only postgres:// or postgresql:// URLs are accepted. A file already
# recorded with different contents stops the run: applied migrations are never edited.
# Run from the repository root.
set -euo pipefail

url="${SWEET_SEATS_MIGRATION_URL:-}"
dry_run=no
[ "${1:-}" = "--dry-run" ] && dry_run=yes

case "$url" in
  postgres://*|postgresql://*) ;;
  *) echo "SWEET_SEATS_MIGRATION_URL must be a postgres:// or postgresql:// URL" >&2; exit 2 ;;
esac

psql_q() { psql "$url" -v ON_ERROR_STOP=1 -X -q -t -A "$@"; }

psql_q -c "set client_min_messages = warning;
  create schema if not exists sweet_seats_ops;
  create table if not exists sweet_seats_ops.applied_migrations (
    filename text primary key, sha256 text not null, applied_at timestamptz not null default now());
  revoke all on schema sweet_seats_ops from public;" >/dev/null

applied=0
for file in $(ls supabase/migrations/*.sql | sort); do
  name="$(basename "$file")"
  sum="$(sha256sum "$file" | cut -d' ' -f1)"
  recorded="$(psql_q -v name="$name" <<'SQL'
select sha256 from sweet_seats_ops.applied_migrations where filename = :'name';
SQL
)"
  if [ -n "$recorded" ]; then
    if [ "$recorded" != "$sum" ]; then
      echo "STOP $name changed after it was applied (recorded $recorded)" >&2
      exit 3
    fi
    continue
  fi
  if [ "$dry_run" = yes ]; then
    echo "would apply $name"
    continue
  fi
  echo "applying $name"
  {
    echo "begin;"
    echo "select pg_advisory_xact_lock(hashtext('sweet_seats_migrations'));"
    cat "$file"
    echo
    echo "insert into sweet_seats_ops.applied_migrations (filename, sha256) values ('$name', '$sum');"
    echo "commit;"
  } | psql "$url" -v ON_ERROR_STOP=1 -X -q >/dev/null
  applied=$((applied + 1))
done
echo "$applied migration(s) applied"
