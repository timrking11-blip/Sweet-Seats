-- Local synthetic discovery: observations quarantined for review. Apply only to a
-- disposable development database. No public policies; the backend projects these after
-- use checks, exactly like source_event_records.
--
-- An observation lands here when its schema and facts validated but it has no reviewed
-- typed crosswalk (unresolved_typed_identity) or it matches more than one event
-- (ambiguous_event_match). observation holds only the declared, validated record fields
-- the ingester kept, never an arbitrary provider payload.
create table public.source_review_records (
  source_record_id uuid primary key,
  source_id uuid not null references public.sources(source_id),
  permission_id uuid not null,
  collection_run_id uuid not null,
  vendor_event_id text not null,
  title text not null,
  reason text not null check (reason in ('unresolved_typed_identity', 'ambiguous_event_match')),
  payload_hash text not null check (payload_hash ~ '^[0-9a-f]{64}$'),
  observation jsonb not null check (jsonb_typeof(observation) = 'object'),
  foreign key (permission_id, source_id) references public.source_permissions(permission_id, source_id),
  foreign key (collection_run_id, source_id, permission_id)
    references public.collection_runs(collection_run_id, source_id, permission_id),
  -- Typed columns are the authority; the stored observation must agree with them.
  check ((observation->>'source_record_id')::uuid = source_record_id
         and (observation->>'source_id')::uuid = source_id
         and (observation->>'permission_id')::uuid = permission_id
         and observation->>'vendor_event_id' = vendor_event_id
         and observation->>'title' = title
         and observation->>'reason' = reason
         and observation->>'payload_hash' = payload_hash)
);
create index source_review_records_run_idx on public.source_review_records(collection_run_id);
alter table public.source_review_records enable row level security;
