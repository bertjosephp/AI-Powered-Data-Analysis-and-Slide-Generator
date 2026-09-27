import { defineConfig } from "@playwright/test";

// End-to-end run against the real FastAPI backend in mock mode (no API keys, no credits).
// Uses dedicated ports so it doesn't collide with `make dev`. Stop `make dev` first:
// Next.js allows one dev server per project directory.
const API_PORT = 8010;
const WEB_PORT = 3010;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    // Uses the locally installed Chrome, so no browser download is needed.
    channel: "chrome",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `.venv/bin/uvicorn app.main:app --port ${API_PORT}`,
      cwd: "../api",
      env: { MOCK_EXTERNAL: "true", CORS_ORIGINS: `http://localhost:${WEB_PORT}` },
      url: `http://127.0.0.1:${API_PORT}/api/v1/health`,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: `pnpm next dev --port ${WEB_PORT}`,
      env: { NEXT_PUBLIC_API_BASE_URL: `http://localhost:${API_PORT}/api/v1` },
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
