-- Waitlist with consent evidence and attribution (Build Plan S4; proposed).
--
-- The coming-soon page is the only public surface, and it captured nothing. A sign-up
-- records the email, the consent copy version and a hash of the exact copy shown (both
-- chosen by the server, never the client), where the visitor came from, and the artists
-- they would follow (free signal for choosing the pilot panel).
--
-- Only the API writes here, as the table owner. The Data API roles get no privileges
-- and there are no RLS policies: anon and authenticated can neither read nor insert,
-- so a list of emails is never exposed to the browser.
--
-- A repeat sign-up keeps the first record (first-touch attribution and the original
-- consent). invited_at is set when the person is invited to the pilot.

create table public.waitlist_signups (
  signup_id uuid primary key default gen_random_uuid(),
  email text not null unique
    check (email = lower(btrim(email))
           and length(email) between 6 and 254
           and email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'),
  consent_version text not null check (consent_version ~ '^[a-z0-9][a-z0-9._-]{0,63}$'),
  consent_copy_sha256 text not null check (consent_copy_sha256 ~ '^[0-9a-f]{64}$'),
  consented_at timestamptz not null default now(),
  source text not null default 'direct' check (source ~ '^[a-z0-9][a-z0-9._-]{0,63}$'),
  artists text[] not null default '{}'
    check (cardinality(artists) <= 10
           and array_to_string(artists, '') !~ '[[:cntrl:]]'
           and length(array_to_string(artists, '')) <= 1000),
  invited_at timestamptz,
  created_at timestamptz not null default now(),
  check (invited_at is null or invited_at >= created_at)
);

create index waitlist_signups_source_idx on public.waitlist_signups (source);

alter table public.waitlist_signups enable row level security;
revoke all on public.waitlist_signups from anon, authenticated;
