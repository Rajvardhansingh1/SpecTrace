# Decision Log — SpecTrace

> Append new decisions; do not silently rewrite history. If a decision changes, mark the old one superseded and add a new entry explaining why.

## D-001 — Use a deployable split frontend/backend architecture
- **Status:** Proposed for MVP; verify against actual deployment constraints.
- **Context:** The project needs a public web UI and a Python-centric domain backend.
- **Decision:** Use Next.js/React on Vercel and FastAPI on Render.
- **Why:** Clear frontend/backend boundary; Python ecosystem fits the core domain; independent deploys simplify iteration.
- **How:** Vercel serves UI and calls a server-side FastAPI URL over HTTPS. Render hosts API and background work. Secrets remain backend-only.
- **Alternatives considered:** Single Streamlit app; full-stack Next.js; local-only app.
- **Trade-offs:** Cross-origin configuration, cold starts, and separate deployment configuration must be handled.
- **Validation required:** Verify build, health endpoint, CORS, environment variables, and production request flow.

## D-002 — Persist meaningful state in a database
- **Status:** Proposed.
- **Context:** Experiments and project state must survive restarts.
- **Decision:** Use PostgreSQL for durable records; use local in-memory state only for transient calculations.
- **Why:** Reproducibility, traceability, and restart safety.
- **How:** Define versioned tables/migrations; avoid logging secrets or raw sensitive payloads.
- **Alternatives considered:** In-memory dictionaries, local JSON files, filesystem-only storage.
- **Trade-offs:** Adds schema and migration work; hosted database choice may affect free-tier availability.
- **Validation required:** Restart persistence and migration tests.

## D-003 — Make the core behavior measurable
- **Status:** Proposed.
- **Context:** A portfolio project should demonstrate technical contribution rather than only a polished UI.
- **Decision:** Establish a small benchmark and record baseline metrics before claiming improvement.
- **Why:** Makes the result reproducible and CV claims defensible.
- **How:** Version dataset/configuration; include metric definitions and baseline in the repository.
- **Alternatives considered:** Qualitative demo only.
- **Trade-offs:** Benchmark labeling costs time but improves credibility.
- **Validation required:** Re-run benchmark from a documented command.

## D-004 — Treat external inputs and model outputs as untrusted
- **Status:** Proposed.
- **Context:** The system processes user data and/or generated outputs.
- **Decision:** Validate schemas, apply limits, avoid secret exposure, and use deterministic checks for safety-critical decisions.
- **Why:** LLM output alone is not a security or correctness guarantee.
- **How:** Typed models, server-side configuration, bounded requests, safe error handling, and explicit policy checks where applicable.
- **Alternatives considered:** Trusting model output directly.
- **Trade-offs:** Additional validation and failure handling.
- **Validation required:** Negative tests, input-boundary tests, and secret scan.

## D-005 — Keep Testing.md user-owned
- **Status:** Fixed project instruction.
- **Context:** The user explicitly requires `Testing.md` not to be modified by the model without explicit permission.
- **Decision:** The agent may read the file but must not write to it unless the user specifically authorizes a change to that file.
- **Why:** Preserve user control over the testing contract.
- **How:** Record test outcomes in `State.md`, test implementation changes in code, and add testing-strategy decisions to this log without editing `Testing.md`.
- **Alternatives considered:** Automatically maintaining the test plan.
- **Trade-offs:** Test strategy changes require explicit user authorization to update `Testing.md`.

