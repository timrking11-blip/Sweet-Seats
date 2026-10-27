-- Sweet Seats: MusicBrainz artist identity cache
-- Registers MusicBrainz as a planned (deny-by-default) source and adds server-side functions
-- that read and write MBID -> artist mappings. The cache is the existing artists and
-- source_entity_mappings tables; nothing here stores raw MusicBrainz payloads.
--
-- Activation needs an owner-approved source_permissions row (collect, derived_retention) and
-- access_status 'approved' or 'active'. Until then every function below fails closed.

insert into public.sources (slug, name, official_url, source_type, access_status, rate_limit_note, owner_note)
values (
  'musicbrainz',
  'MusicBrainz',
  'https://musicbrainz.org',
  'identity',
  'planned',
  'Web service: about 1 request/second per IP; a meaningful User-Agent with contact is required.',
  'Identity fields only: MBID, name, disambiguation. Record terms and permitted uses before activation.'
)
on conflict (slug) do nothing;

create index if not exists artists_lower_name_idx on public.artists (lower(canonical_name));

create or replace function public.musicbrainz_use_is_permitted(requested_use text)
returns boolean
language sql
stable
set search_path = public
as $$
  select coalesce(
    (select public.source_use_is_permitted(source_id, requested_use)
     from public.sources where slug = 'musicbrainz'),
    false
  );
$$;

-- Cached rows are served only while derived retention is still permitted.
create or replace function public.musicbrainz_artist_by_mbid(requested_mbid uuid)
returns table (
  artist_id uuid,
  mbid uuid,
  canonical_name text,
  disambiguation text,
  mapping_confidence numeric,
  mapping_method text
)
language sql
stable
set search_path = public
as $$
  select a.artist_id, m.vendor_id::uuid, a.canonical_name, a.disambiguation,
         m.mapping_confidence, m.mapping_method
  from public.source_entity_mappings m
  join public.sources s on s.source_id = m.source_id and s.slug = 'musicbrainz'
  join public.artists a on a.artist_id = m.artist_id
  where m.record_type = 'artist'
    and m.vendor_id = requested_mbid::text
    and a.identity_status <> 'retired'
    and public.source_use_is_permitted(s.source_id, 'derived_retention');
$$;

create or replace function public.musicbrainz_artists_by_name(requested_name text)
returns table (
  artist_id uuid,
  mbid uuid,
  canonical_name text,
  disambiguation text,
  mapping_confidence numeric,
  mapping_method text
)
language sql
stable
set search_path = public
as $$
  select a.artist_id, m.vendor_id::uuid, a.canonical_name, a.disambiguation,
         m.mapping_confidence, m.mapping_method
  from public.artists a
  join public.source_entity_mappings m on m.artist_id = a.artist_id and m.record_type = 'artist'
  join public.sources s on s.source_id = m.source_id and s.slug = 'musicbrainz'
  where lower(a.canonical_name) = lower(btrim(requested_name))
    and a.identity_status <> 'retired'
    and public.source_use_is_permitted(s.source_id, 'derived_retention');
$$;

-- Creates the artist and its MBID mapping in one transaction, or refreshes a provisional
-- artist that is already mapped. Reviewed artists keep their curated name. run_id is the
-- collection run that fetched the artist; see the check below.
create or replace function public.cache_musicbrainz_artist(
  requested_mbid uuid,
  artist_name text,
  artist_disambiguation text,
  confidence numeric,
  method text,
  run_id uuid
) returns uuid
language plpgsql
set search_path = public
as $$
declare
  mb_source_id uuid;
  cached_artist_id uuid;
  clean_name text := btrim(artist_name);
  clean_disambiguation text := nullif(btrim(artist_disambiguation), '');
begin
  if clean_name is null or length(clean_name) not between 1 and 300 then
    raise exception 'invalid_artist_name' using errcode = '22023';
  end if;

  select source_id into mb_source_id from public.sources where slug = 'musicbrainz';
  if mb_source_id is null or not public.source_use_is_permitted(mb_source_id, 'derived_retention') then
    raise exception 'musicbrainz_retention_not_permitted' using errcode = '42501';
  end if;

  -- Provenance first: a write needs the finalized, succeeded MusicBrainz collection run that
  -- fetched this artist, opened under a captured permission (202610180002). A lookup run
  -- must be for this MBID; a search run's key hashes the name, so any succeeded search run.
  if not exists (
    select 1 from public.collection_runs r
    where r.collection_run_id = run_id
      and r.source_id = mb_source_id
      and r.status = 'succeeded'
      and r.finished_at is not null
      and r.permission_id is not null
      and (r.logical_key like 'artist-search:%'
           or r.logical_key like 'artist-lookup:' || requested_mbid::text || ':%')
  ) then
    raise exception 'musicbrainz_run_required' using errcode = '22023';
  end if;

  -- Serialize concurrent writers for the same MBID so only one artist row is created.
  perform pg_advisory_xact_lock(hashtextextended('musicbrainz-artist:' || requested_mbid::text, 0));

  select m.artist_id into cached_artist_id
  from public.source_entity_mappings m
  where m.source_id = mb_source_id and m.record_type = 'artist' and m.vendor_id = requested_mbid::text;

  if cached_artist_id is not null then
    update public.artists
    set canonical_name = clean_name, disambiguation = clean_disambiguation, updated_at = now()
    where artist_id = cached_artist_id and identity_status = 'provisional';
    return cached_artist_id;
  end if;

  insert into public.artists (canonical_name, disambiguation)
  values (clean_name, clean_disambiguation)
  returning artist_id into cached_artist_id;

  insert into public.source_entity_mappings
    (source_id, record_type, vendor_id, artist_id, mapping_confidence, mapping_method)
  values
    (mb_source_id, 'artist', requested_mbid::text, cached_artist_id, confidence, method);

  return cached_artist_id;
end;
$$;

-- Server-only: the API worker calls these with the service role. Supabase grants execute on
-- new public functions to anon and authenticated by default, so revoke it explicitly.
revoke execute on function public.musicbrainz_use_is_permitted(text) from public, anon, authenticated;
revoke execute on function public.musicbrainz_artist_by_mbid(uuid) from public, anon, authenticated;
revoke execute on function public.musicbrainz_artists_by_name(text) from public, anon, authenticated;
revoke execute on function public.cache_musicbrainz_artist(uuid, text, text, numeric, text, uuid)
  from public, anon, authenticated;
grant execute on function public.musicbrainz_use_is_permitted(text) to service_role;
grant execute on function public.musicbrainz_artist_by_mbid(uuid) to service_role;
grant execute on function public.musicbrainz_artists_by_name(text) to service_role;
grant execute on function public.cache_musicbrainz_artist(uuid, text, text, numeric, text, uuid) to service_role;
