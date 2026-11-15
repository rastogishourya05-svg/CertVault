import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
const repo = path.resolve(__dirname, "../..");
const python =
  process.platform === "win32"
    ? `"${path.join(repo, ".venv/Scripts/python.exe")}"`
    : "python";
export default defineConfig({
  timeout: 90000,
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  webServer: [
    {
      command: `${python} -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --no-access-log`,
      cwd: repo,
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: !process.env.CI,
      timeout: 60000,
    },
    {
      command: `node node_modules/next/dist/bin/next ${process.env.CI ? "start" : "dev"} --hostname 127.0.0.1`,
      cwd: __dirname,
      url: "http://127.0.0.1:3000",
      reuseExistingServer: !process.env.CI,
      timeout: 60000,
    },
  ],
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace:
      process.env.CERTVAULT_LIVE_TESTS === "1"
        ? "off"
        : process.env.CI
          ? "retain-on-failure"
          : "off",
    channel: process.env.PLAYWRIGHT_CHANNEL,
  },
  projects: [
    {
      name: "desktop",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
      },
    },
    {
      name: "mobile",
      use: {
        ...devices["iPhone 13"],
        defaultBrowserType: "chromium",
        viewport: { width: 390, height: 844 },
      },
    },
  ],
});
