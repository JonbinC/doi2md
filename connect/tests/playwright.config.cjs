const { defineConfig } = require('@playwright/test');
const path = require('node:path');

// Self-hosted runners can retain a fixture from a cancelled job. Give every
// workflow attempt its own loopback ports instead of sharing fixed defaults.
const runId = Number.parseInt(process.env.GITHUB_RUN_ID || String(process.pid), 10);
const runAttempt = Number.parseInt(process.env.GITHUB_RUN_ATTEMPT || '1', 10);
const portSlot = ((runId * 7 + runAttempt * 13) % 15000 + 15000) % 15000;
const originPort = Number(process.env.MDTERO_CONNECT_TEST_ORIGIN_PORT) || 20000 + portSlot * 2;
const controlPort = Number(process.env.MDTERO_CONNECT_TEST_CONTROL_PORT) || originPort + 1;
process.env.MDTERO_CONNECT_TEST_ORIGIN_PORT = String(originPort);
process.env.MDTERO_CONNECT_TEST_CONTROL_PORT = String(controlPort);

module.exports = defineConfig({
  testDir: __dirname,
  testMatch: '**/*.spec.cjs',
  outputDir: path.join(__dirname, '../test-results'),
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30000,
  reporter: 'list',
  use: {
    baseURL: `http://127.0.0.1:${originPort}`,
    browserName: 'chromium',
    headless: true,
    launchOptions: {
      ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
        ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
        : {}),
      args: ['--no-sandbox'],
    },
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'uv run python connect/tests/serve_fixture.py',
    cwd: path.resolve(__dirname, '../..'),
    url: `http://127.0.0.1:${controlPort}/health`,
    env: {
      MDTERO_CONNECT_TEST_ORIGIN_PORT: String(originPort),
      MDTERO_CONNECT_TEST_CONTROL_PORT: String(controlPort),
    },
    reuseExistingServer: false,
    timeout: 30000,
  },
});
