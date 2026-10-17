# Explain — SpecTrace

## What the project does
When technical specifications, OpenAPI schemas, and documentation change, engineers need to identify what changed and which downstream components, examples, integrations, and requirements may be affected. Ordinary RAG retrieves relevant text but often cannot trace versioned dependencies.

## The core idea
Version-aware technical documentation retrieval and change-impact analysis. The MVP should be a small, working vertical slice with measurable behavior, not a large collection of loosely connected AI features.

## High-level architecture
Next.js frontend on Vercel; FastAPI API on Render; PostgreSQL for metadata and graph edges; pgvector optional for semantic retrieval; background ingestion task; GitHub API or uploaded archives as sources. Use deterministic parsers for OpenAPI and Markdown first; use an LLM only for semantic change classification and ambiguous links.

## Main components and responsibilities
1. **Frontend:** Collects input, shows progress/results, and renders evidence or traces. It must not contain provider secrets or authoritative policy logic.
2. **API layer:** Validates requests, handles authentication/rate limits where needed, calls domain services, and returns typed responses.
3. **Domain service:** Implements the project-specific workflow. Keep core logic independent of the UI.
4. **Adapters:** Encapsulate model providers, source systems, database access, and external APIs behind replaceable interfaces.
5. **Persistence:** Stores records needed for restart safety, reproducibility, audit, or comparison.
6. **Validation layer:** Independently validates generated results and rejects or safely handles invalid output.
7. **Observability:** Records request IDs, step outcomes, timing, and safe error details. Never log secrets.

## End-to-end flow
Ingest version A and B -> parse files -> normalize artifacts -> diff artifacts -> extract entities and references -> build/update dependency graph -> retrieve candidate impact paths -> rank and verify evidence -> answer with source-linked impact report.

## What makes the project technically meaningful
- Impact-set precision and recall against a hand-labeled benchmark
- Citation/source-location accuracy
- Change classification accuracy
- Ingestion time per document
- Unsupported-impact rate

## Error handling
- Validate external input before expensive processing.
- Use explicit timeouts and bounded retries; do not retry non-idempotent actions blindly.
- Return stable error codes and a safe message to the UI.
- Record diagnostic details server-side without secrets.
- Prefer abstention or explicit failure over fabricating a result.
- Persist checkpoints/results where workflow correctness requires them.

## Deployment model
- **Vercel:** Next.js/React UI.
- **Render:** FastAPI service and bounded background processing.
- **Database:** Hosted PostgreSQL or another explicitly selected persistent database.
- **Secrets:** Environment variables configured in backend hosting; never committed.
- **Health:** Provide `/health` and document readiness/dependency behavior.
- **Limits:** Keep synchronous request durations bounded; use polling for long jobs.

## What not to do
- Do not make the LLM the sole authority for security, correctness, or irreversible actions.
- Do not claim benchmark improvements without a reproducible baseline.
- Do not build abstractions before a working end-to-end slice exists.
- Do not add dependencies without checking whether existing libraries are sufficient.
- Do not treat this starter explanation as proof of implementation; update it when code exists.

## Implementation map (as of 2026-10-16)
Implemented:
- `backend/app/main.py` — `create_app()`: CORS allow-list, `SpecTraceError` → `{"error": {"code", "message"}}` envelope, `GET /health`. No analysis routes yet.
- `backend/app/config.py`, `backend/app/errors.py` — env settings (`SPECTRACE_` prefix); error classes with stable codes (`input_too_large` 413, `unsupported_input` 415, `parse_error` 422, `limit_exceeded` 422).
- `backend/app/core/models.py` — frozen pydantic types: `Location`, `Entity`, `Edge`, `RawRef`, `ParseResult`, `Change`, `Impact`.
- `backend/app/core/limits.py` — `Limits` (files, bytes, entities, YAML nodes/depth).
- `backend/app/core/parsers/openapi.py` — OpenAPI YAML/JSON → endpoint and schema entities, `$ref` edges, exact line spans; semantic content hash.
- `backend/app/core/parsers/markdown.py` — Markdown → sections, requirements (`REQ-###` or RFC 2119 keyword), fenced examples, raw references.
- `backend/app/core/graph.py` — resolves raw references into edges, labels each `confirmed` or `inferred` (rule in D-007), dedupes, records warnings for unresolved references.
- `backend/app/core/diff.py` — per-entity diff, deterministic breaking-change rules, unified source diff.
- `backend/app/core/impact.py` — bounded reverse-edge path search; best path per impacted entity.
- `backend/app/core/pipeline.py` — `analyze()` (input checks, parse, graph, diff, impacts) and `answer_question()`.
- `backend/tests/` — 65 tests; `samples/petstore/{v1,v2}` — sample data with one breaking change (`Pet.id` string → integer) and stale docs.

