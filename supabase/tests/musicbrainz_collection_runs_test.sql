-- Tests for the MusicBrainz collection-run lifecycle (202610180002_musicbrainz_collection_runs.sql)
-- and its provenance gate on cache_musicbrainz_artist (202610180001).
-- Requires supabase/ci/emulate_supabase_roles.sql to have run before the migrations.
--   psql -v ON_ERROR_STOP=1 -f supabase/tests/musicbrainz_collection_runs_test.sql
-- Synthetic permissions only. Everything runs in one transaction and is rolled back.

begin;

do $$
declare
  fn text;
  api_role text;
begin
  foreach fn in array array[
    'public.begin_musicbrainz_run(text, text)',
    'public.finish_musicbrainz_run(uuid, text, integer, text)',
    'public.cache_musicbrainz_artist(uuid, text, text, numeric, text, uuid)'
  ] loop
    foreach api_role in array array['anon', 'authenticated'] loop
      if has_function_privilege(api_role, fn, 'EXECUTE') then
        raise exception 'FAIL % can execute %', api_role, fn;
      end if;
    end loop;
    if exists (
      select 1 from pg_proc p, aclexplode(p.proacl) acl
      where p.oid = fn::regprocedure and acl.grantee = 0 and acl.privilege_type = 'EXECUTE'
    ) then
      raise exception 'FAIL PUBLIC can execute %', fn;
    end if;
    if not has_function_privilege('service_role', fn, 'EXECUTE') then
      raise exception 'FAIL service_role cannot execute %', fn;
    end if;
  end loop;
  if to_regprocedure('public.record_musicbrainz_run(text, text, integer, text, text, timestamptz)') is not null then
    raise exception 'FAIL after-the-fact record_musicbrainz_run still exists';
  end if;
  raise notice 'ok - run lifecycle and cache functions are executable by service_role only';
end;
$$;

-- Opening fails closed: no run row unless the source is approved and a permission that was
-- approved at or before the run start grants collect right now.
do $$
declare
  mb uuid;
  key constant text := 'artist-search:' || repeat('a', 64) || ':' || repeat('0', 32);
  runs_before integer;
