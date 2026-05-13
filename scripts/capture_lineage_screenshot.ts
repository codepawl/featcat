/**
 * Lineage screenshot capture — separate from the main demo run.
 *
 * Kept independent because:
 *   1. It needs demo lineage to exist in the catalog (it seeds it).
 *   2. The Lineage view is shipping on its own branch; this script can run
 *      the day that lands without waiting on the rest of the demo capture.
 *   3. It self-cleans the demo data afterwards so it doesn't pollute the
 *      dev catalog.
 *
 * Run:
 *   bun run capture:lineage
 *   FEATCAT_URL=http://localhost:8000 bun run capture:lineage
 *   SKIP_SEED=1 bun run capture:lineage   # if data is already seeded
 *
 * Requires the featcat CLI on PATH (uv pip install -e .[dev] does this).
 */

import { chromium } from '@playwright/test'
import { execSync } from 'node:child_process'
import * as fs from 'node:fs'
import * as path from 'node:path'

const OUTPUT_DIR = path.resolve(
  process.cwd(),
  '..',
  'slides',
  'screenshots',
  `featcat-demo-${new Date().toISOString().slice(0, 10)}`,
)
const BASE_URL = (process.env.FEATCAT_URL ?? 'http://localhost:5173').replace(/\/$/, '')
const FIXTURE = path.resolve(process.cwd(), '..', 'tests', 'fixtures', 'lineage-demo.json')
const SKIP_SEED = process.env.SKIP_SEED === '1'

function runCli(args: string): boolean {
  try {
    execSync(`featcat ${args}`, { stdio: 'inherit' })
    return true
  } catch {
    return false
  }
}

async function main(): Promise<void> {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true })
  console.log(`Target URL: ${BASE_URL}`)
  console.log(`Output:     ${OUTPUT_DIR}`)

  if (!SKIP_SEED) {
    console.log(`Seeding demo lineage from ${FIXTURE}...`)
    if (!fs.existsSync(FIXTURE)) {
      console.error(`Fixture not found: ${FIXTURE}`)
      process.exit(1)
    }
    if (!runCli(`lineage seed ${FIXTURE} --force`)) {
      console.error('Seed failed. Ensure `featcat` is on PATH and the catalog is initialized.')
      process.exit(1)
    }
  } else {
    console.log('SKIP_SEED=1 — assuming demo data is already present')
  }

  const browser = await chromium.launch()
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    colorScheme: 'dark',
  })
  const page = await context.newPage()
  await page.setViewportSize({ width: 1440, height: 900 })
  await context.addInitScript(() => {
    try {
      localStorage.setItem('theme', 'dark')
    } catch {
      /* ignore */
    }
  })
  await page.evaluate(() => {
    document.documentElement.style.setProperty('zoom', '1.15')
  })

  try {
    await page.goto(`${BASE_URL}/lineage`)

    // The lineage container exists immediately; we want the simulation to
    // have laid out and settled. Wait for the graph node count to stop
    // changing as a proxy for "layout done", capped at 5s.
    const graph = page.locator('[data-testid="lineage-graph"]')
    await graph.waitFor({ state: 'visible', timeout: 15_000 })
    await page.waitForFunction(
      () => {
        const svg = document.querySelector('[data-testid="lineage-graph"] svg')
        const canvas = document.querySelector('[data-testid="lineage-graph"] canvas')
        return (svg && svg.querySelectorAll('g, circle, rect, text').length > 0) || !!canvas
      },
      undefined,
      { timeout: 15_000 },
    )
    // Let d3-force settle and any "fit" animation finish.
    await page.waitForTimeout(2_500)

    const filename = '07-lineage-graph.png'
    await graph.screenshot({
      path: path.join(OUTPUT_DIR, filename),
      type: 'png',
      scale: 'device',
    })
    const stats = fs.statSync(path.join(OUTPUT_DIR, filename))
    console.log(`✓ ${filename}  ${(stats.size / 1024).toFixed(0)} KB`)
  } finally {
    await browser.close()

    if (!SKIP_SEED) {
      console.log('\nCleaning up demo lineage...')
      if (!runCli('lineage clear --demo-only --yes')) {
        console.warn('  ⚠ Cleanup failed. Run manually: featcat lineage clear --demo-only --yes')
      }
    }
  }
}

main().catch((err) => {
  console.error('Capture failed:', err)
  process.exit(1)
})
