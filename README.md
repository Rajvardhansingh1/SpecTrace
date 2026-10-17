# SpecTrace

Version-aware change-impact analysis for API specifications and their documentation.

Give SpecTrace two versions of an OpenAPI file and the Markdown docs that describe it. It lists what changed, classifies each change with fixed rules, and then shows which docs, requirements, examples, endpoints and schemas depend on the change. Every dependent comes with the path that links it to the change and the source line that proves it. A link that is only a guess is labeled as a guess and is never presented as a confirmed breaking change.

With a language model configured (optional), it also writes a short summary of each version and of what changed, and answers questions in plain words. Retrieval finds the relevant passages by keywords and by meaning, the model writes only from those passages and the dependency graph, and the server checks every answer against its sources before it is shown. Without a model, everything above still works.

![Results page: a breaking change to a schema, with confirmed and inferred dependents](assets/results.png)

## Why it exists

Retrieval over documents finds text that mentions a changed name. It cannot follow a dependency: a docs section that describes `GET /pets` depends on the `Pet` schema because the endpoint references it, even though the section never says `Pet`. After a schema change, the useful question is "what else must I re-check?", and the answer needs a trail an engineer can follow and verify.

SpecTrace builds a small dependency graph from explicit references, adds cautious guesses that it labels as guesses, and searches that graph backwards from each change.

![A confirmed path and its cited source line, next to inferred links](assets/evidence.png)

## How it works

```mermaid
flowchart LR
    A[OpenAPI and Markdown files, versions A and B] --> P[Parsers]
    P --> E[Entities with line ranges]
    P --> R[Raw references]
    E --> G[Dependency graph]
    R --> G
    G --> D[Diff and classification]
    D --> I[Impact search over reverse edges]
    I --> O[Impacts with evidence paths]
```

1. **Parse.** Endpoints, schemas, Markdown sections, requirements and fenced examples become entities with stable keys (`endpoint:GET /pets`, `schema:Pet`, `section:docs/guide.md#listing-pets`, `requirement:REQ-001`) and exact line ranges. YAML is read with a round-trip loader that keeps line numbers, and is bounded against alias bombs and deep nesting.
2. **Link.** Each reference becomes an edge, labeled **confirmed** or **inferred**.
3. **Diff.** Entities are compared by content hash. Formatting and comments are ignored. Each change is classified by deterministic rules.
4. **Trace.** From every modified or removed entity, the engine searches the reverse edges up to three links deep and keeps the best path to each dependent.

### Confirmed and inferred

| Label | Created by | Confidence |
|---|---|---|
| Confirmed | an OpenAPI `$ref`; a Markdown mention of `METHOD /path` that matches an endpoint; an anchor link to an existing section; an existing requirement ID | 1.0 |
| Inferred | a backticked name that equals a schema name | 0.8 |
| Inferred | a JSON example whose keys overlap a schema's properties (at least 2 shared keys and Jaccard similarity of at least 0.75) | 0.6 |

A dependent is *confirmed* only when every link on its path is confirmed. It is flagged *confirmed breaking* only when, in addition, a fixed rule classifies the change itself as breaking. Changes whose effect cannot be decided by rule (a requirement reworded, a parameter removed) are classified **needs review**, never breaking.

### Change classification

| Change | Classification |
|---|---|
| Endpoint or schema removed | breaking |
| Required parameter added; parameter became required; parameter type changed | breaking |
| Request body became required or changed schema; a 2xx response removed or its schema changed | breaking |
| Schema property removed, retyped, or added as required | breaking |
| Parameter or request body removed; non-2xx response removed; requirement added, removed or edited | needs review |
| Optional parameter, response or property added; property no longer required | non-breaking |
| Prose, summaries, examples | documentation only |

## Language model and retrieval (optional)

The dependency graph stays the source of truth. The language model explains it; it never decides what is confirmed.

```mermaid
flowchart LR
    F[Files of both versions] --> C[Chunks, one per section, requirement, endpoint, schema or example]
    C --> V[(Embeddings in pgvector)]
    Q[Question] --> H[Hybrid retrieval: keywords plus vector similarity]
    V --> H
    G[Changes and impacts from the graph] --> X[Context with numbered items]
    H --> X
    X --> M[Language model]
    M --> K[Server checks the reply]
    K --> A[Answer with sources, or an honest 'not enough']
```

