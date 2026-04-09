import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 45_000,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:3011",
    trace: "on-first-retry"
  },
  webServer: [
    {
      command: "node tests/mock-ollama-server.js",
      port: 11435,
      reuseExistingServer: false,
      timeout: 120_000
    },
    {
      command: "python -m uvicorn api:app --host 127.0.0.1 --port 18000",
      cwd: "..",
      env: {
        ...process.env,
        OLLAMA_API_KEY: "playwright-test-key",
        OLLAMA_HOST: "http://127.0.0.1:11435",
        OLLAMA_LOCAL_HOST: "http://127.0.0.1:11435"
      },
      port: 18000,
      reuseExistingServer: false,
      timeout: 120_000
    },
    {
      command: "npm run dev -- --port 3011",
      env: {
        ...process.env,
        NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:18000"
      },
      port: 3011,
      reuseExistingServer: false,
      timeout: 120_000
    }
  ]
});
