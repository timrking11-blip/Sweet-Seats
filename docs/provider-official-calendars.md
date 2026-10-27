# Provider: official artist and venue calendars (iCalendar)

Status: **planned, disconnected.** The adapter exists and is tested offline against a
synthetic fixture. No feed is chosen, no permission is approved and no live request
has been made.

## Role

Roadmap Phase 3 "curated official monitors": an artist's or venue's own published
calendar, the source expected to announce shows first. Its purpose is the lead-time
question: does Sweet Seats learn about shows earlier from official calendars than from
Ticketmaster Discovery?

## What the adapter does

`services/api/app/official_feeds.py`

- Reads RFC 5545 iCalendar: unfolds lines, reads VEVENTs, ignores nested alarms.
- `DTSTART` in UTC, with `TZID`, or date-only (`starts_at` null, `time_tba`). A floating
  time with no zone is rejected rather than guessed.
- `STATUS` CONFIRMED / CANCELLED / TENTATIVE map to scheduled / cancelled / unknown.
- Identity is never decided by name. A venue feed's venue and an artist feed's artist
  come from its configuration. Other names become feed-scoped vendor keys
  (`name:glass-harbor`, `location:example-hall`); only a reviewed crosswalk maps a key
  to a canonical UUID. Unmapped keys go to the review queue.
- The calendar's own `CREATED` / `DTSTAMP` is kept as display metadata only. Lead time
  uses `available_at`, when Sweet Seats could know, never the source's claim.
- `fetch_feed` checks the `collect` permission, then `SWEET_SEATS_OFFICIAL_FEEDS_ENABLED`,
  before any request; https only, a 2 MB cap, and conditional GET (`If-None-Match`,
  `If-Modified-Since`) so an unchanged calendar returns `not_modified`.
- Requests reach only the host of the registry entry's owner-approved `official_url`,
  on port 443. The host must resolve only to public addresses: private, loopback,
  link-local (including cloud metadata), multicast, reserved, unspecified, shared and
  documentation ranges, and IPv6 forms that embed an IPv4 address, are refused. The
  connection is pinned to the checked address, and TLS still verifies the host's
  certificate. Redirects are followed by hand, at most 3, each to the same approved
  host and each re-checked; anything else ends the fetch with a fixed error code.

## Provider ingestion and the lead-time comparison

`discovery.ingest_collection` reconciles any adapter's mapped records through the same
path as the synthetic fixtures. Permissions come from the owner-approved registry entry
(`source_registry.planned_official_calendar`), never from the incoming collection, so a
payload cannot grant itself rights. `tests/test_official_feeds.py` runs the comparison
end to end: the same show arrives from the venue calendar and from Ticketmaster,
reconciles to one event through reviewed mappings, and `lead_time_report` credits the
calendar with seeing it first.

## Activation needs owner approval per feed

1. The feed list: which NYC venues and artists, and each calendar URL.
2. Each site's terms and robots policy checked, recorded as a SourcePermission
   (terms version, evidence, validity window, per-use grants).
3. Reviewed crosswalks for each feed's venue and artist keys.
4. `SWEET_SEATS_OFFICIAL_FEEDS_ENABLED=true` in the worker environment.
5. A decision on persisting live observations in PostgreSQL (see the alerts runtime
   contract): the database still accepts only synthetic `.invalid` URLs.