- **Knowledge base.** Each comparison is its own knowledge base: the two versions you added. Their entities become chunks that follow the structure of the documents, with exact file and line ranges. Chunks and their embeddings are stored in the `chunks` table in Supabase (a `vector` column, pgvector) the first time a question is asked, and reused after that. A persistent project library, where documents are added once and compared later, is not built yet.
- **Retrieval.** Keyword ranking (BM25) finds exact names and paths. Vector similarity finds passages that say the same thing in other words. Reciprocal rank fusion merges the two. Facts about any entity named in the question, taken from the graph, are put first.
- **Summaries.** One short summary per version and one of what changed, written from an outline of each version and from the deterministic change list.
- **Checks on every reply.** It must be one JSON object. Every citation must name an item that was in the context. An answer that cites nothing is not shown. An answer that names an endpoint, schema, section, requirement or example that was not in the context is not shown. A question that matches nothing in the documents is not sent to the model at all.
- **Prompt injection.** Document text is untrusted data. It is placed between delimiters that carry a random token, angle brackets in it are neutralized so it cannot close them, and the instructions tell the model to ignore any instructions found inside. The model has no tools and cannot fetch anything.
- **Cost and abuse guards.** Calls to the model and the embedding service are limited per visitor per hour and per server per day, retries are bounded, prompts are size-bounded, and a failing embedding service degrades to keyword retrieval instead of failing the question.
- **Privacy.** Nothing is sent to a provider until the visitor clicks, and the page names who receives the text first. Each visitor sees only their own comparisons (see Security notes).

### Setting it up

Both the chat model and the embeddings speak the OpenAI-compatible protocol, so a provider is a base URL, a key and a model name. Put them in `backend/.env` (see `backend/.env.example`):

| Goal | Settings |
|---|---|
| Chat with OpenRouter | `SPECTRACE_LLM_PROVIDER=openrouter`, `SPECTRACE_LLM_API_KEY`, `SPECTRACE_LLM_MODEL` (an id from the OpenRouter catalog) |
| Chat with Groq | `SPECTRACE_LLM_PROVIDER=groq`, `SPECTRACE_LLM_API_KEY`, `SPECTRACE_LLM_MODEL` (a Groq model id) |
| Embeddings with OpenRouter | `SPECTRACE_EMBEDDING_PROVIDER=openrouter`, `SPECTRACE_EMBEDDING_MODEL`; reuses the chat key when the chat provider is also OpenRouter |
| Embeddings with Jina AI (free-tier key) | `SPECTRACE_EMBEDDING_PROVIDER=jina`, `SPECTRACE_EMBEDDING_API_KEY`, `SPECTRACE_EMBEDDING_MODEL` |
| Embeddings with no key and no network | `SPECTRACE_EMBEDDING_PROVIDER=hashing` (matches shared words, not meaning) or `fastembed` (a real local model; `pip install fastembed`; roughly 1 GB of memory) |
| Any other OpenAI-compatible server | `openai_compatible` with `SPECTRACE_LLM_BASE_URL` or `SPECTRACE_EMBEDDING_BASE_URL` |

Check the setup before using the interface. It sends a fixed one-word prompt and prints names and timings, never keys or replies:

```
cd backend && python -m scripts.check_providers
```

Model ids, prices and free-tier limits change; look them up on the provider's page. Hugging Face's hosted inference has a very small free monthly credit, which is enough to try it but not to index real documents. The vectors in the database depend on the embedding model: changing `SPECTRACE_EMBEDDING_MODEL` makes the next question re-embed the comparison.

## Benchmark

`benchmark/v1` holds 14 synthetic cases with 26 hand-labeled dependents, split into a development set and a held-out set. The comparison is with keyword retrieval: every other entity whose text contains the changed entity's name.

| | Precision | Recall |
|---|---|---|
| SpecTrace | 1.00 | 0.96 |
| Keyword baseline | 0.87 | 0.77 |

The benchmark measures the deterministic engine only. It does not evaluate what a language model writes; the checks above are enforced in code and covered by tests, but answer quality with a real model has not been measured.

Also measured: certainty label correct 1.00, cited line correct 1.00, confirmed claims that the labels contradict 0, impacts without a valid evidence path 0, median analysis time about 2 to 3 ms per document. The single miss is a docs section four links from the change, beyond the three-link search.

**Read these numbers with their limits in mind.** The labels were written by the engine's authors before the first run and have not been independently reviewed. The dataset is small and synthetic, and one error moves the held-out recall by 10 points. The engine was not tuned on this data. The keyword baseline was corrected once after the first run, which is disclosed in [`benchmark/v1/README.md`](benchmark/v1/README.md) together with the metric definitions.

