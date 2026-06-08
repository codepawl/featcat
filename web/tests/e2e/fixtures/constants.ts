import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))

export const BACKEND_PORT = 8101
export const FRONTEND_PORT = 5174
export const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`
export const FRONTEND_URL = `http://localhost:${FRONTEND_PORT}`

export const REPO_ROOT = resolve(__dirname, '../../../..')
export const VENV_PYTHON = resolve(REPO_ROOT, '.venv/bin/python')
export const FIXTURES_PARQUET_DIR = resolve(REPO_ROOT, 'tests/fixtures')
export const TMP_DIR = resolve(__dirname, '../.tmp')
export const TEST_DB_PATH = resolve(TMP_DIR, 'e2e.db')
