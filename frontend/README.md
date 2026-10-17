# SpecTrace frontend

Next.js (App Router, TypeScript) client for the SpecTrace API. Design direction and tokens: [DESIGN.md](DESIGN.md).

## Run it

```
cp .env.example .env.local        # NEXT_PUBLIC_API_URL, default http://localhost:8000
npm install
npm run dev                       # http://localhost:3000
```

The backend must be running (`conda run -n SpecTrace python -m uvicorn app.main:app --port 8000` from `backend/`). Without `SPECTRACE_DATABASE_URL` the backend keeps runs in memory.

`NEXT_PUBLIC_API_URL` is visible in the browser. Never put a secret in it.

## Checks

```
npm run typecheck
npm run lint
npm test            # unit and component tests (Vitest)
npm run test:e2e    # builds, starts the backend with an in-memory database and the frontend, runs Chrome tests
```

The end-to-end tests use the system Chrome and start both servers themselves. The backend they start is given an empty database URL, so they never reach a hosted database.

## Data copied from the repository

The Vercel project root is `frontend/`, so the build cannot read `../samples` or `../benchmark`. `npm run sync` copies the petstore sample into `lib/sample-data.json` and the latest `benchmark/v1/results/*-all.json` into `data/benchmark.json`. Both generated files are committed. Re-run `sync` after changing the sample or saving a new benchmark result.

## Pages

| Route | Purpose |
|---|---|
| `/` | Add two versions of files (or load the petstore example), compare, browse earlier comparisons |
| `/runs/[id]` | Optional written summaries, change ledger, evidence paths with the cited source lines, source diff, questions with numbered sources |
| `/benchmark` | Stored benchmark result with the limits of its labels |

## Known limits

- Accessibility is checked by automated tests only; no real screen reader or user testing yet (see [ACCESSIBILITY.md](ACCESSIBILITY.md)).
- Tests run in Chrome only.
- Not deployed. The Vercel build and the production CORS origin are unverified.
