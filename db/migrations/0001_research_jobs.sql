-- Proposed (NOT applied). Durable queue + idempotency for Linear research triggers.
-- Requires a Notion decision ID before applying; see docs/linear-research-agent.md.
create table if not exists research_jobs (
  id uuid primary key default gen_random_uuid(),
  linear_issue_id text not null,
  linear_webhook_id text,
  preset text not null check (preset in ('low', 'medium')),
  source text not null check (source in ('webhook', 'sweep', 'manual')),
  status text not null default 'queued' check (status in ('queued','running','posted','failed','skipped')),
  attempts int not null default 0,
  linear_comment_id text,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
-- One active job per issue; prevents webhook + sweep double-posting.
create unique index if not exists research_jobs_one_active
  on research_jobs (linear_issue_id) where status in ('queued', 'running');
alter table research_jobs enable row level security;  -- service role only; no public policies
