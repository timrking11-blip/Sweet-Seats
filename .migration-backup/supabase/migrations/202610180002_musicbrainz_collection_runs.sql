-- Sweet Seats: MusicBrainz collection runs
-- Every MusicBrainz network call is covered by one public.collection_runs row. Rows carry
-- fixed error codes and hashed or MBID-based logical keys only; no artist names or provider
-- payloads.
--
-- Lifecycle (fail closed):
--   1. begin_musicbrainz_run opens the row BEFORE any network access. It requires the
--      musicbrainz source to be approved or active and a SourcePermission that grants
--      'collect', was approved at or before the run start, and is neither revoked nor expired
--      at the run start. That exact permission_id is captured on the row. If no permission
--      qualifies, or the row cannot be written, the caller must make no request.
--      The row opens as status 'failed', error_code 'incomplete', finished_at null, so a run
--      that is never finalized reads as a failure, never a success.
--   2. finish_musicbrainz_run finalizes that same row exactly once with the outcome. It never
--      creates a row and never changes the captured permission.
--   3. cache_musicbrainz_artist (202610180001) accepts a write only with a finalized,
--      succeeded MusicBrainz run that captured a permission.
--
-- Retries: one logical request is one run. The client's bounded retries (MAX_RETRIES, and a
-- capped Retry-After wait; services/api/app/musicbrainz.py) are attempts inside that run,
-- authorized by the permission captured when it opened, and are not recorded separately.
-- Because a run is finalized once and logical keys are unique, a retry cannot open or close
-- another row. A new resolve call is a new logical request with a new key and a new run.

update public.sources
set adapter_version = 'musicbrainz-ws2-0.1', updated_at = now()
where slug = 'musicbrainz' and adapter_version is null;

-- Opens a run and returns its id with the authorizing permission and start time.
create or replace function public.begin_musicbrainz_run(
  run_logical_key text,
  run_adapter_version text
) returns table (collection_run_id uuid, permission_id uuid, started_at timestamptz)
language plpgsql
set search_path = public
as $$
#variable_conflict use_column
declare
  mb_source_id uuid;
  mb_access_status public.source_access_status;
  run_started_at timestamptz := now();
  authorizing_permission_id uuid;
  new_run_id uuid;
begin
  -- operation:subject:nonce, where subject is a SHA-256 of the normalized name or an MBID.
  if run_logical_key is null
     or run_logical_key !~ '^artist-(search:[0-9a-f]{64}|lookup:[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}):[0-9a-f]{32}$' then
    raise exception 'invalid_logical_key' using errcode = '22023';
  end if;
  if run_adapter_version is null or run_adapter_version !~ '^[a-z0-9][a-z0-9.-]{0,63}$' then
    raise exception 'invalid_adapter_version' using errcode = '22023';
  end if;

  -- Share locks hold the source status and the chosen permission until this run row commits,
  -- so a concurrent revocation or status change cannot interleave with the capture.
  select s.source_id, s.access_status into mb_source_id, mb_access_status
  from public.sources s where s.slug = 'musicbrainz'
  for share;
  if mb_source_id is null then
    raise exception 'musicbrainz_source_missing' using errcode = '42704';
  end if;
  if mb_access_status not in ('approved', 'active') then
    raise exception 'musicbrainz_source_not_approved' using errcode = '42501';
  end if;

  -- Same window as source_use_is_permitted, evaluated at the run start.
  select p.permission_id into authorizing_permission_id
  from public.source_permissions p
  where p.source_id = mb_source_id
    and p.collect_allowed
    and p.approved_at is not null
    and p.approved_at <= run_started_at
    and (p.revoked_at is null or p.revoked_at > run_started_at)
    and (p.expires_at is null or p.expires_at > run_started_at)
  order by p.approved_at desc, p.created_at desc, p.permission_id
  limit 1
  for share;
  if authorizing_permission_id is null then
    raise exception 'musicbrainz_collect_not_permitted' using errcode = '42501';
  end if;

  insert into public.collection_runs
    (source_id, logical_key, status, started_at, finished_at, adapter_version, permission_id,
     item_count, error_code)
  values
    (mb_source_id, run_logical_key, 'failed', run_started_at, null, run_adapter_version,
     authorizing_permission_id, 0, 'incomplete')
  returning public.collection_runs.collection_run_id into new_run_id;

  return query select new_run_id, authorizing_permission_id, run_started_at;
end;
$$;

-- Finalizes an open run exactly once. Raises if the run is unknown, not MusicBrainz, or
-- already finalized.
create or replace function public.finish_musicbrainz_run(
  run_id uuid,
  run_status text,
  run_item_count integer,
  run_error_code text
) returns void
language plpgsql
set search_path = public
as $$
begin
  if run_status is null or run_status not in ('succeeded', 'empty', 'failed') then
    raise exception 'invalid_run_status' using errcode = '22023';
  end if;
  if run_item_count is null or run_item_count < 0
     or (run_status = 'succeeded') <> (run_item_count > 0) then
    raise exception 'invalid_item_count' using errcode = '22023';
  end if;
  -- A failure carries a fixed snake_case code; a success carries none. 'incomplete' is
  -- reserved for runs that were never finalized.
  if (run_status = 'failed') <> (run_error_code is not null)
     or run_error_code !~ '^[a-z][a-z0-9_]{0,63}$'
     or run_error_code = 'incomplete' then
    raise exception 'invalid_error_code' using errcode = '22023';
  end if;

  update public.collection_runs r
  set status = run_status::public.collection_status,
      item_count = run_item_count,
      error_code = run_error_code,
      finished_at = greatest(now(), r.started_at)
  from public.sources s
  where r.collection_run_id = run_id
    and s.source_id = r.source_id
    and s.slug = 'musicbrainz'
    and r.finished_at is null
    and r.status = 'failed'
    and r.error_code = 'incomplete';
  if not found then
    raise exception 'musicbrainz_run_not_open' using errcode = '55000';
  end if;
end;
$$;

-- Server-only, like the artist cache functions in 202610180001.
revoke execute on function public.begin_musicbrainz_run(text, text)
  from public, anon, authenticated;
revoke execute on function public.finish_musicbrainz_run(uuid, text, integer, text)
  from public, anon, authenticated;
grant execute on function public.begin_musicbrainz_run(text, text) to service_role;
grant execute on function public.finish_musicbrainz_run(uuid, text, integer, text) to service_role;
