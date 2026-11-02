-- Row-level-security denial tests for the Phase 1 foundation tables.
-- Requires supabase/ci/emulate_supabase_roles.sql to have run before the migrations, so
-- anon/authenticated hold Supabase's default table grants and only RLS can deny them.
--   psql -v ON_ERROR_STOP=1 -f supabase/tests/rls_denial_test.sql
-- Synthetic rows only. Everything runs in one transaction and is rolled back.

begin;

-- Premise and catalog checks, as the migration owner.
do $$
declare
  foundation constant text[] := array[
    'sources', 'source_permissions', 'artists', 'venues', 'venue_configurations',
    'events', 'event_performers', 'source_entity_mappings', 'collection_runs'];
  tbl text;
  missing text;
  policy_count integer;
begin
  foreach tbl in array foundation loop
    if not has_table_privilege('anon', 'public.' || tbl, 'SELECT, INSERT, UPDATE, DELETE')
       or not has_table_privilege('authenticated', 'public.' || tbl, 'SELECT, INSERT, UPDATE, DELETE') then
      raise exception 'FAIL premise: API roles lack Supabase default grants on %; RLS would not be what denies', tbl;
    end if;
  end loop;
  raise notice 'ok - API roles hold Supabase default grants on all foundation tables';

  -- Every table in public must have RLS enabled, including tables added by later migrations.
  select string_agg(c.relname, ', ') into missing
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity;
  if missing is not null then
    raise exception 'FAIL public tables without row level security: %', missing;
  end if;
  raise notice 'ok - every public table has row level security enabled';

  -- The foundation grants no user-facing access; user policies arrive with their own migration.
  select count(*) into policy_count from pg_policies
  where schemaname = 'public' and tablename = any(foundation);
  if policy_count > 0 then
    raise exception 'FAIL foundation tables have % RLS policies; expected none', policy_count;
  end if;
  raise notice 'ok - foundation tables define no RLS policies';
end;
$$;

-- Seed one synthetic row per table as the owner, so empty results prove denial rather than absence.
do $$
declare
  v_source uuid;
  v_permission uuid;
  v_artist uuid;
  v_venue uuid;
  v_configuration uuid;
  v_event uuid;
begin
  insert into public.sources (slug, name, official_url, source_type, access_status)
  values ('rls-synthetic', 'RLS synthetic source', 'https://example.test/rls', 'synthetic', 'approved')
  returning source_id into v_source;

  insert into public.source_permissions (source_id, terms_url, terms_version, evidence_note,
    collect_allowed, approved_at, created_at)
  values (v_source, 'https://example.test/terms', 'v1', 'synthetic', true,
    timestamptz '2026-01-02 00:00:00+00', timestamptz '2026-01-01 00:00:00+00')
  returning permission_id into v_permission;

  insert into public.artists (canonical_name) values ('Synthetic Artist') returning artist_id into v_artist;
  insert into public.venues (name) values ('Synthetic Hall') returning venue_id into v_venue;
  insert into public.venue_configurations (venue_id, label, arrangement)
  values (v_venue, 'Main room', 'standing') returning configuration_id into v_configuration;
  insert into public.events (venue_id, configuration_id, local_date, first_seen_at)
  values (v_venue, v_configuration, date '2026-11-01', timestamptz '2026-10-01 00:00:00+00')
  returning event_id into v_event;
  insert into public.event_performers (event_id, artist_id) values (v_event, v_artist);
  insert into public.source_entity_mappings (source_id, record_type, vendor_id, event_id, mapping_method)
  values (v_source, 'event', 'synthetic-event-1', v_event, 'synthetic');
  insert into public.collection_runs (source_id, logical_key, status, finished_at, adapter_version, permission_id)
  values (v_source, 'synthetic-run-1', 'succeeded', timestamptz '2026-10-01 00:05:00+00', 'test', v_permission);

  perform set_config('ss_test.source_id', v_source::text, true);
  perform set_config('ss_test.permission_id', v_permission::text, true);
  perform set_config('ss_test.artist_id', v_artist::text, true);
  perform set_config('ss_test.venue_id', v_venue::text, true);
  perform set_config('ss_test.configuration_id', v_configuration::text, true);
  perform set_config('ss_test.event_id', v_event::text, true);
end;
$$;

