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

## Graph maintenance rules

- Update the graph when a component, data contract, trust boundary, state transition, persistence dependency, or external integration changes.
- Add nodes and edges only when grounded in actual code or explicitly labeled as planned.
- Keep diagrams readable; split a graph if it becomes too dense.
- Explain non-obvious edges and failure paths in `Explain.md`.
