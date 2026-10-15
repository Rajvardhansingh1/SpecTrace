# Design Graph — Version-aware technical documentation retrieval and change-impact analysis

> These graphs describe the intended MVP architecture. Keep them synchronized with the implementation. Mark unimplemented nodes as planned in `State.md`; do not present planned architecture as shipped.

## 1. System context

```mermaid
flowchart TB
    U[User / Developer] --> UI[Next.js UI on Vercel]
    UI --> API[FastAPI API on Render]
    API --> CORE[Domain Logic]
    CORE --> DB[(PostgreSQL / persistent storage)]
    CORE --> EXT[External adapters / model or source systems]
    CORE --> OBS[Logs, metrics, audit events]
    OBS --> DB
    API --> UI
```

## 2. High-level request flow

```mermaid
flowchart TD
    A[User submits task] --> B[Validate request and identity]
    B --> C[Normalize input and load persisted state]
    C --> D[Run domain workflow]
    D --> E{Decision / validation gate}
    E -->|Valid| F[Persist result and evidence]
    E -->|Recoverable issue| G[Bounded recovery or clarification]
    E -->|Unsafe / unsupported| H[Reject safely with reason]
    G --> D
    F --> I[Return result with trace]
    H --> I
```

## 3. Detailed project workflow

```mermaid
flowchart TD
    A[Input] --> B[Parse and validate]
    B --> C[Build typed internal representation]
    C --> D[Core project operation]
    D --> E[Independent validation / policy check]
    E -->|Pass| F[Persist result and trace]
    E -->|Fail| G[Bounded correction, retry, or reject]
    G --> E
    F --> H[API response]
```

## 4. Deployment and trust boundaries

```mermaid
flowchart LR
    subgraph Browser["User-controlled browser"]
      UI[Next.js frontend]
    end
    subgraph Server["Render backend / trusted server"]
      API[FastAPI]
      AUTH[Authentication and input validation]
      CORE[Domain logic]
      SECRETS[Server-side secrets]
    end
    subgraph Persistence["Persistent services"]
      DB[(PostgreSQL)]
    end
    UI -->|HTTPS; no provider secrets| API
    API --> AUTH --> CORE
    CORE --> DB
    CORE --> SECRETS
```

## 5. Project-specific workflow

```mermaid
flowchart TD
    A[Ingest version A and B] --> B[Normalize and validate]
    B --> C[Execute core operation]
    C --> D[Validate evidence, result, or policy]
    D -->|Pass| E[Persist output and metrics]
    D -->|Fail| F[Recover, abstain, or reject]
    F --> G[Record failure reason]
    E --> H[Display result and trace]
    G --> H
```

## 6. Implemented core engine data flow (as of 2026-10-16)

Everything in this diagram exists and is unit-tested. Nodes outside it (database, HTTP routes, frontend, benchmark) are planned.

```mermaid
flowchart TD
    FILES["files A and B: {path: text}"] --> CHK["_build: path safety, size and count limits"]
    CHK -->|.yaml .yml .json| OAS["parse_openapi: ruamel rt, node/depth caps"]
    CHK -->|.md .txt| MD["parse_markdown"]
    CHK -->|other types or non-OpenAPI| UNS["unsupported list"]
    OAS --> PR["ParseResult: entities, direct edges"]
    MD --> PR2["ParseResult: entities, raw refs"]
    PR --> G["build_graph: resolve refs, label confirmed or inferred"]
    PR2 --> G
    G --> GA["Graph A"]
    G --> GB["Graph B"]
    GA --> D["diff_graphs: hash compare, deterministic classification"]
    GB --> D
    D --> CH["Change list with source diffs"]
    CH --> I["find_impacts: reverse-edge paths over A and B edges, depth 3"]
    GA --> I
    GB --> I
    I --> R["AnalysisResult: changes, impacts with evidence paths, warnings, stats"]
    R --> Q["answer_question: answered, no_change or uncertain"]
```

Trust boundary note: every input to `_build` is untrusted. Limits and path checks run before parsing; the only code that interprets YAML is `parsers/openapi.py`.

## Graph maintenance rules

- Update the graph when a component, data contract, trust boundary, state transition, persistence dependency, or external integration changes.
- Add nodes and edges only when grounded in actual code or explicitly labeled as planned.
- Keep diagrams readable; split a graph if it becomes too dense.
- Explain non-obvious edges and failure paths in `Explain.md`.

## Persistence and API flow (implemented 2026-10-16; hosted DB not yet connected to the backend)

```mermaid
flowchart LR
    C[Client] -->|JSON, size-checked| API[/v1/runs routes/]
    API --> P[core.pipeline.analyze]
    API <--> S[RunStore SQLAlchemy]
    S -->|local tests| PG[(Postgres 17 via Supabase CLI)]
    S -->|prod, planned| SB[(Supabase via session pooler)]
    SB -. RLS on, no policies; anon and authenticated revoked .- X[public REST API blocked]
```

Trust boundary: request bodies are untrusted and are size-limited before parsing; the database is
reachable only from the backend. Run states: `running` -> `done` or `failed` (with error code).

Request middleware order (implemented): `CORS -> log_requests -> rate_limit -> limit_body_size -> route`. The rate limiter keeps per-client timestamps in process memory (planned limitation: not shared across workers). Logs are a trust boundary: only request id, route template, status, duration and error codes leave the process.

## Frontend flow (implemented 2026-10-16, tested locally, not deployed)

```mermaid
flowchart LR
    U[Browser] -->|files read locally| F[Compare form]
    F -->|POST /v1/runs| API[(SpecTrace API)]
    API --> R[Run view]
    R -->|GET /v1/runs/id| API
    R -->|GET /v1/runs/id/snippet| API
    R -->|POST /v1/runs/id/ask| API
    B[Benchmark page] --- D[(data/benchmark.json, copied at build)]
```

Trust boundary: the browser sends file contents to the API and receives only JSON. The API origin must be in `SPECTRACE_CORS_ORIGINS`; `Retry-After` and `X-Request-ID` are exposed to it. The frontend contains no database URL or key.