-- Each API role must see nothing, change nothing and insert nothing.
do $$
declare
  api_roles constant text[] := array['anon', 'authenticated'];
  foundation constant text[] := array[
    'sources', 'source_permissions', 'artists', 'venues', 'venue_configurations',
    'events', 'event_performers', 'source_entity_mappings', 'collection_runs'];
  source_id constant text := current_setting('ss_test.source_id');
  permission_id constant text := current_setting('ss_test.permission_id');
  artist_id constant text := current_setting('ss_test.artist_id');
  venue_id constant text := current_setting('ss_test.venue_id');
  configuration_id constant text := current_setting('ss_test.configuration_id');
  event_id constant text := current_setting('ss_test.event_id');
  inserts text[];
  api_role text;
  tbl text;
  stmt text;
  n bigint;
  permitted boolean;
begin
  inserts := array[
    format($i$insert into public.sources (slug, name, official_url, source_type)
      values ('rls-intruder', 'x', 'https://example.test/x', 'synthetic')$i$),
    format($i$insert into public.source_permissions (source_id, terms_url, terms_version, evidence_note,
      collect_allowed, approved_at) values (%L, 'https://example.test/t', 'v9', 'x', true, now())$i$, source_id),
    $i$insert into public.artists (canonical_name) values ('Intruder')$i$,
    $i$insert into public.venues (name) values ('Intruder Hall')$i$,
    format($i$insert into public.venue_configurations (venue_id, label, arrangement)
      values (%L, 'x', 'x')$i$, venue_id),
    format($i$insert into public.events (venue_id, configuration_id, local_date, first_seen_at)
      values (%L, %L, date '2026-12-01', now())$i$, venue_id, configuration_id),
    format($i$insert into public.event_performers (event_id, artist_id, role)
      values (%L, %L, 'support')$i$, event_id, artist_id),
    format($i$insert into public.source_entity_mappings (source_id, record_type, vendor_id, artist_id, mapping_method)
      values (%L, 'artist', 'intruder-1', %L, 'x')$i$, source_id, artist_id),
    format($i$insert into public.collection_runs (source_id, logical_key, status, adapter_version, permission_id)
      values (%L, 'intruder-run', 'failed', 'x', %L)$i$, source_id, permission_id)
  ];

  foreach api_role in array api_roles loop
    execute format('set local role %I', api_role);

    foreach tbl in array foundation loop
      execute format('select count(*) from public.%I', tbl) into n;
      if n <> 0 then
        execute 'reset role';
        raise exception 'FAIL % can read % row(s) from %', api_role, n, tbl;
      end if;

      execute format('update public.%I set created_at = created_at', tbl);
      get diagnostics n = row_count;
      if n <> 0 then
        execute 'reset role';
        raise exception 'FAIL % updated % row(s) in %', api_role, n, tbl;
      end if;

      execute format('delete from public.%I', tbl);
      get diagnostics n = row_count;
      if n <> 0 then
        execute 'reset role';
        raise exception 'FAIL % deleted % row(s) from %', api_role, n, tbl;
      end if;
    end loop;

    foreach stmt in array inserts loop
      begin
        execute stmt;
        execute 'reset role';
        raise exception 'FAIL % inserted a row: %', api_role, left(regexp_replace(stmt, '\s+', ' ', 'g'), 80);
      exception
        when insufficient_privilege then
          if sqlerrm not like '%row-level security%' then
            execute 'reset role';
            raise exception 'FAIL % insert denied by grants, not RLS: %', api_role, sqlerrm;
          end if;
      end;
    end loop;

    -- The permission check reads through RLS for API roles, so it must deny even an approved source.
    permitted := public.source_use_is_permitted(source_id::uuid, 'collect', timestamptz '2026-10-18 12:00:00+00');

    execute 'reset role';
    if permitted is distinct from false then
      raise exception 'FAIL % sees source permission through source_use_is_permitted', api_role;
    end if;
    raise notice 'ok - % reads 0 rows, changes 0 rows and is denied inserts by RLS on all % tables',
      api_role, array_length(foundation, 1);
  end loop;

  -- Sanity: the owner still sees the seeded rows and the approved permission.
  if not public.source_use_is_permitted(source_id::uuid, 'collect', timestamptz '2026-10-18 12:00:00+00') then
    raise exception 'FAIL owner no longer sees the seeded permission; the denial checks prove nothing';
  end if;
  raise notice 'ok - owner still sees the seeded rows';
end;
$$;

rollback;
