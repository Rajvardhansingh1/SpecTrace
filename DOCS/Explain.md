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

Planned, not implemented: `frontend/`, `backend/app/adapters/` (sources, LLM, store), `backend/app/api/v1/`, database models and Alembic migrations, `scripts/` (benchmark), `benchmark/`.

Known limitations of the engine: only `#/components/schemas/*` refs are resolved (no external or parameter refs); renamed entities appear as remove + add; `allOf`/`oneOf` composition is not interpreted; bare-word mentions are not detected; the confidence values are unmeasured defaults.
