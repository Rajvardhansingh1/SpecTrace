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
