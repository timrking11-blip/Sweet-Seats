-- Local synthetic discovery review queue. Apply only to a disposable development database.
-- Observations without a reviewed typed crosswalk (or with an ambiguous event match) are
-- retained for review instead of being projected; no public policies, backend access only.
create table public.source_unresolved_records (
  source_record_id uuid primary key,
  source_id uuid not null references public.sources(source_id),
  permission_id uuid not null,
  collection_run_id uuid not null,
  reason text not null check (reason in ('unresolved_typed_identity', 'ambiguous_event_match')),
  payload_hash text not null check (payload_hash ~ '^[0-9a-f]{64}$'),
  observation jsonb not null check (jsonb_typeof(observation) = 'object'),
  foreign key (permission_id, source_id) references public.source_permissions(permission_id, source_id),
  foreign key (collection_run_id, source_id, permission_id)
    references public.collection_runs(collection_run_id, source_id, permission_id)
);
create index source_unresolved_records_run_idx on public.source_unresolved_records(collection_run_id);
alter table public.source_unresolved_records enable row level security;