Core data flow: files → parser → `ParseResult` → `build_graph` → `Graph` (A and B) → `diff_graphs` → `Change[]` → `find_impacts` over the union of A and B edges → `AnalysisResult`.

Persistence and API (implemented 2026-10-16): `app/adapters/store.py` holds `RunStore` over SQLAlchemy; the `runs` table keeps input files and the serialized result as JSON (`jsonb` on Postgres). `app/api/v1/runs.py` exposes `POST /v1/runs` (analyze inline, store, return summary), `GET /v1/runs`, `GET /v1/runs/{id}` and `POST /v1/runs/{id}/ask` (re-runs the deterministic analysis on stored inputs, then `answer_question`). `main.py` adds a request-size check (413 before parsing) and replaces pydantic validation detail with a fixed `invalid_request` message so submitted input is never echoed. A failed analysis marks the run `failed` with its error code. With no `SPECTRACE_DATABASE_URL` the store is in-memory SQLite and nothing survives a restart.

Planned, not implemented: `frontend/`, source adapters (GitHub), LLM adapter, rate limiting, `scripts/` (benchmark), `benchmark/`.

Known limitations of the engine: only `#/components/schemas/*` refs are resolved (no external or parameter refs); renamed entities appear as remove + add; `allOf`/`oneOf` composition is not interpreted; bare-word mentions are not detected; the confidence values are unmeasured defaults.

Request pipeline (implemented 2026-10-16), outermost first: CORS, request logging (assigns the request id, catches unhandled errors and returns a generic 500), rate limiting, body-size check, routes. CORS is outermost so 413 and 429 responses still carry CORS headers. Logs hold identifiers only; see D-012.

Benchmark (implemented 2026-10-16): `backend/scripts/benchmark.py` loads each case from `benchmark/v1/cases/<id>/{a,b}`, runs `analyze`, and scores the reported (change, impacted) pairs against `expected.json`. It also scores a keyword baseline and checks every impact's evidence path (chained, inside the files, no inferred edge under a `confirmed` label). Citation of an impact is the evidence of the last edge on its path, the line where the impacted entity makes its reference.

Frontend (implemented 2026-10-16): `frontend/lib/api.ts` is the only place that talks to the API; it maps every failure to a stable code (`network`, `timeout`, `bad_response`, or the backend's code) and reads `Retry-After`. `lib/evidence.ts` decides which version's files an evidence line belongs to: the engine merges both versions' edges and lets B win, so an edge present in B cites B and any other edge cites A. `RunView` loads a run, `ChangeList` filters and selects, `ChangeDetail` shows reasons, dependents and the diff, `ImpactItem` shows the path from the impacted entity to the change and fetches the cited lines from `/v1/runs/{id}/snippet`, and `AskPanel` posts a question. Every data view has loading, empty and error states with a cause and a next step. The page never holds a secret: the only configuration is the public API URL.

Input and theme (2026-10-16): `components/VersionPane.tsx` accepts files by picker, folder picker or drop. `lib/files.ts` `collectDropped` takes the file-system entries synchronously inside the drop event (the browser empties them after the first `await`), then walks directories in batches, skipping `node_modules` and `.git` and stopping at 1,000 files. `ThemeToggle` writes `data-theme` on `<html>` and stores the choice; an inline script in `app/layout.tsx` applies a stored choice before first paint. `RunStore` serializes access when the database is in-memory SQLite (see D-015).

RAG layer (2026-10-17): `AIService` (`app/service.py`) is the only place that combines the pieces. For a question it re-runs the deterministic analysis, builds or loads the run's chunks (`chunk_entities` over both versions), embeds them once through the configured embedder and stores them in `chunks` (pgvector on Postgres, a JSON list on SQLite), embeds the question, takes DB-side cosine similarities (Python on SQLite), fuses them with BM25 (`retrieve`), assembles a numbered context with graph facts first (`build_context`), and calls the chat model. `rag.py` then verifies the reply: one JSON object, citations that exist, no entity key that is not in the context, no uncited answer. Summaries use the same checks over an outline of each version and over the change list. Narratives are saved in `runs.result.narrative`. `CallBudget` bounds calls per owner per hour and per process per day.
