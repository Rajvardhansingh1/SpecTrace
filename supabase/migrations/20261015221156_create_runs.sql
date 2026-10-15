create table public.runs (
  id uuid primary key default gen_random_uuid(),
  status text not null check (status in ('running', 'done', 'failed')),
  label_a text not null check (char_length(label_a) <= 100),
  label_b text not null check (char_length(label_b) <= 100),
  created_at timestamptz not null default now(),
  finished_at timestamptz,
  error_code text,
  files_a jsonb not null,
  files_b jsonb not null,
  result jsonb
);

create index runs_created_at_idx on public.runs (created_at desc);

-- RLS on with no policies: anon and authenticated roles (the public REST API) get no access.
-- The backend connects through the pooler with a role that bypasses RLS.
alter table public.runs enable row level security;
revoke all on public.runs from anon, authenticated;
