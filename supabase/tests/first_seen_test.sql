-- First-seen evidence and pilot metrics (Step 6): append-only, invisible to the Data API,
-- and removable only by an explicit rights purge. Run after the emulation scripts and
-- the migrations. Everything runs in one transaction and is rolled back.

begin;

do $$
declare
  v_source uuid;
  v_event uuid;
  n bigint;
  api_role text;
begin
  insert into public.sources (slug, name, official_url, source_type, access_status)
  values ('first-seen-test', 'First seen test source', 'https://example.test/fs', 'official_calendar', 'approved')
  returning source_id into v_source;
  insert into public.events (local_date, first_seen_at) values (date '2026-12-01', now())
  returning event_id into v_event;
  insert into public.event_first_seen (event_id, source_id, first_available_at, first_observed_at,
    source_record_id, collection_run_id, permission_id)
  values (v_event, v_source, now(), now() - interval '1 minute', gen_random_uuid(), gen_random_uuid(),
    gen_random_uuid());
  insert into public.pilot_metrics (period_start, period_end, metrics_version, metrics)
  values (date '2026-11-16', date '2026-11-23', 'pilot-metrics-test', '{"lead_time": {}}');

  -- Neither the Data API roles nor anyone without the purge flag rewrites the evidence.
  foreach api_role in array array['anon', 'authenticated'] loop
    if has_table_privilege(api_role, 'public.event_first_seen', 'SELECT')
       or has_table_privilege(api_role, 'public.pilot_metrics', 'SELECT') then
      raise exception 'FAIL % can read first-seen evidence or pilot metrics', api_role;
    end if;
  end loop;
  begin
    update public.event_first_seen set first_available_at = first_available_at + interval '1 day';
    raise exception 'FAIL first-seen evidence was rewritten';
  exception when insufficient_privilege then null;
  end;
  begin
    delete from public.event_first_seen;
    raise exception 'FAIL first-seen evidence was deleted without a rights purge';
  exception when insufficient_privilege then null;
  end;
  begin
    update public.pilot_metrics set metrics = '{}';
    raise exception 'FAIL a pilot metrics row was edited';
  exception when insufficient_privilege then null;
  end;
  begin
    delete from public.pilot_metrics;
    raise exception 'FAIL a pilot metrics row was deleted';
  exception when insufficient_privilege then null;
  end;
  raise notice 'ok - first-seen evidence and pilot metrics are append-only and private';

  -- The G-08 purge path: an explicit, transaction-scoped flag.
  perform set_config('sweet_seats.rights_purge', 'on', true);
  delete from public.event_first_seen where source_id = v_source;
  get diagnostics n = row_count;
  perform set_config('sweet_seats.rights_purge', '', true);
  if n <> 1 then
    raise exception 'FAIL the rights purge removed % rows; expected 1', n;
  end if;
  raise notice 'ok - only an explicit rights purge removes first-seen evidence';
end;
$$;

rollback;
