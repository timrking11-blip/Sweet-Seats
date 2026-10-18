-- Align the database with the Python discovery contract.
-- 1. 'rescheduled' is accepted by normalize(), the API model and the web type, but the
--    enum rejected it, rolling back a whole seed with store_write_failed.
-- 2. A permission needs approval evidence and a terms version (SS-DATA-0.1
--    SourcePermission: "approval evidence required"). Empty strings no longer permit.
--    The time window and source-status rules are unchanged.

alter type public.event_status add value if not exists 'rescheduled' after 'scheduled';

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
      and btrim(permission.evidence_note) <> ''
      and btrim(permission.terms_version) <> ''
      -- A permission applies only within [approved_at, revoked_at/expires_at) at as_of.
      -- A null as_of makes these comparisons null, which denies.
      and permission.approved_at is not null
      and permission.approved_at <= as_of
      and (permission.revoked_at is null or permission.revoked_at > as_of)
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