## D-006 — Deterministic-first engine; LLM off in the MVP
- **Date:** 2026-10-16
- **Status:** Accepted for Plan 1 (user approved proceeding with the spec; P1 not separately contested)
- **Context / problem:** Impact analysis must be reproducible and benchmarkable; the brief says deterministic parsers first.
- **Decision:** No LLM calls. Change classification uses fixed rules; semantically ambiguous cases (requirement edits) are classified `unknown`, never `breaking`.
- **Why this option:** Reproducible results, zero model cost, no leakage of document content to a provider.
- **How it is implemented:** `backend/app/core/diff.py` rules; `Classification.UNKNOWN` for requirements and removed parameters.
- **Alternatives considered:** LLM classification of every change; hybrid from day one.
- **Consequences / trade-offs:** Semantic changes in prose are not judged; recall on subtle changes will be limited.
- **Validation / evidence:** `tests/test_diff.py` (9 tests). Part of the diff rules are untested (see `State.md`).

## D-007 — Confirmed vs inferred labeling rule
- **Date:** 2026-10-16
- **Status:** Accepted
- **Context / problem:** The brief forbids presenting speculative impact as a confirmed breaking change.
- **Decision:** An edge is `confirmed` only for OpenAPI `$ref`, a Markdown `METHOD /path` mention that matches an endpoint (path parameter names and trailing slash ignored), an anchor link to an existing section, or an existing requirement ID. Backticked schema name = `inferred` 0.8. JSON example keys vs schema properties = `inferred` 0.6, requiring at least 2 shared keys and Jaccard ≥ 0.75. An impact is `confirmed` only if every edge on its path is; `confirmed_breaking` additionally requires a `breaking` classification from a deterministic rule.
- **Why this option:** Syntactic evidence is checkable; heuristics carry their confidence and reason.
- **How it is implemented:** `graph.py` (`_resolve`, constants), `impact.py` (`_impact`).
- **Alternatives considered:** Single score; treating backticked names as confirmed.
- **Consequences / trade-offs:** 0.8, 0.6 and 0.75 are unmeasured starting values. The 0.75 threshold was chosen so the `NewPet` schema (Jaccard 0.67) is not matched by a `Pet` example. Plan 3 must tune them on a held-out split, not on the sample.
- **Validation / evidence:** `tests/test_graph.py`, `tests/test_impact.py`, `tests/test_regression_scenarios.py` (hand-labeled impact sets: 5 confirmed, 2 inferred for the petstore `Pet.id` change).

## D-008 — ruamel.yaml round-trip loader with explicit bounds
- **Date:** 2026-10-16
- **Status:** Accepted
- **Context / problem:** Citations need line numbers; `yaml.safe_load` drops them. Uploaded YAML is untrusted.
- **Decision:** Parse with `ruamel.yaml` `YAML(typ="rt")` (no arbitrary object construction), then walk the result iteratively without a visited set, capping nodes (200,000) and depth (50); map `RecursionError` to `limit_exceeded`.
- **Why this option:** Line info plus alias-bomb protection. Aliases load as shared objects in milliseconds, so the node-count walk is what stops expansion.
- **How it is implemented:** `parsers/openapi.py` `_load`, `_check_bounds`.
- **Alternatives considered:** PyYAML safe_load plus text search for line numbers (inaccurate).
- **Consequences / trade-offs:** YAML merge keys (`<<`) are not exercised by tests. JSON documents parse through the same loader; line numbers for single-line JSON are all 1.
- **Validation / evidence:** `tests/test_openapi_parser.py`: alias bomb, depth 100 and 5000 rejected.

## D-009 — Python 3.13 in the `SpecTrace` conda env
- **Date:** 2026-10-16
- **Status:** Accepted
- **Context / problem:** The env had no interpreter; `conda run` silently used `C:\Python314`.
- **Decision:** Install Python 3.13.16 into the env; run everything as `conda run -n SpecTrace python -m ...`; pin direct dependencies in `backend/requirements*.txt`.
- **Why this option:** All compiled dependencies ship `cp313` wheels; Render supports 3.13.
- **Alternatives considered:** Keep 3.14 (wheel availability unverified).
- **Validation / evidence:** `pip check` clean; 65 tests pass under 3.13.16.