```
cd backend
python -m scripts.benchmark                # all cases
python -m scripts.benchmark --split heldout --details
python -m scripts.benchmark --save         # stores benchmark/v1/results/<date>-<split>.json
```

## Repository layout

```
backend/      FastAPI service and the analysis engine
  app/core/       parsers, graph, diff, impact search, chunking, retrieval and the checks on model output (no web or database imports)
  app/adapters/   run and chunk store (SQLAlchemy; in-memory SQLite or Postgres with pgvector), model and embedding clients
  app/service.py  ties retrieval, the model and the stores together
  app/api/        HTTP routes and the rate limiter
  scripts/        benchmark runner and the provider check
  tests/
frontend/     Next.js interface (see frontend/README.md, DESIGN.md, ACCESSIBILITY.md)
benchmark/    dataset v1 and stored results
samples/      petstore example used by the tests and the interface
supabase/     database migrations and SQL tests
render.yaml   Render blueprint for the API
```

## Quick start

Requirements: Python 3.13 and Node.js 22.12 or newer (24 is used in CI). Docker is only needed for a local Supabase stack.

```
# API
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000

# Interface (second terminal)
cd frontend
cp .env.example .env.local
npm install
npm run dev                                           # http://localhost:3000
```

Without `SPECTRACE_DATABASE_URL` the API keeps runs in memory, so nothing survives a restart. Open the interface, press **Load petstore example**, then **Compare versions**.

### Database (optional, for persistence)

Runs and the chunks with their embeddings are stored in two Postgres tables, defined in [`supabase/migrations`](supabase/migrations) (the second migration enables the `vector` extension). Row level security is enabled with no policies and the public roles are revoked, so the tables are reachable only through the API's own connection.

```
supabase start && supabase test db          # local Postgres and the SQL tests (needs Docker)
supabase link --project-ref <ref> && supabase db push
```

Use the **session pooler** connection string for the API (the direct host is IPv6 only). A plain `postgresql://` URL is accepted.

## Configuration

Set through environment variables or `backend/.env` (see [`backend/.env.example`](backend/.env.example)).

| Variable | Default | Meaning |
|---|---|---|
| `SPECTRACE_DATABASE_URL` | unset | Postgres URL; unset means in-memory SQLite |
| `SPECTRACE_CORS_ORIGINS` | `["http://localhost:3000"]` | allowed browser origins, as a JSON list |
| `SPECTRACE_MAX_REQUEST_BYTES` | `12000000` | largest request body |
| `SPECTRACE_RATE_LIMIT_PER_MINUTE` | `120` | requests per client per minute |
| `SPECTRACE_RATE_LIMIT_HEAVY_PER_MINUTE` | `10` | POST requests (they run an analysis) per client per minute |
| `SPECTRACE_TRUST_PROXY_HEADERS` | `false` | read the client address from `X-Forwarded-For`; enable only behind a proxy you control |
| `SPECTRACE_LLM_*` | provider `none` | chat model: provider, key, model, base URL, timeout, retries, output and context size, call limits |
| `SPECTRACE_EMBEDDING_*` | provider `none` | embeddings: provider, key, model, base URL, batch size, chunk limit |

The interface needs one setting, `NEXT_PUBLIC_API_URL`. It is visible in the browser, so it must never hold a secret.

## API

| Method and path | Purpose |
|---|---|
| `GET /health` | liveness |
| `POST /v1/runs` | compare two versions; body `{files_a, files_b, label_a, label_b}` with `{path: text}` maps; returns the run summary |
| `GET /v1/runs` | recent runs |
| `GET /v1/runs/{id}` | a run with its changes, impacts, graph and notes |
| `POST /v1/runs/{id}/ask` | `{question}`; with a model configured, a written answer with numbered sources plus the graph's dependents; without one, name matching only. Says it is uncertain rather than guessing |
| `POST /v1/runs/{id}/narrative` | `{refresh}`; summaries of both versions and of what changed (needs a model); saved with the run |
| `GET /v1/capabilities` | whether a model and embeddings are configured, their names, and who would receive document text; never a key |
| `GET /v1/runs/{id}/snippet?version=a\|b&file=&line=&context=` | source lines around a cited location |

Every `/v1/runs` call needs an `X-Owner-Token` header: a random string of 16 to 128 characters (letters, digits, `-`, `_`) that the client creates and keeps. Only its SHA-256 hash is stored, and a run is visible only to its owner (another owner gets `404`). The web interface creates one per browser.

