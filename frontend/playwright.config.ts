import { defineConfig } from "@playwright/test";

const FRONTEND = "http://localhost:3000";
const BACKEND = "http://localhost:8000";

// Defaults suit the local setup (system Chrome, a conda environment named SpecTrace). CI overrides them.
const BACKEND_COMMAND =
  process.env.E2E_BACKEND_COMMAND ??
  "conda run --no-capture-output -n SpecTrace python -m uvicorn app.main:app --port 8000";
// An empty E2E_CHANNEL selects the Chromium that `playwright install` downloads.
const CHANNEL = process.env.E2E_CHANNEL === undefined ? "chrome" : process.env.E2E_CHANNEL || undefined;

export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  // The first request after startup can be slow on a busy machine.
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: FRONTEND,
    channel: CHANNEL,
    trace: "retain-on-failure",
  },
  webServer: [
    {
      // An empty database URL forces in-memory SQLite, so tests never reach a hosted database
      // even when backend/.env points at one.
      command: BACKEND_COMMAND,
      cwd: "../backend",
      url: `${BACKEND}/health`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        SPECTRACE_DATABASE_URL: "",
        // The deterministic test model and the local embedder exercise the whole retrieval and
        // answer path without a provider or a key.
        SPECTRACE_LLM_PROVIDER: "test",
        SPECTRACE_EMBEDDING_PROVIDER: "hashing",
        SPECTRACE_LLM_CALLS_PER_OWNER_PER_HOUR: "100000",
        SPECTRACE_LLM_CALLS_PER_DAY: "1000000",
        SPECTRACE_RATE_LIMIT_HEAVY_PER_MINUTE: "200",
        SPECTRACE_RATE_LIMIT_PER_MINUTE: "2000",
      },
    },
    {
      command: "npm run build && npm run start",
      url: FRONTEND,
      reuseExistingServer: false,
      timeout: 240_000,
      env: { NEXT_PUBLIC_API_URL: BACKEND },
    },
  ],
});
