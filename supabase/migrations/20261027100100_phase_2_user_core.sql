-- Phase 2 core: user profiles, artist follows and notification consent (SS-DATA-0.1
-- User, ArtistFollow, NotificationSubscription).
--
-- First-party record rule (Notion 02, approved 2026-10-18): these tables never copy a
-- licensed provider value. They reference provider-derived data only by internal ID
-- (artist_id), and display text is projected at read time under current permissions.
-- supabase/tests/user_isolation_test.sql pins the allowed columns.
--
-- Each user sees and changes only their own rows. auth.uid() is the Supabase Auth
-- subject; anon has no policy and so no access. Service-role workers bypass RLS.

create table public.user_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  locale text not null default 'en-US',
  timezone text not null default 'America/New_York',
  consent_version text,
  deletion_requested_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.artist_follows (
  follow_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.user_profiles(user_id) on delete cascade,
  artist_id uuid not null references public.artists(artist_id) on delete restrict,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, artist_id)
);

create index artist_follows_artist_idx on public.artist_follows (artist_id) where enabled;

create table public.notification_subscriptions (
  subscription_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.user_profiles(user_id) on delete cascade,
  channel text not null check (channel in ('email', 'web_push')),
  -- A secret-manager or encrypted-store reference, never the address or push endpoint.
  endpoint_ref text not null check (btrim(endpoint_ref) <> ''),
  consent_version text not null check (btrim(consent_version) <> ''),
  consent_at timestamptz not null,
  revoked_at timestamptz,
  created_at timestamptz not null default now(),
  -- No send without current consent: a subscription is active exactly while unrevoked.
  check (revoked_at is null or revoked_at >= consent_at),
  unique (user_id, channel, endpoint_ref)
);

alter table public.user_profiles enable row level security;
alter table public.artist_follows enable row level security;
alter table public.notification_subscriptions enable row level security;

create policy user_profiles_own on public.user_profiles
  for all to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

create policy artist_follows_own on public.artist_follows
  for all to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

create policy notification_subscriptions_own on public.notification_subscriptions
  for all to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));
