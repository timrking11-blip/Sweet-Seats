-- Sweet Seats: MusicBrainz collection runs
-- Every MusicBrainz network call records one public.collection_runs row: its outcome, item
-- count, adapter version and the SourcePermission it ran under. Rows carry fixed error codes
-- and hashed or MBID-based logical keys only; no artist names or provider payloads.

update public.sources
set adapter_version = 'musicbrainz-ws2-0.1', updated_at = now()
where slug = 'musicbrainz' and adapter_version is null;

-- Records one finished call. permission_id is the newest permission that grants 'collect' at
-- the time of recording; it is null when none does (for example, revoked mid-call), and that
-- null is itself the evidence. Returns the new collection_run_id.
create or replace function public.record_musicbrainz_run(
  run_logical_key text,
  run_status text,
  run_item_count integer,
  run_error_code text,
  run_adapter_version text,
  run_started_at timestamptz default null
) returns uuid
language plpgsql
set search_path = public
as $$
declare
  mb_source_id uuid;
  current_permission_id uuid;
  recorded_at timestamptz := now();
  new_run_id uuid;
begin
  -- operation:subject:nonce, where subject is a SHA-256 of the normalized name or an MBID.
  if run_logical_key is null
     or run_logical_key !~ '^artist-(search:[0-9a-f]{64}|lookup:[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}):[0-9a-f]{32}$' then
    raise exception 'invalid_logical_key' using errcode = '22023';
  end if;
  if run_status is null or run_status not in ('succeeded', 'empty', 'failed') then
    raise exception 'invalid_run_status' using errcode = '22023';
  end if;
  if run_item_count is null or run_item_count < 0
     or (run_status = 'succeeded') <> (run_item_count > 0) then
    raise exception 'invalid_item_count' using errcode = '22023';
  end if;
  -- A failure carries a fixed snake_case code; a success carries none.
  if (run_status = 'failed') <> (run_error_code is not null)
     or run_error_code !~ '^[a-z][a-z0-9_]{0,63}$' then
    raise exception 'invalid_error_code' using errcode = '22023';
  end if;
  if run_adapter_version is null or run_adapter_version !~ '^[a-z0-9][a-z0-9.-]{0,63}$' then
    raise exception 'invalid_adapter_version' using errcode = '22023';
  end if;

  select source_id into mb_source_id from public.sources where slug = 'musicbrainz';
  if mb_source_id is null then
    raise exception 'musicbrainz_source_missing' using errcode = '42704';
  end if;

  -- Same window as source_use_is_permitted: approved, not yet revoked, not expired.
  select p.permission_id into current_permission_id
  from public.source_permissions p
  where p.source_id = mb_source_id
    and p.collect_allowed
    and p.approved_at is not null
    and p.approved_at <= recorded_at
    and (p.revoked_at is null or p.revoked_at > recorded_at)
    and (p.expires_at is null or p.expires_at > recorded_at)
  order by p.approved_at desc, p.created_at desc
  limit 1;

  insert into public.collection_runs
    (source_id, logical_key, status, started_at, finished_at, adapter_version, permission_id,
     item_count, error_code)
  values
    (mb_source_id, run_logical_key, run_status::public.collection_status,
     least(coalesce(run_started_at, recorded_at), recorded_at), recorded_at,
     run_adapter_version, current_permission_id, run_item_count, run_error_code)
  returning collection_run_id into new_run_id;

  return new_run_id;
end;
$$;

-- Server-only, like the artist cache functions in 202610180001.
revoke execute on function public.record_musicbrainz_run(text, text, integer, text, text, timestamptz)
  from public, anon, authenticated;
grant execute on function public.record_musicbrainz_run(text, text, integer, text, text, timestamptz)
  to service_role;
