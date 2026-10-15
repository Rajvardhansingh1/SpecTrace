# SpecTrace Design Spec

**Date:** 2026-10-16
**Status:** Draft, awaiting user approval
**Inputs:** `DOCS/ProjectBreif.md`, `DOCS/CLAUDE.md`, `DOCS/Testing.md` (read-only), user answers in chat.

## 1. Path classification

Architectural: this is a new project with no existing flow to extend. The full brainstorming path applies (design, written spec, user review, then writing-plans).

## 2. Decisions already made by the user

| Topic | Decision |
|---|---|
| Database | Supabase (hosted Postgres). Supabase MCP is connected; the project is created when Plan 2 needs it. |
| Hosting | Render MCP is connected; used for backend deployment in Plan 5, with user authorization before creating paid resources. |
| Python runtime | Conda env `SpecTrace` with Python 3.13.16 (installed 2026-10-16; the env previously had no interpreter). |
| Security brief | Written into `DOCS/Prompt.md` and `DOCS/ProjectBreif.md` ("Security and safety"). |
| Workflow | Superpowers skills: brainstorming, writing-plans, test-driven-development, subagent-driven-development, verification-before-completion. |

## 3. Decisions proposed by this spec (need your approval)

| ID | Proposal | Why | Alternative |
|---|---|---|---|
| P1 | The MVP engine is deterministic. No LLM call in the first release; an `LLMClassifier` adapter interface and a mock exist but the default is "off". | Matches the brief ("deterministic parsers first") and keeps benchmark results reproducible and free. | Add a real provider later, after the baseline is measured. |
| P2 | Local development and integration tests use a disposable Docker Postgres. Production uses Supabase through its **session pooler** connection string. | Docker 29 is installed. Render has no IPv6 route to Supabase's direct host, so the pooler is required. | SQLite for tests (rejected: hides Postgres differences). |
| P3 | SQLAlchemy 2 + Alembic for storage (both already in the env). Tables hold JSON columns for entities and edges, with RLS enabled and no public policies. | Portable, migration-driven, no new ORM. | Supabase client library (rejected: bypasses migrations and exposes REST surface). |
| P4 | Ingestion runs inline for small inputs and as a FastAPI background task with polling for larger ones. Run state is persisted. | Render free tier has no worker; this is the simplest correct option. | Separate worker (rejected for MVP). |
| P5 | Frontend: Next.js (App Router, TypeScript). Graph shown as an evidence-path list plus a small SVG diagram, no heavy graph library. | Keeps the bundle small and the evidence readable. | Cytoscape/D3 (rejected for MVP). |
| P6 | The baseline for the benchmark is keyword retrieval: find every document section that mentions the changed entity's name (grep-style). | A sensible, honest comparison for "ordinary RAG cannot trace dependencies". | Embedding retrieval, added later if time allows. |

## 4. Architecture

```
Next.js (Vercel) --HTTPS--> FastAPI (Render) --> Domain core --> Supabase Postgres
                                   |                |
                                   |                +--> Source adapters (upload, GitHub public API)
                                   +--> /health, /v1/*  +--> LLM adapter (off by default, mock for tests)
```

Backend layout (`backend/app/`):

| Path | Responsibility |
|---|---|
| `main.py` | App factory, CORS, error handlers, router wiring. |
| `config.py` | Environment settings (pydantic-settings). |
| `errors.py` | `SpecTraceError` and stable error codes. |
| `core/models.py` | Typed domain objects: `Entity`, `Edge`, `Change`, `Impact`, `ParseResult`. |
| `core/limits.py` | Size and count limits. |
| `core/parsers/openapi.py` | OpenAPI YAML/JSON to entities and `$ref` edges, with source lines. |
| `core/parsers/markdown.py` | Markdown to sections, requirements, examples, and raw references. |
| `core/graph.py` | Resolve raw references into labeled edges; dependents index. |
| `core/diff.py` | Entity-level diff, deterministic breaking-change rules, exact source diffs. |
| `core/impact.py` | Evidence-path search and ranking; confirmed vs inferred labeling. |
| `core/pipeline.py` | `analyze(files_a, files_b)` and question answering. |
| `adapters/` | Sources (upload, GitHub), LLM (off/mock), store (SQLAlchemy). |
| `api/v1/` | Routes and request/response schemas. |

The domain core imports nothing from `api/` or `adapters/`.

## 5. Domain contract

