-- Retrieval for the language-model features: document chunks with their embeddings, and owner
-- scoping so one visitor cannot read another's comparisons.

create extension if not exists vector with schema extensions;

alter table public.runs add column if not exists owner_hash text;
create index if not exists runs_owner_idx on public.runs (owner_hash, created_at desc);

create table public.chunks (
  id bigint generated always as identity primary key,
  run_id uuid not null references public.runs (id) on delete cascade,
  version text not null check (version in ('a', 'b')),
  key text not null,
  kind text not null,
  name text not null,
  file text not null,
  line_start integer not null check (line_start >= 1),
  line_end integer not null check (line_end >= line_start),
  ordinal integer not null check (ordinal >= 0),
  text text not null,
  text_hash text not null,
  -- Unconstrained dimension: the size depends on the embedding model, and a run's chunks all use
  -- one model (recorded in embedding_model). A run holds a few hundred chunks, so similarity is an
  -- exact scan; add an HNSW index per model when a library of many documents needs one.
  embedding extensions.vector,
  embedding_model text
);

create index chunks_run_idx on public.chunks (run_id, version);

-- Row level security on with no policies, and the public roles revoked: only the API's own
-- database connection can read or write these tables.
alter table public.chunks enable row level security;
revoke all on public.chunks from anon, authenticated;
