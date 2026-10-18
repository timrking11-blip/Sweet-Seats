-- Tests for public.record_musicbrainz_run (202610180002_musicbrainz_collection_runs.sql).
-- Requires supabase/ci/emulate_supabase_roles.sql to have run before the migrations.
--   psql -v ON_ERROR_STOP=1 -f supabase/tests/musicbrainz_collection_runs_test.sql
-- Synthetic permissions only. Everything runs in one transaction and is rolled back.

begin;

do $$
declare
  fn constant text := 'public.record_musicbrainz_run(text, text, integer, text, text, timestamptz)';
  api_role text;
begin
  foreach api_role in array array['anon', 'authenticated'] loop
    if has_function_privilege(api_role, fn, 'EXECUTE') then
      raise exception 'FAIL % can execute record_musicbrainz_run', api_role;
    end if;
  end loop;
  if exists (
    select 1 from pg_proc p, aclexplode(p.proacl) acl
    where p.oid = fn::regprocedure and acl.grantee = 0 and acl.privilege_type = 'EXECUTE'
  ) then
    raise exception 'FAIL PUBLIC can execute record_musicbrainz_run';
  end if;
  if not has_function_privilege('service_role', fn, 'EXECUTE') then
    raise exception 'FAIL service_role cannot execute record_musicbrainz_run';
  end if;
  raise notice 'ok - record_musicbrainz_run is executable by service_role only';
end;
$$;

-- Permission evidence: the newest permission that grants collect right now, else null.
do $$
declare
  mb uuid;
  current_permission uuid;
  run_id uuid;
  run public.collection_runs;
  search_key constant text := 'artist-search:' || repeat('a', 64) || ':' || repeat('0', 32);
begin
  select source_id into mb from public.sources where slug = 'musicbrainz';
  if (select adapter_version from public.sources where source_id = mb) is distinct from 'musicbrainz-ws2-0.1' then
    raise exception 'FAIL musicbrainz adapter_version was not set';
  end if;

  -- No permission at all: the run is still recorded, with a null permission_id.
  run_id := public.record_musicbrainz_run(search_key, 'empty', 0, null, 'musicbrainz-ws2-0.1');
  select * into run from public.collection_runs where collection_run_id = run_id;
  if run.permission_id is not null or run.source_id <> mb or run.status <> 'empty'
     or run.finished_at is null or run.started_at > run.finished_at then
    raise exception 'FAIL unpermitted run recorded wrongly: %', row_to_json(run);
  end if;

  insert into public.source_permissions (source_id, terms_url, terms_version, evidence_note,
    collect_allowed, approved_at, created_at)
  values
    -- older approved: superseded by the newer one below
    (mb, 'https://example.test/terms', 'v1', 'synthetic', true, now() - interval '3 days', now() - interval '4 days'),
    -- newest approval but revoked
    (mb, 'https://example.test/terms', 'v3', 'synthetic', true, now() - interval '1 hour', now() - interval '2 hours'),
    -- newer approval but expired
    (mb, 'https://example.test/terms', 'v2e', 'synthetic', true, now() - interval '2 hours', now() - interval '3 days'),
    -- newer approval without collect
    (mb, 'https://example.test/terms', 'v2n', 'synthetic', false, now() - interval '90 minutes', now() - interval '3 days'),
    -- not approved yet
    (mb, 'https://example.test/terms', 'v4', 'synthetic', true, null, now() - interval '1 hour');
  update public.source_permissions set revoked_at = now() - interval '30 minutes'
  where source_id = mb and terms_version = 'v3';
  update public.source_permissions set expires_at = now() - interval '1 minute'
  where source_id = mb and terms_version = 'v2e';

  insert into public.source_permissions (source_id, terms_url, terms_version, evidence_note,
    collect_allowed, approved_at, created_at)
  values (mb, 'https://example.test/terms', 'v2', 'synthetic', true, now() - interval '2 days', now() - interval '3 days')
  returning permission_id into current_permission;

  run_id := public.record_musicbrainz_run(
    'artist-lookup:6c7a9f0b-3c1e-4d5a-9a43-0d0b3e1f7a11:' || repeat('1', 32),
    'succeeded', 1, null, 'musicbrainz-ws2-0.1', now() - interval '2 seconds');
  select * into run from public.collection_runs where collection_run_id = run_id;
  if run.permission_id is distinct from current_permission then
    raise exception 'FAIL run used permission %, expected the current v2 permission', run.permission_id;
  end if;
  if run.item_count <> 1 or run.error_code is not null or run.started_at >= run.finished_at then
    raise exception 'FAIL succeeded run recorded wrongly: %', row_to_json(run);
  end if;

  run_id := public.record_musicbrainz_run(
    'artist-search:' || repeat('b', 64) || ':' || repeat('2', 32),
    'failed', 0, 'upstream_unavailable', 'musicbrainz-ws2-0.1', now() + interval '1 hour');
  select * into run from public.collection_runs where collection_run_id = run_id;
  if run.status <> 'failed' or run.error_code <> 'upstream_unavailable'
     or run.permission_id is distinct from current_permission
     or run.started_at > run.finished_at then
    raise exception 'FAIL failed run recorded wrongly: %', row_to_json(run);
  end if;
  raise notice 'ok - runs record the current collect permission, or null when there is none';

  -- One row per logical key.
  begin
    perform public.record_musicbrainz_run(search_key, 'empty', 0, null, 'musicbrainz-ws2-0.1');
    raise exception 'FAIL duplicate logical key was accepted';
  exception when unique_violation then
    null;
  end;
  raise notice 'ok - a logical key is recorded once';
end;
$$;

-- Malformed input is rejected, so names and payloads cannot reach collection_runs.
do $$
declare
  good_key constant text := 'artist-search:' || repeat('c', 64) || ':' || repeat('3', 32);
  bad record;
begin
  for bad in
    select * from (values
      ('raw name in key', 'artist-search:Phoebe Bridgers:' || repeat('3', 32), 'empty', 0, null::text, 'musicbrainz-ws2-0.1'),
      ('key without nonce', 'artist-search:' || repeat('c', 64), 'empty', 0, null, 'musicbrainz-ws2-0.1'),
      ('unsupported status', good_key, 'skipped', 0, null, 'musicbrainz-ws2-0.1'),
      ('succeeded with no items', good_key, 'succeeded', 0, null, 'musicbrainz-ws2-0.1'),
      ('empty with items', good_key, 'empty', 2, null, 'musicbrainz-ws2-0.1'),
      ('negative count', good_key, 'failed', -1, 'network_error', 'musicbrainz-ws2-0.1'),
      ('failed without code', good_key, 'failed', 0, null, 'musicbrainz-ws2-0.1'),
      ('success with code', good_key, 'empty', 0, 'network_error', 'musicbrainz-ws2-0.1'),
      ('payload as code', good_key, 'failed', 0, 'MusicBrainz said: {"error": "x"}', 'musicbrainz-ws2-0.1'),
      ('missing adapter version', good_key, 'empty', 0, null, null)
    ) as t(label, k, s, n, code, adapter)
  loop
    begin
      perform public.record_musicbrainz_run(bad.k, bad.s, bad.n, bad.code, bad.adapter);
      raise exception 'FAIL accepted %', bad.label;
    exception when invalid_parameter_value then
      null;
    end;
  end loop;
  raise notice 'ok - malformed keys, statuses, counts, codes and versions are rejected';
end;
$$;

rollback;
