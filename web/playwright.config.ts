import { defineConfig, devices } from '@playwright/test'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))

const BACKEND_PORT = 8101
const FRONTEND_PORT = 5174
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`
const FRONTEND_URL = `http://localhost:${FRONTEND_PORT}`

const REPO_ROOT = resolve(__dirname, '..')
const TMP_DIR = resolve(__dirname, 'tests/e2e/.tmp')
const TEST_DB_PATH = resolve(TMP_DIR, 'e2e.db')

// Wipe + create the temp dir as part of the webServer command so it runs
// exactly ONCE per test run — not on every worker import of this config.
const BACKEND_BOOT_CMD =
  `mkdir -p "${TMP_DIR}" && ` +
  `rm -f "${TEST_DB_PATH}" "${TEST_DB_PATH}-journal" "${TEST_DB_PATH}-wal" "${TEST_DB_PATH}-shm" && ` +
  `"${REPO_ROOT}/.venv/bin/python" -m uvicorn featcat.server:create_app --factory --host 127.0.0.1 --port ${BACKEND_PORT}`

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: process.env.CI ? 'github' : [['list'], ['html', { open: 'never' }]],
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: FRONTEND_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command: BACKEND_BOOT_CMD,
      url: `${BACKEND_URL}/api/health`,
      cwd: REPO_ROOT,
      reuseExistingServer: false,
      timeout: 60_000,
      stdout: 'ignore',
      stderr: 'pipe',
      env: {
        FEATCAT_CATALOG_DB_PATH: TEST_DB_PATH,
        FEATCAT_LLAMACPP_URL: 'http://127.0.0.1:1',
        FEATCAT_SERVER_HOST: '127.0.0.1',
        FEATCAT_SERVER_PORT: String(BACKEND_PORT),
        FEATCAT_AUTO_DOC: 'false',
        PYTHONUNBUFFERED: '1',
      },
    },
    {
      command: `vite --port ${FRONTEND_PORT} --strictPort`,
      url: FRONTEND_URL,
      cwd: __dirname,
      reuseExistingServer: false,
      timeout: 60_000,
      stdout: 'pipe',
      stderr: 'pipe',
      env: {
        VITE_API_PROXY: BACKEND_URL,
      },
    },
  ],
})

export { BACKEND_URL, FRONTEND_URL, TEST_DB_PATH, TMP_DIR }
