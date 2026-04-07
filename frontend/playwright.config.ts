import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 45_000,
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "on-first-retry"
  },
  webServer: {
    command: "npm run dev -- --port 3000",
    port: 3000,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000
  }
});