## D-010 — Database topology (proposed, not yet implemented)
- **Date:** 2026-10-16
- **Status:** Proposed (Plan 2)
- **Decision:** Docker Postgres for local/integration tests; Supabase (session pooler URL) for production, created via the Supabase MCP; SQLAlchemy + Alembic; RLS enabled with no public policies.
- **Validation required:** Restart-persistence and migration tests; RLS denial test for the anon role.

## D-011 — Runs stored as one row with JSON; Supabase CLI owns the schema
- **Date:** 2026-10-16
- **Status:** Accepted (supersedes the table list in the design spec section 6 and the Alembic part of D-010)
- **Context / problem:** The spec called for artifacts/edges/changes tables and Alembic. The first slice only needs to create, read and list runs, and re-run questions.
- **Decision:** One `runs` table: status, labels, timestamps, error code, input files (`jsonb`), result (`jsonb`). Schema lives in `supabase/migrations/` and is applied with the Supabase CLI or MCP. RLS on, no policies, `anon`/`authenticated` revoked; the backend connects through the pooler. `ask` re-runs the deterministic analysis on stored inputs.
- **Why this option:** Smallest durable design that works; the CLI gives migration history, a local Postgres and pgTAP tests.
- **How it is implemented:** `app/adapters/store.py`, `supabase/migrations/20261015221156_create_runs.sql`, `supabase/tests/runs.test.sql`.
- **Alternatives considered:** Normalized tables now (premature); Alembic (a second migration system next to the Supabase one).
- **Consequences / trade-offs:** Large inputs are stored in the row (limit 5 MB per side); no SQL queries across entities; SQLAlchemy's `create_all` also runs at startup and is a no-op when the table exists. Tests default to in-memory SQLite, with Postgres tests opt-in through `SPECTRACE_TEST_DATABASE_URL`.
- **Validation / evidence:** 88 tests pass against local Postgres; pgTAP 8/8; see `State.md`.

## D-012 — In-process rate limiting and content-free logging
- **Date:** 2026-10-16
- **Status:** Accepted
- **Context / problem:** `Testing.md` security tests require rate limits and no secret leakage in logs. Uploaded documents can contain anything, and database errors can echo statement parameters.
- **Decision:** A sliding-window limiter in process memory (no new dependency), with a tight bucket for POST. Logging records identifiers and codes only: request id, method, route template, status, duration, error code or exception class. A redacting filter is a second line of defence.
- **Why this option:** Meets the free-tier single-instance deployment with no extra service; making the log content-free is stronger than trying to scrub content.
- **How it is implemented:** `app/api/ratelimit.py`, `app/logging_config.py`, middleware in `app/main.py`; settings `SPECTRACE_RATE_LIMIT_*` and `SPECTRACE_TRUST_PROXY_HEADERS`.
- **Alternatives considered:** `slowapi` or Redis (new dependency or service); logging request bodies at debug level (rejected).
- **Consequences / trade-offs:** Limits reset on restart and are per worker, so they do not stop a distributed flood. Behind Render the proxy header must be trusted explicitly, otherwise all clients share one proxy IP.
- **Validation / evidence:** `tests/test_rate_limit.py` (8 tests), `tests/test_logging.py` (7 tests).

## Project-specific decisions to resolve before implementation
- **Problem and scope:** Use the MVP defined in `Prompt.md`; do not add unrelated features.
- **Data and benchmark:** Impact-set precision and recall against a hand-labeled benchmark is a primary measure; define dataset construction and labeling before model optimization.
- **Model/provider:** Select only after checking availability, cost, latency, license, and deployment limits.
- **Persistence:** Keep persistent records separate from ephemeral caches.
- **Deployment:** Do not claim production readiness until live health checks and core user flows are verified.

## Decision entry template
### D-XXX — Short decision title
- **Date:** YYYY-MM-DD
- **Status:** Proposed / Accepted / Superseded
- **Context / problem:**
- **Decision:**
- **Why this option:**
- **How it is implemented:**
- **Alternatives considered:**
- **Consequences / trade-offs:**
- **Validation / evidence:**
