-- Sweet Seats: Phase 1 foundation
-- Canonical identity, provenance and deny-by-default source-permission records.
-- This migration intentionally excludes provider credentials, raw payloads, offer history,
-- user notifications and predictive-model tables. Those require their own approved gates.

create extension if not exists pgcrypto;

create type public.source_access_status as enum ('planned', 'reviewing', 'approved', 'active', 'suspended', 'revoked');
create type public.event_status as enum ('scheduled', 'postponed', 'cancelled', 'completed', 'unknown');
create type public.reconciliation_status as enum ('unresolved', 'provisional', 'reviewed', 'rejected');
create type public.source_record_type as enum ('artist', 'venue', 'event');
create type public.collection_status as enum ('succeeded', 'empty', 'failed', 'skipped', 'stale');

create table public.sources (
  source_id uuid primary key default gen_random_uuid(),
  slug text not null unique check (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
  name text not null,
  official_url text not null check (official_url ~ '^https://'),
  source_type text not null,
  access_status public.source_access_status not null default 'planned',
  adapter_version text,
  rate_limit_note text,
  owner_note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.source_permissions (
  permission_id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.sources(source_id) on delete restrict,
  terms_url text not null check (terms_url ~ '^https://'),
  terms_version text not null,
  evidence_note text not null,
  collect_allowed boolean not null default false,
  display_allowed boolean not null default false,
  raw_retention_allowed boolean not null default false,
  derived_retention_allowed boolean not null default false,
  feature_allowed boolean not null default false,
  train_allowed boolean not null default false,
  test_allowed boolean not null default false,
  expires_at timestamptz,
  approved_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz not null default now(),
  check (approved_at is null or revoked_at is null or approved_at <= revoked_at),
  check (expires_at is null or expires_at > created_at)
);

create index source_permissions_active_idx on public.source_permissions (source_id, expires_at)
  where revoked_at is null;

create table public.artists (
  artist_id uuid primary key default gen_random_uuid(),
  canonical_name text not null,
  artist_type text not null default 'music',
  disambiguation text,
  identity_status text not null default 'provisional' check (identity_status in ('provisional', 'reviewed', 'merged', 'retired')),
  official_links jsonb not null default '[]'::jsonb check (jsonb_typeof(official_links) = 'array'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index artists_name_idx on public.artists using gin (to_tsvector('simple', canonical_name));

create table public.venues (
  venue_id uuid primary key default gen_random_uuid(),
  name text not null,
  address_text text,
  latitude numeric(9, 6),
  longitude numeric(9, 6),
  timezone text not null default 'America/New_York',
  neighborhood text,
  identity_status text not null default 'provisional' check (identity_status in ('provisional', 'reviewed', 'merged', 'retired')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (
    (latitude is null and longitude is null)
    or (
      latitude is not null
      and longitude is not null
      and latitude between -90 and 90
      and longitude between -180 and 180
    )
  )
);

create table public.venue_configurations (
  configuration_id uuid primary key default gen_random_uuid(),
  venue_id uuid not null references public.venues(venue_id) on delete restrict,
  label text not null,
  arrangement text not null,
  capacity_estimate integer check (capacity_estimate is null or capacity_estimate > 0),
  effective_from date,
  effective_to date,
  confidence numeric(4, 3) check (confidence is null or confidence between 0 and 1),
  created_at timestamptz not null default now(),
  check (effective_to is null or effective_from is null or effective_to >= effective_from)
);

create table public.events (
  event_id uuid primary key default gen_random_uuid(),
  venue_id uuid references public.venues(venue_id) on delete restrict,
  configuration_id uuid references public.venue_configurations(configuration_id) on delete restrict,
  starts_at timestamptz,
  local_date date,
  timezone text not null default 'America/New_York',
  time_tba boolean not null default false,
  status public.event_status not null default 'unknown',
  first_seen_at timestamptz not null,
  claimed_announcement_at timestamptz,
  reconciliation_status public.reconciliation_status not null default 'unresolved',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (starts_at is not null or local_date is not null),
  check (time_tba is false or local_date is not null)
);

create index events_schedule_idx on public.events (local_date, starts_at);
create index events_venue_idx on public.events (venue_id);

create table public.event_performers (
  event_performer_id uuid primary key default gen_random_uuid(),
  event_id uuid not null references public.events(event_id) on delete cascade,
  artist_id uuid not null references public.artists(artist_id) on delete restrict,
  role text not null default 'performer',
  billing_order integer check (billing_order is null or billing_order >= 0),
  created_at timestamptz not null default now(),
  unique (event_id, artist_id, role)
);

create table public.source_entity_mappings (
  mapping_id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.sources(source_id) on delete restrict,
  record_type public.source_record_type not null,
  vendor_id text not null,
  artist_id uuid references public.artists(artist_id) on delete restrict,
  venue_id uuid references public.venues(venue_id) on delete restrict,
  event_id uuid references public.events(event_id) on delete restrict,
  mapping_confidence numeric(4, 3) not null default 0.5 check (mapping_confidence between 0 and 1),
  mapping_method text not null,
  created_at timestamptz not null default now(),
  check (
    (record_type = 'artist' and artist_id is not null and venue_id is null and event_id is null) or
    (record_type = 'venue' and venue_id is not null and artist_id is null and event_id is null) or
    (record_type = 'event' and event_id is not null and artist_id is null and venue_id is null)
  ),
  unique (source_id, record_type, vendor_id)
);

create table public.collection_runs (
  collection_run_id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.sources(source_id) on delete restrict,
  logical_key text not null,
  status public.collection_status not null,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  adapter_version text not null,
  permission_id uuid references public.source_permissions(permission_id) on delete restrict,
  item_count integer not null default 0 check (item_count >= 0),
  error_code text,
  error_detail_redacted text,
  created_at timestamptz not null default now(),
  check ((status in ('succeeded', 'empty') and finished_at is not null) or status not in ('succeeded', 'empty')),
  unique (source_id, logical_key)
);

create or replace function public.source_use_is_permitted(
  requested_source_id uuid,
  requested_use text,
  as_of timestamptz default now()
) returns boolean
language sql
stable
set search_path = public
as $$
  select exists (
    select 1
    from public.sources source
    join public.source_permissions permission on permission.source_id = source.source_id
    where source.source_id = requested_source_id
      and source.access_status in ('approved', 'active')
      and permission.approved_at is not null
      and permission.revoked_at is null
      and (permission.expires_at is null or permission.expires_at > as_of)
      and case requested_use
        when 'collect' then permission.collect_allowed
        when 'display' then permission.display_allowed
        when 'raw_retention' then permission.raw_retention_allowed
        when 'derived_retention' then permission.derived_retention_allowed
        when 'feature' then permission.feature_allowed
        when 'train' then permission.train_allowed
        when 'test' then permission.test_allowed
        else false
      end
  );
$$;

-- No public table access is granted by default. API workers use a service role;
-- authenticated user-facing policies are introduced with the user/watchlist migration.
alter table public.sources enable row level security;
alter table public.source_permissions enable row level security;
alter table public.artists enable row level security;
alter table public.venues enable row level security;
alter table public.venue_configurations enable row level security;
alter table public.events enable row level security;
alter table public.event_performers enable row level security;
alter table public.source_entity_mappings enable row level security;
alter table public.collection_runs enable row level security;

