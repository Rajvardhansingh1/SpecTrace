# Build Prompt — SpecTrace

You are the principal engineer building **SpecTrace**, a portfolio-quality AI engineering project. Read `CLAUDE.md` and `AgenticSkillsDiscovery.md` first, then read `State.md`, `Decision.md`, `Explain.md`, `Design_graph.md`, and `Testing.md` before implementation. Follow the instruction that `Testing.md` is immutable unless the user explicitly authorizes edits.

## Product concept
When technical specifications, OpenAPI schemas, and documentation change, engineers need to identify what changed and which downstream components, examples, integrations, and requirements may be affected. Ordinary RAG retrieves relevant text but often cannot trace versioned dependencies.

## Product goal
Deliver a small, polished, reproducible MVP that demonstrates the specific engineering capability below, not a generic chatbot. The system must be deployable with a Next.js frontend on Vercel and a Python FastAPI backend on Render.

## Required MVP behavior
1. Accept Git repository URLs or uploaded Markdown, OpenAPI YAML/JSON, and text-based technical documents from two versions.
2. Normalize sources into versioned artifacts with stable identifiers and source locations.
3. Detect additions, deletions, and semantic changes; preserve exact source diffs.
4. Extract entities such as endpoints, schemas, requirements, examples, and named components.
5. Build a lightweight dependency graph from explicit references and cautiously inferred links.
6. Answer impact questions with evidence paths and clear labels for confirmed versus inferred impacts.
7. Provide an interface to inspect a change, graph path, source snippets, and confidence.

## Recommended architecture
Next.js frontend on Vercel; FastAPI API on Render; PostgreSQL for metadata and graph edges; pgvector optional for semantic retrieval; background ingestion task; GitHub API or uploaded archives as sources. Use deterministic parsers for OpenAPI and Markdown first; use an LLM only for semantic change classification and ambiguous links.

## Core flow
Ingest version A and B -> parse files -> normalize artifacts -> diff artifacts -> extract entities and references -> build/update dependency graph -> retrieve candidate impact paths -> rank and verify evidence -> answer with source-linked impact report.

## Interface requirements
- Landing/overview section that explains the problem and technical contribution.
- Main interactive workflow with useful example/demo data.
- Results view with evidence, trace, diff, or decision details appropriate to the domain.
- Benchmark/metrics view showing real measured outputs and metric definitions.
- Clear loading, empty, error, and unsupported-input states.
- Demo mode that does not require visitors to supply secrets.
- Responsive design and accessible labels.
- Never display fake benchmark values as real results. If using illustrative examples, label them clearly.

## Backend requirements
- FastAPI application with versioned request/response schemas.
- `/health` endpoint and clear error responses.
- Domain logic separated from route handlers.
- Adapter interfaces for external providers and mock implementations for tests.
- Request size, duration, and concurrency limits appropriate to the MVP.
- Server-side environment variables for secrets.
- Persistent storage for records that must survive restarts.
- Structured, privacy-safe logging with request/run identifiers.
- Bounded retries and explicit timeouts for external calls.
- Database migrations or a documented reproducible schema setup.

## Data and evaluation
Build a small, versioned benchmark and explain how it was constructed. Avoid benchmark leakage. Record:
- Impact-set precision and recall against a hand-labeled benchmark
- Citation/source-location accuracy
- Change classification accuracy
- Ingestion time per document
- Unsupported-impact rate

The benchmark must be runnable through a documented command. Store run configuration, dataset version, and actual results. Compare against a sensible baseline; do not claim the proposed method is better unless measured results support that conclusion.

## Testing requirements
Treat `Testing.md` as the user-owned test plan. Read it and implement code/tests that satisfy it, but do not modify the file unless the user explicitly authorizes that exact edit. At minimum, implement unit tests for core deterministic logic, integration tests for the API/persistence boundary, and regression tests for the domain-specific failure cases. Use mocked external services by default.

## Deployment requirements
- Frontend: Next.js/React on Vercel.
- Backend: FastAPI on Render.
- Configure CORS for the deployed frontend origin.
- Keep secrets only in Render environment variables.
- Use a persistent hosted database for durable data.
- Include `.env.example` with placeholder values only.
- Add a README with local setup, environment variables, test commands, benchmark commands, architecture, deployment steps, known limitations, and screenshots/demo instructions.
- Verify deployed health endpoint and one real end-to-end flow before marking deployment complete.
- Do not assume a free plan supports GPUs, durable disk, long-running jobs, or guaranteed low latency. Choose a deployment strategy that fits the actual service constraints.

## Security and safety
SpecTrace ingests untrusted documents and repository URLs, so the backend treats every input as hostile. These rules are requirements, and each one needs a test.

**Threat model**
- Assets: Supabase credentials, any optional LLM API key, uploaded documents, stored graphs and impact reports.
- Actors: anonymous public-demo visitors, and authors of uploaded or fetched content. Neither is trusted.
- Out of scope for the MVP: user accounts and multi-tenant isolation. The public demo is read-mostly and uses synthetic data.

