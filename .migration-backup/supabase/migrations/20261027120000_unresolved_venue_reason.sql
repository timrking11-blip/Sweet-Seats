-- An observation whose venue has no reviewed crosswalk is a review item with its own
-- reason (unresolved_venue_identity), alongside unmapped artists and ambiguous matches.
alter table public.source_unresolved_records
  drop constraint source_unresolved_records_reason_check,
  add constraint source_unresolved_records_reason_check check (reason in (
    'unresolved_venue_identity', 'unresolved_typed_identity', 'ambiguous_event_match'));
