alter table public.discovery_state
  add column unresolved_observations jsonb not null default '{}'::jsonb
  check (jsonb_typeof(unresolved_observations) = 'object');
