import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

/** Vitest sits alongside Vite (shared resolve aliases + React plugin) but
 *  swaps the Playwright browser for jsdom so component tests run fast in
 *  Node. Co-located `*.test.{ts,tsx}` files live next to their components.
 *
 *  Excludes the Playwright e2e tree (`tests/e2e/`) so the two runners stay
 *  in their own lanes — `bun run test` for unit, `bun run test:e2e` for e2e.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    exclude: ['tests/e2e/**', 'node_modules/**'],
    css: true,
  },
})
