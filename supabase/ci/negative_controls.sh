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
MB_RUNS_TEST=supabase/tests/musicbrainz_collection_runs_test.sql
WAITLIST_TEST=supabase/tests/waitlist_test.sql
CONSENT_TEST=supabase/tests/consent_history_test.sql
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

run_control "RLS disabled on review records" \
  "public tables without row level security: source_unresolved_records" "$RLS_TEST" \
  "alter table public.source_unresolved_records disable row level security;"

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

# Consent evidence is server-written (20261029100000_user_consent_integrity.sql).
run_control "signed-in users can create subscriptions directly" \
  "FAIL user A created a subscription directly" "$USER_TEST" \
  "grant insert on public.notification_subscriptions to authenticated;"

run_control "signed-in users can rewrite consent evidence" \
  "FAIL user A rewrote consent evidence" "$USER_TEST" \
  "grant update on public.notification_subscriptions to authenticated;"

run_control "revocation time accepted from the client" \
  "FAIL a revocation time came from the client" "$USER_TEST" \
  "drop trigger notification_subscriptions_stamp_revocation on public.notification_subscriptions;"

run_control "revocation can be reversed" \
  "FAIL user A reversed a revocation" "$USER_TEST" \
  "" yes "s/raise exception 'revocation_is_final' using errcode = '42501';/return new;/"

run_control "deletion request can be withdrawn" \
  "FAIL user A withdrew a deletion request" "$USER_TEST" \
  "" yes "s/  if tg_op = 'UPDATE' and old.deletion_requested_at is not null then/  if false then/"

run_control "signed-in users can delete their profile and its evidence" \
  "FAIL user A deleted their profile directly" "$USER_TEST" \
  "grant delete on public.user_profiles to authenticated;"

run_control "follows writable after a deletion request" \
  "FAIL user A followed after a deletion request" "$USER_TEST" \
  "drop trigger artist_follows_refuse_after_deletion_request on public.artist_follows;"

run_control "outcome consent version changed without a new time" \
  "FAIL outcome consent version changed without a new time" "$USER_TEST" \
  "" yes "s/ or new.outcome_consent_version is distinct from old.outcome_consent_version//"

run_control "outcome consent time accepted from the client" \
  "FAIL outcome consent was back-dated" "$USER_TEST" \
  "" yes "/new.outcome_consent_at := now();/d"

# MusicBrainz collection runs.
run_control "begin_musicbrainz_run executable by anon" \
  "FAIL anon can execute public.begin_musicbrainz_run(text, text)" "$MB_RUNS_TEST" \
  "grant execute on function public.begin_musicbrainz_run(text, text) to anon;"

run_control "collection run ignores permission revocation" \
  "FAIL run used permission" "$MB_RUNS_TEST" \
  "" yes "s/and (p.revoked_at is null or p.revoked_at > run_started_at)//"

run_control "collection run accepts a permission approved after the run start" \
  "FAIL run used permission without a qualifying collect grant" "$MB_RUNS_TEST" \
  "" yes "/and p.approved_at <= run_started_at/d"

run_control "collection run ignores source access status" \
  "FAIL run opened while the source is planned" "$MB_RUNS_TEST" \
  "" yes "s/if mb_access_status not in ('approved', 'active') then/if false then/"

run_control "finalized run can be finalized again" \
  "FAIL a finalized run was finalized twice" "$MB_RUNS_TEST" \
  "" yes "/and r.finished_at is null/d;/and r.status = 'failed'\$/d;s/and r.error_code = 'incomplete';/;/"

run_control "artist cached without a collection run" \
  "FAIL cached without a matching succeeded run" "$MB_RUNS_TEST" \
  "" yes "s/raise exception 'musicbrainz_run_required' using errcode = '22023';/null;/"

# Waitlist privacy.
run_control "waitlist readable by anon" \
  "FAIL anon holds privileges on waitlist_signups" "$WAITLIST_TEST" \
  "grant select on public.waitlist_signups to anon;"

run_control "waitlist insertable by authenticated through a policy" \
  "FAIL waitlist_signups has 1 RLS policies" "$WAITLIST_TEST" \
  "grant insert on public.waitlist_signups to authenticated;
   create policy waitlist_open on public.waitlist_signups for insert to authenticated with check (true);"

run_control "waitlist accepts an unnormalised email" \
  "FAIL an email that is not normalised was accepted" "$WAITLIST_TEST" \
  "" yes "s/check (email = lower(btrim(email))/check (true/"

# Consent history (G-15).
run_control "consent events can be rewritten" \
  "FAIL the owner changed a consent event" "$CONSENT_TEST" \
  "drop trigger consent_events_append_only on public.consent_events;"

run_control "consent events writable by a signed-in user" \
  "FAIL user A wrote a consent event directly" "$CONSENT_TEST" \
  "grant insert on public.consent_events to authenticated;
   create policy consent_events_insert_own on public.consent_events for insert to authenticated
     with check (user_id = (select auth.uid()));"

run_control "outcome consent under an unregistered copy" \
  "FAIL outcome consent accepted under an unregistered copy" "$CONSENT_TEST" \
  "drop trigger user_profiles_require_registered_outcome_copy on public.user_profiles;"

run_control "outcome consent under a retired copy" \
  "FAIL outcome consent accepted under a retired copy" "$CONSENT_TEST" \
  "" yes "s/and c.retired_at is null) then/) then/"

run_control "subscription consent not recorded" \
  "FAIL subscription grant not recorded with its copy hash" "$CONSENT_TEST" \
  "drop trigger notification_subscriptions_record_consent on public.notification_subscriptions;"

run_control "a user's consent change recorded as the server's" \
  "FAIL user A sees the wrong consent history" "$CONSENT_TEST" \
  "" yes "s/when current_setting('role') in ('authenticated', 'anon') then 'user'/when false then 'user'/"

echo "${count} negative controls, ${failures} not caught"
[ "$failures" -eq 0 ]

