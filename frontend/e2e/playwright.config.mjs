import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  workers: 1,
  retries: 0,
  timeout: 90_000,
  use: {
    baseURL: "https://localhost",
    ignoreHTTPSErrors: true,
    ...devices["Desktop Chrome"],
  },
});
