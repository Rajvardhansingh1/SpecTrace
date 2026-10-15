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

## Implementation map
Update this section with actual paths once files are created:
- `frontend/` — planned UI.
- `backend/app/main.py` — planned API entry point.
- `backend/app/core/` — planned domain logic.
- `backend/app/adapters/` — planned external integrations.
- `backend/app/models/` — planned request/response schemas.
- `backend/tests/` — planned automated tests.
- `scripts/` — planned benchmark/demo scripts.
