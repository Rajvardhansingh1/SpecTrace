import { defineConfig } from "@playwright/test";

const FRONTEND = "http://localhost:3000";
const BACKEND = "http://localhost:8000";

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
    // The system Chrome is used so no browser download is needed.
    channel: "chrome",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      // An empty database URL forces in-memory SQLite, so tests never reach a hosted database
      // even when backend/.env points at one.
      command: "conda run --no-capture-output -n SpecTrace python -m uvicorn app.main:app --port 8000",
      cwd: "../backend",
      url: `${BACKEND}/health`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        SPECTRACE_DATABASE_URL: "",
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
