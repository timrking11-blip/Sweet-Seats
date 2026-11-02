-- Permission-window tests for public.source_use_is_permitted.
-- Run against a disposable database after applying supabase/migrations, e.g.
--   psql -v ON_ERROR_STOP=1 -f supabase/tests/source_permissions_test.sql
-- Synthetic sources only. Everything runs in one transaction and is rolled back.

begin;

create function pg_temp.permission_case(
  case_slug text,
  status public.source_access_status,
  approved timestamptz,
  revoked timestamptz,
  expires timestamptz
) returns uuid
language plpgsql
as $$
declare
  new_source_id uuid;
begin
  insert into public.sources (slug, name, official_url, source_type, access_status)
  values (case_slug, case_slug, 'https://example.test/' || case_slug, 'synthetic', status)
  returning source_id into new_source_id;

  insert into public.source_permissions (
    source_id, terms_url, terms_version, evidence_note,
    collect_allowed, display_allowed, approved_at, revoked_at, expires_at, created_at
  ) values (
    new_source_id, 'https://example.test/terms', 'v1', 'synthetic test permission',
    true, false, approved, revoked, expires, timestamptz '2026-01-01 00:00:00+00'
  );

  return new_source_id;
end;
$$;

create function pg_temp.expect(label text, actual boolean, expected boolean) returns void
language plpgsql
as $$
begin
  if actual is distinct from expected then
    raise exception 'FAIL %: expected %, got %', label, expected, actual;
  end if;
  raise notice 'ok - %', label;
end;
$$;

do $$
declare
  t constant timestamptz := timestamptz '2026-10-18 12:00:00+00';
  past constant timestamptz := t - interval '30 days';
  future constant timestamptz := t + interval '30 days';
  s uuid;
begin
  -- Baseline: approved before as_of, never revoked or expired.
  s := pg_temp.permission_case('approved-past', 'approved', past, null, null);
  perform pg_temp.expect('approved in the past permits collect',
    public.source_use_is_permitted(s, 'collect', t), true);
  perform pg_temp.expect('allowed flag is still required (display=false)',
    public.source_use_is_permitted(s, 'display', t), false);
  perform pg_temp.expect('unknown use is denied',
    public.source_use_is_permitted(s, 'resell', t), false);
  perform pg_temp.expect('null as_of is denied',
    public.source_use_is_permitted(s, 'collect', null), false);
  perform pg_temp.expect('as_of before the approval is denied',
    public.source_use_is_permitted(s, 'collect', past - interval '1 second'), false);

  -- Approval timing.
  s := pg_temp.permission_case('approved-future', 'approved', future, null, null);
  perform pg_temp.expect('future-dated approval is denied',
    public.source_use_is_permitted(s, 'collect', t), false);
  perform pg_temp.expect('future-dated approval applies once reached',
    public.source_use_is_permitted(s, 'collect', future), true);

  s := pg_temp.permission_case('approved-null', 'approved', null, null, null);
  perform pg_temp.expect('missing approval is denied',
    public.source_use_is_permitted(s, 'collect', t), false);

  s := pg_temp.permission_case('approved-at-t', 'approved', t, null, null);
  perform pg_temp.expect('approval exactly at as_of permits',
    public.source_use_is_permitted(s, 'collect', t), true);

  -- Revocation timing.
  s := pg_temp.permission_case('revoked-past', 'approved', past, past + interval '1 day', null);
  perform pg_temp.expect('past revocation is denied',
    public.source_use_is_permitted(s, 'collect', t), false);
  perform pg_temp.expect('as_of before the revocation still permits',
    public.source_use_is_permitted(s, 'collect', past + interval '1 hour'), true);

  s := pg_temp.permission_case('revoked-future', 'approved', past, future, null);
  perform pg_temp.expect('scheduled future revocation still permits now',
    public.source_use_is_permitted(s, 'collect', t), true);
  perform pg_temp.expect('scheduled revocation denies once reached',
    public.source_use_is_permitted(s, 'collect', future), false);

  s := pg_temp.permission_case('revoked-at-t', 'approved', past, t, null);
  perform pg_temp.expect('revocation exactly at as_of is denied',
    public.source_use_is_permitted(s, 'collect', t), false);

  -- Expiry timing.
  s := pg_temp.permission_case('expired-past', 'approved', past, null, past + interval '1 day');
  perform pg_temp.expect('expired permission is denied',
    public.source_use_is_permitted(s, 'collect', t), false);

  s := pg_temp.permission_case('expires-future', 'active', past, null, future);
  perform pg_temp.expect('unexpired permission on an active source permits',
    public.source_use_is_permitted(s, 'collect', t), true);

  s := pg_temp.permission_case('expires-at-t', 'approved', past, null, t);
  perform pg_temp.expect('expiry exactly at as_of is denied',
    public.source_use_is_permitted(s, 'collect', t), false);

  -- Approval evidence (SS-DATA-0.1: approval evidence required).
  s := pg_temp.permission_case('evidence-empty', 'approved', past, null, null);
  update public.source_permissions set evidence_note = '  ' where source_id = s;
  perform pg_temp.expect('empty evidence is denied',
    public.source_use_is_permitted(s, 'collect', t), false);

  s := pg_temp.permission_case('terms-empty', 'approved', past, null, null);
  update public.source_permissions set terms_version = '' where source_id = s;
  perform pg_temp.expect('empty terms version is denied',
    public.source_use_is_permitted(s, 'collect', t), false);

  -- Status vocabulary shared with the Python contract.
  perform pg_temp.expect('rescheduled is a valid event status',
    'rescheduled'::text = any (enum_range(null::public.event_status)::text[]), true);

  -- Source status gate.
  s := pg_temp.permission_case('source-planned', 'planned', past, null, null);
  perform pg_temp.expect('planned source is denied despite a valid permission',
    public.source_use_is_permitted(s, 'collect', t), false);

  s := pg_temp.permission_case('source-suspended', 'suspended', past, null, null);
  perform pg_temp.expect('suspended source is denied despite a valid permission',
    public.source_use_is_permitted(s, 'collect', t), false);

  perform pg_temp.expect('unknown source is denied',
    public.source_use_is_permitted(gen_random_uuid(), 'collect', t), false);
end;
$$;

rollback;