**Entity** (`frozen`): `key` (stable across versions, e.g. `endpoint:GET /pets/{petId}`, `schema:Pet`, `section:guide.md#fetching-a-pet`, `requirement:REQ-001`, `example:guide.md#fetching-a-pet:1`), `kind`, `name`, `location` (file, 1-based line range), `content_hash` (semantic for OpenAPI, whitespace-normalized for Markdown), `text` (exact source slice, used for diffs), `attrs`.

**Edge**: `source_key` depends on `target_key`. `relation`, `label` (`confirmed` or `inferred`), `confidence` (0 to 1), `evidence` (location of the reference), `reason`.

Labeling rule, enforced in `graph.py` and tested:
- `confirmed`: syntactic, explicit reference. OpenAPI `$ref`; Markdown mention of `METHOD /path` that matches an endpoint; Markdown anchor link to an existing section; mention of an existing requirement ID.
- `inferred`: heuristic. Backticked identifier equal to a schema name (0.8); example JSON keys overlapping a schema's properties (0.6; at least 2 shared keys and Jaccard similarity of at least 0.75). A bare-word mention heuristic (0.5) is deferred until the benchmark can measure its false-positive rate.

**Change**: `key`, `kind`, `change_type` (`added`, `removed`, `modified`), `classification` (`breaking`, `non_breaking`, `documentation`, `unknown`), `reasons`, `source_diff` (unified diff of exact source slices), `before`/`after` locations.

**Impact**: `change_key`, `impacted_key`, `certainty` (`confirmed` or `inferred`), `confidence` (product of edge confidences), `path` (ordered edges with evidence), `confirmed_breaking` (true only when the change is classified `breaking` by a deterministic rule **and** every edge on the path is `confirmed`).

Path selection: simple paths up to depth 3 over the union of edges from both versions; one best path per impacted entity, ranked confirmed first, then confidence, then length. A path-expansion cap bounds the search.

**Abstention:** a question that matches no known entity returns `uncertain` with a reason; it never fabricates an impact.

## 6. Persistence (Supabase)

Tables: `runs` (id, status, created_at, finished_at, error_code, limits_json, version labels), `artifacts` (run_id, version, key, kind, hash, location, text), `edges` (run_id, version, source, target, relation, label, confidence, evidence, reason), `changes`, `impacts`, `benchmark_runs`. All managed by Alembic. RLS enabled on every table with no public policies. The backend uses a dedicated least-privilege role through the pooler.

## 7. Error handling

Stable codes: `input_too_large`, `unsupported_input`, `parse_error`, `limit_exceeded`, `source_not_allowed`, `private_repo_not_authorized`, `run_timeout`, `internal_error`. Responses carry the code and a safe message only. Details go to server logs with the run ID.

## 8. Testing

Follows `Testing.md` (read-only). Unit tests for parsers, diff, graph, impact. Integration tests against disposable Docker Postgres. Security tests from the brief's verification list. Regression tests for the five project scenarios in `Testing.md` section 3, using the petstore sample in `samples/petstore/`. Frontend smoke test with Playwright. Actual results recorded in `State.md` only.

## 9. Benchmark

`benchmark/v1/`: hand-labeled cases (version pairs plus expected impact sets), a README on how labels were produced, and a runner `python -m scripts.benchmark`. Metrics: impact-set precision and recall, citation line accuracy, change classification accuracy, ingestion ms per document, unsupported-impact rate (confirmed impacts without a valid evidence path; must be 0). Baseline per P6. Results are stored with dataset version, config and date. Cases are written before tuning the engine, and tuning is evaluated on a held-out split.

## 10. Roadmap and plans

This spec covers several independent subsystems, so it is split into plans. Each plan produces working, testable software.

| Plan | Scope | Status |
|---|---|---|
| 1 | Backend core engine: scaffold, parsers, graph, diff, impact, pipeline, petstore sample, regression tests | Written: `DOCS/superpowers/plans/2026-10-16-backend-core-engine.md` |
| 2 | Persistence and API: SQLAlchemy models, Alembic, run lifecycle, `/v1` routes, limits, security tests | After plan 1 |
| 3 | Benchmark: dataset v1, runner, baseline, stored results | After plan 2 |
| 4 | Frontend: overview, analyze flow, results, benchmark view | After plan 2 |
| 5 | GitHub source, deployment config, README | After plans 3 and 4 |

## 11. What I need from you

1. Approve or change P1 to P6.
2. Supabase project: created through the Supabase MCP when Plan 2 starts (user decision, 2026-10-16).
3. Dependencies: installed into the env on 2026-10-16 (see plan Task 0).
4. Authorize `git init` in `SpecTrace/` so the plan's commits work (it is not a repository yet).