Errors always have the shape `{"error": {"code", "message"}}` with a stable code (`input_too_large`, `unsupported_input`, `parse_error`, `limit_exceeded`, `rate_limited`, `invalid_request`, `owner_required`, `not_found`, `llm_unavailable`, `llm_rate_limited`, `llm_timeout`, `llm_bad_output`, `budget_exceeded`, `internal_error`). Messages never echo submitted content.

Limits per version: 200 files, 1 MB per file, 5 MB in total, 200,000 YAML nodes, nesting depth 50, 20,000 entities. Absolute paths and `..` in file names are rejected.

## Security notes

- Uploaded files are untrusted: YAML is parsed with a round-trip loader (no object construction), bounded in nodes and depth, and file names are validated.
- Request size is checked before parsing, per-client rate limits apply, and validation errors are replaced by a fixed message so input is not reflected.
- Logs hold identifiers only (request id, route pattern, status, duration, error code), never file names or contents, and a filter redacts credentials in URLs.
- Secrets live in environment variables. The interface contains no database URL or key, and a test checks that none is served to the browser.
- The database tables have row level security enabled with no policies.
- There are no accounts. Each browser has a random owner token, and comparisons, documents and summaries are visible only to the token that created them, so a public deployment does not expose one visitor's documents to another. Clearing site data forgets the token.
- Provider keys live only on the server. Error messages and logs never include a key, a prompt or a reply, because a provider can echo the prompt, which holds the documents.

Known gaps: the owner token is possession-based, not an account (anyone holding it has access, and it cannot be recovered); rate limits and call budgets are per process and in memory; and the body-size check relies on `Content-Length`.

## Tests

```
cd backend  && pytest --cov=app --cov=scripts            # 227 tests; 8 need SPECTRACE_TEST_DATABASE_URL (Postgres with pgvector)
cd frontend && npm run typecheck && npm run lint && npm test
cd frontend && npm run test:e2e                          # Chrome, against a real API with an in-memory database
supabase test db                                         # SQL tests (needs Docker)
```

The end-to-end suite builds the interface, starts both servers (the API with the deterministic test model and the local hashing embedder, so the retrieval and answer path runs without a key), and covers the main flow, bad input, a down or rate-limited API, keyboard use, drag and drop, the theme toggle, axe accessibility scans in light and dark, small screens and text enlargement. By default it expects a conda environment named `SpecTrace` and the system Chrome; set `E2E_BACKEND_COMMAND` and `E2E_CHANNEL=""` to use a plain Python environment and the Chromium that `npx playwright install chromium` downloads (this is what CI does).

Accessibility is checked by automated tests; no screen-reader testing has been done yet. See [`frontend/ACCESSIBILITY.md`](frontend/ACCESSIBILITY.md).

## Deployment

1. **Database.** Create a Supabase project and apply the migration (`supabase db push`). Copy the session pooler URL.
2. **API on Render.** Create a Blueprint from `render.yaml`. Set `SPECTRACE_DATABASE_URL` to the pooler URL (as a secret) and `SPECTRACE_CORS_ORIGINS` to a JSON list holding the frontend origin. To enable the language-model features also set `SPECTRACE_LLM_PROVIDER`, `SPECTRACE_LLM_API_KEY` (secret), `SPECTRACE_LLM_MODEL`, and the embedding settings. The health check is `/health`.
3. **Interface on Vercel.** Import the repository, set the project root to `frontend`, and set `NEXT_PUBLIC_API_URL` to the Render URL. Then add the Vercel origin to `SPECTRACE_CORS_ORIGINS` on Render.

## Limitations

- Only OpenAPI 3 `components/schemas` references are resolved. No external or parameter references, no `allOf`/`oneOf` interpretation, and renamed entities appear as a removal plus an addition.
- Inputs are OpenAPI YAML or JSON and Markdown or plain text. There is no Git or GitHub ingestion yet; files are added in the interface or through the API.
- Each comparison is its own knowledge base. There is no persistent project library that spans comparisons yet.
- The language-model path has been tested with a deterministic stand-in and with simulated provider replies, including failures and hostile documents. It has not yet been run against a live provider, and answer quality with a real model has not been measured.
- Without embeddings, retrieval uses keywords and the graph only, which misses passages that share no words with the question.
- The inferred-link confidences (0.8 and 0.6) and the 0.75 similarity threshold are starting values, not tuned.
- Analysis runs inside the request. Large inputs are bounded by the limits above rather than queued.
- The benchmark is small, synthetic and not independently labeled.

## License

No license has been chosen yet. Until one is added, all rights are reserved by the authors.
