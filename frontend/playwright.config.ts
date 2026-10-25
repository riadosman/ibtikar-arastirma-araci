import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 60000,
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3100",
    headless: true,
    reducedMotion: "reduce",
    trace: "retain-on-failure",
  },
  reporter: "list",
});