begin
  select source_id into mb from public.sources where slug = 'musicbrainz';
  if (select adapter_version from public.sources where source_id = mb) is distinct from 'musicbrainz-ws2-0.1' then
    raise exception 'FAIL musicbrainz adapter_version was not set';
  end if;
  select count(*) into runs_before from public.collection_runs where source_id = mb;

  -- Source still planned, even with a valid permission.
  insert into public.source_permissions (source_id, terms_url, terms_version, evidence_note,
    collect_allowed, approved_at, created_at)
  values (mb, 'https://example.test/terms', 'planned-ok', 'synthetic', true,
          now() - interval '1 day', now() - interval '2 days');
  begin
    perform public.begin_musicbrainz_run(key, 'musicbrainz-ws2-0.1');
    raise exception 'FAIL run opened while the source is planned';
  exception when insufficient_privilege then
    null;
  end;
  delete from public.source_permissions where source_id = mb;

  update public.sources set access_status = 'approved' where source_id = mb;
  insert into public.source_permissions (source_id, terms_url, terms_version, evidence_note,
    collect_allowed, approved_at, created_at)
  values
    -- revoked
    (mb, 'https://example.test/terms', 'revoked', 'synthetic', true, now() - interval '1 hour', now() - interval '2 hours'),
    -- expired
    (mb, 'https://example.test/terms', 'expired', 'synthetic', true, now() - interval '2 hours', now() - interval '3 days'),
    -- no collect
    (mb, 'https://example.test/terms', 'no-collect', 'synthetic', false, now() - interval '90 minutes', now() - interval '3 days'),
    -- not approved
    (mb, 'https://example.test/terms', 'unapproved', 'synthetic', true, null, now() - interval '1 hour'),
    -- approved after the run starts (now() is this transaction's start, the run start)
    (mb, 'https://example.test/terms', 'approved-later', 'synthetic', true, now() + interval '1 second', now() - interval '1 hour');
  update public.source_permissions set revoked_at = now() - interval '30 minutes'
  where source_id = mb and terms_version = 'revoked';
  update public.source_permissions set expires_at = now() - interval '1 minute'
  where source_id = mb and terms_version = 'expired';

  begin
    perform public.begin_musicbrainz_run(key, 'musicbrainz-ws2-0.1');
    raise exception 'FAIL run used permission without a qualifying collect grant';
  exception when insufficient_privilege then
    null;
  end;
  if (select count(*) from public.collection_runs where source_id = mb) <> runs_before then
    raise exception 'FAIL a denied open left a collection run row';
  end if;
  raise notice 'ok - opening fails closed without an approved source and a qualifying permission';
end;
$$;

-- The exact authorizing permission is captured at open; finalization updates that same row.
do $$
declare
  mb uuid;
  older_permission uuid;
  current_permission uuid;
  opened record;
  run public.collection_runs;
  runs_before integer;
  lookup_key constant text := 'artist-lookup:6c7a9f0b-3c1e-4d5a-9a43-0d0b3e1f7a11:' || repeat('1', 32);
  failed_key constant text := 'artist-search:' || repeat('b', 64) || ':' || repeat('2', 32);
begin
  select source_id into mb from public.sources where slug = 'musicbrainz';
  insert into public.source_permissions (source_id, terms_url, terms_version, evidence_note,
    collect_allowed, approved_at, created_at)
  values (mb, 'https://example.test/terms', 'v1', 'synthetic', true, now() - interval '3 days', now() - interval '4 days')
  returning permission_id into older_permission;
  insert into public.source_permissions (source_id, terms_url, terms_version, evidence_note,
    collect_allowed, approved_at, created_at)
  values (mb, 'https://example.test/terms', 'v2', 'synthetic', true, now() - interval '2 days', now() - interval '3 days')
  returning permission_id into current_permission;
  select count(*) into runs_before from public.collection_runs where source_id = mb;

  select * into opened from public.begin_musicbrainz_run(lookup_key, 'musicbrainz-ws2-0.1');
  if opened.permission_id is distinct from current_permission then
    raise exception 'FAIL run used permission %, expected the newest qualifying v2 permission', opened.permission_id;
  end if;
  select * into run from public.collection_runs where collection_run_id = opened.collection_run_id;
  if run.permission_id is distinct from current_permission or run.source_id <> mb
     or run.status <> 'failed' or run.error_code <> 'incomplete' or run.finished_at is not null
     or run.started_at <> opened.started_at or run.item_count <> 0 then
    raise exception 'FAIL open run recorded wrongly: %', row_to_json(run);
  end if;

  -- Revoking after the run started does not rewrite the captured authorization.
  update public.source_permissions set revoked_at = now() + interval '1 second'
  where permission_id = current_permission;
  perform public.finish_musicbrainz_run(opened.collection_run_id, 'succeeded', 1, null);
  select * into run from public.collection_runs where collection_run_id = opened.collection_run_id;
  if run.status <> 'succeeded' or run.item_count <> 1 or run.error_code is not null
     or run.finished_at is null or run.finished_at < run.started_at
     or run.permission_id is distinct from current_permission then
    raise exception 'FAIL finalized run recorded wrongly: %', row_to_json(run);
  end if;
  if (select count(*) from public.collection_runs where source_id = mb) <> runs_before + 1 then
    raise exception 'FAIL finalization created a second row';
  end if;

  -- Retries are attempts inside one run: a finalized run cannot be finalized again.
  begin
    perform public.finish_musicbrainz_run(opened.collection_run_id, 'failed', 0, 'upstream_unavailable');
    raise exception 'FAIL a finalized run was finalized twice';
  exception when object_not_in_prerequisite_state then
    null;
  end;
  begin
    perform public.finish_musicbrainz_run(gen_random_uuid(), 'empty', 0, null);
    raise exception 'FAIL finalized a run that was never opened';
  exception when object_not_in_prerequisite_state then
    null;
  end;
  begin
    perform public.begin_musicbrainz_run(lookup_key, 'musicbrainz-ws2-0.1');
    raise exception 'FAIL duplicate logical key was accepted';
  exception when unique_violation then
    null;
  end;

  -- With v2 revoked, the older v1 is the one captured.
  update public.source_permissions set revoked_at = now() where permission_id = current_permission;
  select * into opened from public.begin_musicbrainz_run(failed_key, 'musicbrainz-ws2-0.1');
  if opened.permission_id is distinct from older_permission then
    raise exception 'FAIL run used permission % after v2 was revoked, expected v1', opened.permission_id;
  end if;
  perform public.finish_musicbrainz_run(opened.collection_run_id, 'failed', 0, 'upstream_unavailable');
  select * into run from public.collection_runs where collection_run_id = opened.collection_run_id;
  if run.status <> 'failed' or run.error_code <> 'upstream_unavailable' or run.finished_at is null then
    raise exception 'FAIL failed run recorded wrongly: %', row_to_json(run);
  end if;
  raise notice 'ok - open captures the authorizing permission and finalization updates that row once';
end;
$$;

-- Malformed input is rejected, so names and payloads cannot reach collection_runs.
do $$
declare
  good_key constant text := 'artist-search:' || repeat('c', 64) || ':' || repeat('3', 32);
  opened record;
  bad_key text;
  bad record;
begin
  foreach bad_key in array array[
    'artist-search:Phoebe Bridgers:' || repeat('3', 32),
    'artist-search:' || repeat('c', 64)
  ] loop
    begin
      perform public.begin_musicbrainz_run(bad_key, 'musicbrainz-ws2-0.1');
      raise exception 'FAIL accepted key %', bad_key;
    exception when invalid_parameter_value then
      null;
    end;
  end loop;
  begin
    perform public.begin_musicbrainz_run(good_key, null);
    raise exception 'FAIL accepted a missing adapter version';
  exception when invalid_parameter_value then
    null;
  end;

  select * into opened from public.begin_musicbrainz_run(good_key, 'musicbrainz-ws2-0.1');
  for bad in
    select * from (values
      ('unsupported status', 'skipped', 0, null::text),
      ('succeeded with no items', 'succeeded', 0, null),
      ('empty with items', 'empty', 2, null),
      ('negative count', 'failed', -1, 'network_error'),
      ('failed without code', 'failed', 0, null),
      ('success with code', 'empty', 0, 'network_error'),
      ('reserved incomplete code', 'failed', 0, 'incomplete'),
      ('payload as code', 'failed', 0, 'MusicBrainz said: {"error": "x"}')
    ) as t(label, s, n, code)
  loop
    begin
      perform public.finish_musicbrainz_run(opened.collection_run_id, bad.s, bad.n, bad.code);
      raise exception 'FAIL accepted %', bad.label;
    exception when invalid_parameter_value then
      null;
    end;
  end loop;
  raise notice 'ok - malformed keys, statuses, counts, codes and versions are rejected';
end;
$$;

-- No cache write without a finalized, succeeded run that fetched the artist.
do $$
declare
  mb uuid;
  mbid constant uuid := '6c7a9f0b-3c1e-4d5a-9a43-0d0b3e1f7a11';
  other_mbid constant uuid := '0f3e2a1b-7c6d-4e5f-8a9b-1c2d3e4f5a6b';
  open_run record;
  empty_run record;
  lookup_run record;
  search_run record;
  bad_run uuid;
begin
  select source_id into mb from public.sources where slug = 'musicbrainz';
  insert into public.source_permissions (source_id, terms_url, terms_version, evidence_note,
    collect_allowed, derived_retention_allowed, approved_at, created_at)
  values (mb, 'https://example.test/terms', 'cache', 'synthetic', true, true,
          now() - interval '1 day', now() - interval '2 days');

  select * into open_run from public.begin_musicbrainz_run(
    'artist-lookup:' || mbid || ':' || repeat('4', 32), 'musicbrainz-ws2-0.1');
  select * into empty_run from public.begin_musicbrainz_run(
    'artist-lookup:' || mbid || ':' || repeat('5', 32), 'musicbrainz-ws2-0.1');
  perform public.finish_musicbrainz_run(empty_run.collection_run_id, 'empty', 0, null);
  select * into lookup_run from public.begin_musicbrainz_run(
    'artist-lookup:' || other_mbid || ':' || repeat('6', 32), 'musicbrainz-ws2-0.1');
  perform public.finish_musicbrainz_run(lookup_run.collection_run_id, 'succeeded', 1, null);

  foreach bad_run in array array[
    null, gen_random_uuid(), open_run.collection_run_id, empty_run.collection_run_id,
    lookup_run.collection_run_id
  ] loop
    begin
      perform public.cache_musicbrainz_artist(mbid, 'Synthetic Artist', null, 1.0, 'musicbrainz-lookup', bad_run);
      raise exception 'FAIL cached without a matching succeeded run (%)', coalesce(bad_run::text, 'null');
    exception when invalid_parameter_value then
      null;
    end;
  end loop;
  if exists (select 1 from public.source_entity_mappings where vendor_id = mbid::text) then
    raise exception 'FAIL a rejected cache write left a mapping';
  end if;

  select * into search_run from public.begin_musicbrainz_run(
    'artist-search:' || repeat('d', 64) || ':' || repeat('7', 32), 'musicbrainz-ws2-0.1');
  perform public.finish_musicbrainz_run(search_run.collection_run_id, 'succeeded', 2, null);
  perform public.cache_musicbrainz_artist(mbid, 'Synthetic Artist', null, 0.9,
    'musicbrainz-search-exact', search_run.collection_run_id);
  if not exists (select 1 from public.source_entity_mappings where vendor_id = mbid::text) then
    raise exception 'FAIL cache write with a succeeded run was not stored';
  end if;
  raise notice 'ok - cache writes need the finalized succeeded run that fetched the artist';
end;
$$;

rollback;
