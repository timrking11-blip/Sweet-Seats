#!/usr/bin/env bash
# Negative controls for the SQL tests in supabase/tests.
#
# Each control builds a throwaway database, deliberately breaks the schema (or the
# Supabase grant emulation), and requires a test file to FAIL with an expected message.
# A control whose tests still pass means that regression would ship unnoticed.
#
# CI only: needs PGHOST/PGUSER/PGPASSWORD for a disposable PostgreSQL server and runs
# from the repository root, after emulate_supabase_roles.sql has created the API roles
# (roles are cluster-wide; the grants it sets are per database). Never point it at a
# Supabase project.
set -uo pipefail

ROLES=supabase/ci/emulate_supabase_roles.sql
PERMISSIONS_TEST=supabase/tests/source_permissions_test.sql
RLS_TEST=supabase/tests/rls_denial_test.sql
mapfile -t MIGRATIONS < <(ls supabase/migrations/*.sql | sort)

failures=0
count=0

# run_control NAME EXPECTED TEST_FILE BREAKAGE_SQL [ROLES yes|no] [MIGRATION_SED] [TEST_SED]
run_control() {
  local name="$1" expected="$2" test_file="$3" breakage="$4"
  local roles="${5:-yes}" migration_sed="${6:-}" test_sed="${7:-}"
  count=$((count + 1))
  local db="negative_control_${count}"
  local tmp
  tmp="$(mktemp -d)"

  psql -q -d postgres -c "drop database if exists ${db}" >/dev/null
  psql -q -d postgres -c "create database ${db}" >/dev/null

  {
    if [ "$roles" = yes ]; then cat "$ROLES"; echo; fi
    for f in "${MIGRATIONS[@]}"; do
      if [ -n "$migration_sed" ]; then sed "$migration_sed" "$f"; else cat "$f"; fi
      echo
    done
    printf '%s\n' "$breakage"
  } >"$tmp/setup.sql"

  if [ -n "$test_sed" ]; then sed "$test_sed" "$test_file" >"$tmp/test.sql"; else cp "$test_file" "$tmp/test.sql"; fi

  if ! psql -q -v ON_ERROR_STOP=1 -d "$db" -f "$tmp/setup.sql" >"$tmp/setup.log" 2>&1; then
    echo "ERROR  ${name}: setup failed"
    cat "$tmp/setup.log"
    failures=$((failures + 1))
  elif psql -q -v ON_ERROR_STOP=1 -d "$db" -f "$tmp/test.sql" >"$tmp/test.log" 2>&1; then
    echo "MISSED ${name}: $(basename "$test_file") passed against the broken schema"
    failures=$((failures + 1))
  elif grep -qF -- "$expected" "$tmp/test.log"; then
    echo "caught ${name}"
  else
    echo "WRONG  ${name}: failed, but not with: ${expected}"
    grep -E 'ERROR|FAIL' "$tmp/test.log" | head -5
    failures=$((failures + 1))
  fi

  psql -q -d postgres -c "drop database if exists ${db}" >/dev/null
  rm -rf "$tmp"
}

# Row-level security.
run_control "RLS disabled on a foundation table" \
  "public tables without row level security: artists" "$RLS_TEST" \
  "alter table public.artists disable row level security;"

run_control "new public table created without RLS" \
  "public tables without row level security: unprotected_notes" "$RLS_TEST" \
  "create table public.unprotected_notes (note text);"

run_control "permissive anon policy" \
  "foundation tables have 1 RLS policies" "$RLS_TEST" \
  "create policy leak on public.events for select to anon using (true);"

# With the policy-count guard neutralised, the per-role read checks must still catch the leak.
run_control "permissive anon policy (read check alone)" \
  "FAIL anon can read 1 row(s) from events" "$RLS_TEST" \
  "create policy leak on public.events for select to anon using (true);" \
  yes "" "s/if policy_count > 0 then/if false then/"

run_control "authenticated-only insert policy" \
  "FAIL authenticated inserted a row" "$RLS_TEST" \
  "create policy leak on public.artists for insert to authenticated with check (true);" \
  yes "" "s/if policy_count > 0 then/if false then/"

run_control "permission check runs as security definer" \
  "FAIL anon sees source permission through source_use_is_permitted" "$RLS_TEST" \
  "alter function public.source_use_is_permitted(uuid, text, timestamptz) security definer;"

run_control "Supabase default grants missing" \
  "FAIL premise" "$RLS_TEST" \
  "" no

# Source-permission time window.
run_control "approval no longer compared with as_of" \
  "FAIL null as_of is denied" "$PERMISSIONS_TEST" \
  "" yes "/permission.approved_at <= as_of/d"

run_control "revocation treated as immediate" \
  "FAIL as_of before the revocation still permits" "$PERMISSIONS_TEST" \
  "" yes "s/(permission.revoked_at is null or permission.revoked_at > as_of)/permission.revoked_at is null/"

run_control "expiry boundary made inclusive" \
  "FAIL expiry exactly at as_of is denied" "$PERMISSIONS_TEST" \
  "" yes "s/permission.expires_at > as_of/permission.expires_at >= as_of/"

echo "${count} negative controls, ${failures} not caught"
[ "$failures" -eq 0 ]
