-- First-seen evidence and weekly pilot metrics (Build Plan S3, Step 6; proposed).
--
-- The pilot asks whether official calendars make shows knowable before the listing API
-- does. Its evidence is, per canonical event and source, the earliest time the source
-- made the event available (observation available_at). That history is the asset, so it
-- is kept apart from the observations, which a reseed or replay can change, and it is
-- append-only:
--
-- event_first_seen
--   - written only by a trigger on source_event_records: a row is added when an
--     observation makes an (event, source) pair available earlier than any row so far.
--     The current first-seen time is the minimum per pair; rows are never rewritten.
--   - UPDATE is refused for every role. DELETE is refused unless the transaction sets
--     sweet_seats.rights_purge = 'on': the hook for the G-08 purge of data derived from
--     a revoked or expired permission (that job, and its retention period, are separate).
--
-- pilot_metrics
--   - one row per period and metrics version, written by the weekly job
--     (services/api/app/pilot_metrics.py). Append-only: a recomputed week is a new
--     metrics_version, never an edited row.
--
-- Both are internal measurements: RLS on, no policies, no Data API privileges.

create table public.event_first_seen (
  event_id uuid not null references public.events(event_id) on delete restrict,
  source_id uuid not null references public.sources(source_id) on delete restrict,
  first_available_at timestamptz not null,
  first_observed_at timestamptz not null,
  source_record_id uuid not null,
  collection_run_id uuid not null,
  permission_id uuid not null,
  recorded_at timestamptz not null default now(),
  primary key (event_id, source_id, first_available_at),
  check (first_observed_at <= first_available_at)
);

create index event_first_seen_available_idx on public.event_first_seen (first_available_at);

create table public.pilot_metrics (
  period_start date not null,
  period_end date not null,
  metrics_version text not null check (metrics_version ~ '^[a-z0-9][a-z0-9._-]{0,63}$'),
  computed_at timestamptz not null default now(),
  metrics jsonb not null check (jsonb_typeof(metrics) = 'object'),
  primary key (period_start, metrics_version),
  check (period_end > period_start)
);

alter table public.event_first_seen enable row level security;
alter table public.pilot_metrics enable row level security;
revoke all on public.event_first_seen from anon, authenticated;
revoke all on public.pilot_metrics from anon, authenticated;

create function public.refuse_first_seen_change() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'DELETE' and current_setting('sweet_seats.rights_purge', true) = 'on'
     and current_setting('role') not in ('anon', 'authenticated') then
    return old;
  end if;
  raise exception 'first_seen_is_append_only' using errcode = '42501';
end;
$$;

create trigger event_first_seen_append_only
  before update or delete on public.event_first_seen
  for each row execute function public.refuse_first_seen_change();

create function public.refuse_pilot_metrics_change() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception 'pilot_metrics_are_append_only' using errcode = '42501';
end;
$$;

create trigger pilot_metrics_append_only
  before update or delete on public.pilot_metrics
  for each row execute function public.refuse_pilot_metrics_change();

create trigger pilot_metrics_no_truncate
  before truncate on public.pilot_metrics
  for each statement execute function public.refuse_pilot_metrics_change();

create function public.record_first_seen() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  available timestamptz := new.available_at::timestamptz;
begin
  if not exists (
    select 1 from public.event_first_seen f
    where f.event_id = new.event_id and f.source_id = new.source_id
      and f.first_available_at <= available) then
    insert into public.event_first_seen (event_id, source_id, first_available_at,
      first_observed_at, source_record_id, collection_run_id, permission_id)
    values (new.event_id, new.source_id, available, new.observed_at::timestamptz,
      new.source_record_id, new.collection_run_id, new.permission_id);
  end if;
  return null;
end;
$$;

create trigger source_event_records_record_first_seen
  after insert on public.source_event_records
  for each row execute function public.record_first_seen();

revoke all on function public.refuse_first_seen_change() from public, anon, authenticated;
revoke all on function public.refuse_pilot_metrics_change() from public, anon, authenticated;
revoke all on function public.record_first_seen() from public, anon, authenticated;

-- Backfill from observations already stored: the earliest one per (event, source).
insert into public.event_first_seen (event_id, source_id, first_available_at,
  first_observed_at, source_record_id, collection_run_id, permission_id)
select distinct on (r.event_id, r.source_id)
  r.event_id, r.source_id, r.available_at::timestamptz, r.observed_at::timestamptz,
  r.source_record_id, r.collection_run_id, r.permission_id
from public.source_event_records r
order by r.event_id, r.source_id, r.available_at::timestamptz, r.source_record_id;
