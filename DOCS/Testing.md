# Testing Plan — SpecTrace

> **USER-OWNED / IMMUTABLE TO THE MODEL.** This file was initialized because the user requested a project testing plan. After initialization, an AI/coding agent must not edit, append to, regenerate, or reformat this file unless the user explicitly authorizes changes to `Testing.md`. Agents may read it. Record actual test outcomes in `State.md`; implement tests in source files.

## 1. Testing goals
- Verify correctness of the domain workflow.
- Verify API schemas and error handling.
- Verify persistence and restart behavior where relevant.
- Verify security boundaries and safe handling of untrusted input.
- Verify the benchmark can be reproduced.
- Verify Vercel frontend to Render backend integration.

## 2. Test layers
### Unit tests
Test parsers, validators, policy rules, scoring/metric functions, state transitions, and domain services in isolation. Use deterministic fixtures.

### Integration tests
Test API + database, adapter boundaries, migrations, persistence, timeout behavior, and error mapping. Prefer mock providers for reproducibility.

### End-to-end tests
Exercise the main user flow from frontend request to backend result and trace. Include empty input, malformed input, backend failure, and long-running task status if applicable.

### Security tests
Test oversized input, invalid schema, injection-like input, authorization boundaries, secret leakage in logs, rate limits, and unsafe external actions. Use synthetic data.

### Reliability tests
Inject provider/network faults and verify bounded retries, no uncontrolled retry loops, graceful failure, and correct state persistence.

### Benchmark tests
Run the fixed dataset with pinned configurations. Report metric definitions, dataset version, model/provider/version, run date, and baseline. Do not compare results from different datasets as if directly comparable.

## 3. Project-specific test scenarios
- [ ] Two versions with one breaking API change produce the expected change record.
- [ ] Known downstream references are retrieved and correctly cited.
- [ ] Unrelated components are not reported as confirmed impacts.
- [ ] Unsupported or ambiguous impact questions are labeled as uncertain.
- [ ] Private repository access is not attempted without authorized credentials.

## 4. Commands to establish during implementation
These are placeholders until the actual project layout and tooling are confirmed:
- Install dependencies using the lockfile and documented package manager.
- Run formatting/linting.
- Run unit tests.
- Run integration tests against a disposable test database.
- Run the project benchmark.
- Build the frontend.
- Start the backend and check `/health`.
- Run a smoke test against the deployed frontend/backend.

Do not invent successful results. Record actual commands, exit codes, failures, and skipped checks in `State.md`.

## 5. Release acceptance checklist
- [ ] Main user flow works locally.
- [ ] Negative/error paths are covered.
- [ ] No secrets are committed or exposed to the frontend.
- [ ] Persistent state survives a restart where required.
- [ ] Benchmark command and metric definitions are documented.
- [ ] Vercel build succeeds.
- [ ] Render deployment and health check succeed.
- [ ] Frontend-to-backend CORS and environment configuration are verified.
- [ ] README states known limitations.
