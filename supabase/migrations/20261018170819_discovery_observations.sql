-- Local synthetic discovery. Apply only to a disposable development database.
-- No public policies; source facts are projected by the backend after use checks.
alter table public.sources add column discovery_metadata jsonb;
alter table public.events add column discovery_match_key text;
alter table public.collection_runs add column replay_digest text
  check (replay_digest ~ '^[0-9a-f]{64}$');
alter table public.collection_runs add constraint collection_run_source_key
  unique (collection_run_id, source_id, permission_id);
alter table public.source_permissions add constraint permission_source_key
  unique (permission_id, source_id);
alter table public.collection_runs add constraint collection_run_permission_source_fk
  foreign key (permission_id, source_id) references public.source_permissions(permission_id, source_id);
alter table public.source_entity_mappings add constraint mapping_event_source_key
  unique (source_id, record_type, vendor_id, event_id);

create table public.discovery_state (
  singleton boolean primary key default true check (singleton),
  version text not null check (version = 'SS-DISCOVERY-DEMO-0.1'),
  synthetic boolean not null check (synthetic),
  unresolved_records jsonb not null default '{}'::jsonb
    check (jsonb_typeof(unresolved_records) = 'object')
);

create table public.source_event_records (
  source_record_id uuid primary key,
  source_id uuid not null references public.sources(source_id),
  permission_id uuid not null,
  collection_run_id uuid not null,
  event_id uuid not null references public.events(event_id),
  vendor_event_id text not null,
  record_type public.source_record_type not null default 'event' check (record_type = 'event'),
  venue_id uuid not null references public.venues(venue_id),
  title text not null,
  starts_at text,
  local_date date not null,
  timezone text not null check (timezone = 'America/New_York'),
  status public.event_status not null,
  observed_at text not null,
  available_at text not null,
  source_url text not null check (source_url ~ '^https://[^/?#@]+[.]invalid(/[^?#]*)?$'),
  ticket_url text check (ticket_url ~ '^https://[^/?#@]+[.]invalid(/[^?#]*)?$'),
  vendor_venue_id text not null,
  adapter_version text not null,
  payload_hash text not null check (payload_hash ~ '^[0-9a-f]{64}$'),
  foreign key (permission_id, source_id) references public.source_permissions(permission_id, source_id),
  foreign key (collection_run_id, source_id, permission_id)
    references public.collection_runs(collection_run_id, source_id, permission_id),
  foreign key (source_id, record_type, vendor_event_id, event_id)
    references public.source_entity_mappings(source_id, record_type, vendor_id, event_id),
  check (observed_at::timestamptz <= available_at::timestamptz)
);
create index source_event_records_event_idx on public.source_event_records(event_id);
create index source_event_records_run_idx on public.source_event_records(collection_run_id);

create table public.source_event_performers (
  source_record_id uuid not null references public.source_event_records(source_record_id),
  artist_id uuid not null references public.artists(artist_id),
  role text not null check (role in ('headliner', 'support', 'performer')),
  billing_order integer not null check (billing_order >= 0),
  primary key (source_record_id, artist_id, role)
);
alter table public.discovery_state enable row level security;
alter table public.source_event_records enable row level security;
alter table public.source_event_performers enable row level security;