**Input handling**
- Enforce size limits: per-file bytes, files per version, total upload bytes, and entity/edge counts per run. Reject over-limit input with a stable error code before parsing.
- Accept only Markdown (`.md`), OpenAPI (`.yaml`, `.yml`, `.json`) and plain text (`.txt`). Reject everything else as unsupported. Decide by content and extension, not by the client's MIME type.
- Parse YAML with a safe loader only. Never use `yaml.load` with an unsafe loader, `eval`, `pickle`, or any dynamic code execution on uploaded content. Cap YAML nesting depth and alias expansion to block billion-laughs input.
- Archives (zip/tar): reject path traversal (`..`, absolute paths, symlinks), cap decompressed size and file count, and never extract to a path derived from archive names.
- Treat document text as data. Text found inside documents must never be executed or followed as an instruction, including when it is sent to an LLM.

**Repository fetching (SSRF and privacy)**
- Public GitHub repositories only, by default. Allow `https://github.com/<owner>/<repo>` and nothing else; resolve through the GitHub API, never by shelling out to `git clone` with user-controlled arguments.
- Block requests to private, loopback and link-local addresses, and do not follow redirects off the allowed host.
- Never attempt a private repository without explicit, user-supplied authorization for that run. Never store such tokens, never log them, and discard them when the run ends.
- Cap repository size, file count and API calls per run. Honor GitHub rate limits with bounded retries.

**Secrets**
- Secrets exist only in backend environment variables (Render) and a local `.env` that is git-ignored. `.env.example` holds placeholders only.
- The browser receives no Supabase service-role key, no database URL, and no LLM key. Only the backend API URL is public.
- Never log secrets, tokens, full document bodies or raw request bodies. Logs carry run IDs, step names, durations, counts and error codes.
- Run a secret scan before every release.

**Database (Supabase)**
- The backend connects server-side with a least-privilege database role. The service-role key is never used from the frontend.
- Enable row-level security on every table, with no public policies, so the Supabase REST endpoint exposes nothing even if the anon key leaks.
- Use parameterized queries through the ORM only. No string-built SQL.
- Apply schema changes only through versioned migrations.

**API hardening**
- Validate every request and response with typed schemas. Return stable error codes and safe messages with no stack traces or file paths.
- Set CORS to the deployed frontend origin and local dev origins only, never `*`.
- Rate-limit per client, cap concurrent runs, and set a wall-clock timeout on every run and every outbound call.
- Escape all rendered output in the frontend. Render document snippets as text, never as raw HTML. If Markdown is rendered, sanitize it.

**LLM use (optional, off by default)**
- Output is untrusted. Parse it against a strict schema and discard anything that does not validate.
- The LLM can propose a change classification or an ambiguous link. It cannot create a confirmed impact. Confirmed impacts require deterministic evidence: an explicit reference found in the source.
- Send only the minimum snippets needed. Never send secrets or private-repository content to a provider without explicit authorization.
- Set a timeout, a bounded retry count, a per-run request cap and a token cap. If the call fails, fall back to the deterministic result and say so.

**Honest-reporting safety**
- Every impact carries a label: `confirmed` (explicit reference with a source location) or `inferred` (heuristic or model-suggested, with its evidence and a confidence).
- Speculative impact is never presented as a confirmed breaking change.
- When evidence is insufficient, the system abstains and says so.

**Verification**
- Tests cover: oversized input, wrong file type, malicious YAML, archive traversal, SSRF targets, private-repo refusal, secret absence in logs, RLS denial for the anon role, and the confirmed-versus-inferred labeling rule.
- Dependencies are pinned and audited (`pip-audit`, `npm audit`) before release.

## Implementation sequence
1. Inspect the repository and report its actual starting state.
2. Follow the skill discovery process and update the skill graph in `State.md` with verified skills.
3. Confirm requirements and resolve only essential ambiguities; record important decisions in `Decision.md`.
4. Create a minimal end-to-end vertical slice with mock/sample data.
5. Add persistence and error handling.
6. Implement domain-specific logic and evaluation.
7. Add unit/integration/regression tests without editing `Testing.md`.
8. Run tests and record actual results in `State.md`.
9. Update `Explain.md` and `Design_graph.md` to match the code.
10. Prepare Vercel and Render deployment configuration.
11. Verify deployment if credentials/permissions are available; otherwise state what remains unverified.
12. Review security, dependencies, and docs; report skills applied and unresolved issues.

## Definition of done
- [ ] A new developer can run the project from the README.
- [ ] Main workflow works with demo data.
- [ ] Core logic has automated tests.
- [ ] Domain benchmark and baseline are reproducible.
- [ ] Errors and unsupported cases are handled explicitly.
- [ ] Secrets are not committed or exposed in the browser.
- [ ] Vercel frontend and Render backend deployment steps are documented.
- [ ] `State.md`, `Decision.md`, `Explain.md`, and `Design_graph.md` accurately reflect actual implementation.
- [ ] `Testing.md` remains untouched unless the user explicitly authorizes an edit.
- [ ] No unverified claim is presented as completed.
