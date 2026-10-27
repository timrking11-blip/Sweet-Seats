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
AUTH=supabase/ci/emulate_supabase_auth.sql
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
    cat "$AUTH"; echo
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

run_control "RLS disabled on source observations" \
  "public tables without row level security: source_event_records" "$RLS_TEST" \
  "alter table public.source_event_records disable row level security;"

run_control "permissive observation policy" \
  "discovery table has policies: source_event_records" "supabase/tests/discovery_contract_test.sql" \
  "create policy leak on public.source_event_records for select to anon using (true);"

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

# Source-permission evidence.
run_control "approval evidence no longer required" \
  "FAIL empty evidence is denied" "$PERMISSIONS_TEST" \
  "" yes "/btrim(permission.evidence_note) <> ''/d"

# Phase 2 user isolation and the first-party record rule.
USER_TEST=supabase/tests/user_isolation_test.sql

run_control "follows readable by every signed-in user" \
  "FAIL user A reads 2 artist_follows rows" "$USER_TEST" \
  "create policy leak on public.artist_follows for select to authenticated using (true);"

run_control "insert check no longer tied to the signed-in user" \
  "FAIL user A inserted a follow for user B" "$USER_TEST" \
  "" yes "s/  with check (user_id = (select auth.uid()));/  with check (true);/"

run_control "provider value column added to a user table" \
  "FAIL user tables have unreviewed columns: artist_follows.last_seen_price_minor" "$USER_TEST" \
  "alter table public.artist_follows add column last_seen_price_minor integer;"

run_control "outcomes recordable without outcome consent" \
  "FAIL user A recorded an outcome without outcome consent" "$USER_TEST" \
  "" yes "/and profile.outcome_consent_at is not null/d"

run_control "alerts readable by every signed-in user" \
  "FAIL user A reads 2 alerts rows" "$USER_TEST" \
  "create policy leak on public.alerts for select to authenticated using (true);"

run_control "provider title column added to the alert outbox" \
  "FAIL user tables have unreviewed columns: alerts.event_title" "$USER_TEST" \
  "alter table public.alerts add column event_title text;"

run_control "RLS disabled on per-subscription delivery state" \
  "public tables without row level security: alert_deliveries" "$RLS_TEST" \
  "alter table public.alert_deliveries disable row level security;"

run_control "provider value column added to delivery state" \
  "FAIL user tables have unreviewed columns: alert_deliveries.endpoint_address" "$USER_TEST" \
  "alter table public.alert_deliveries add column endpoint_address text;"

echo "${count} negative controls, ${failures} not caught"
[ "$failures" -eq 0 ]

