/**
 * Demo screenshot capture for slides.
 *
 * Captures 6 focused crops of the featcat web UI for use in presentations:
 *   01 — Dashboard stats cards row
 *   02 — Features list with active search filter ("cpu")
 *   03a — Feature detail modal (header + metadata)
 *   03b — Feature detail modal (monitoring section)
 *   04 — AI chat conversation with mocked tool call
 *   05 — Group detail panel
 *   06 — Similarity matrix region
 *
 * Lineage is captured separately by capture_lineage_screenshot.ts because
 * it needs demo data seeding + cleanup that shouldn't be coupled to this
 * happy-path run.
 *
 * Run:
 *   bun run capture:demo                                  # default Vite at :5173
 *   FEATCAT_URL=http://localhost:8000 bun run capture:demo
 *   ONLY=04 bun run capture:demo                          # rerun a single shot
 */

import { chromium, type Page, type Locator } from '@playwright/test'
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
const ONLY = process.env.ONLY?.split(',').map((s) => s.trim()).filter(Boolean) ?? []

interface ClipRect {
  x: number
  y: number
  width: number
  height: number
}

async function setupPage(page: Page): Promise<void> {
  // 1440x900 viewport matches the design target; 115% zoom lifts text into
  // the readable range when these PNGs land on a slide.
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.evaluate(() => {
    document.documentElement.style.setProperty('zoom', '1.15')
  })
  await page.waitForTimeout(200)
}

async function waitForDataLoad(page: Page): Promise<void> {
  // The UI uses .animate-pulse for the Skeleton placeholder. Wait until it's
  // gone before screenshotting so we never capture a loading state. Cap at
  // 15s — anything slower is a real bug worth surfacing rather than papering
  // over with longer waits.
  await page
    .waitForFunction(
      () => document.querySelectorAll('.animate-pulse').length === 0,
      undefined,
      { timeout: 15_000 },
    )
    .catch(() => {
      console.warn('  ⚠ Skeletons still present after 15s — capturing anyway')
    })
  await page.waitForTimeout(400)
}

async function captureElement(locator: Locator, filename: string): Promise<void> {
  const full = path.join(OUTPUT_DIR, filename)
  await locator.screenshot({ path: full, type: 'png', scale: 'device' })
  console.log(`✓ ${filename}`)
}

async function captureRegion(page: Page, clip: ClipRect, filename: string): Promise<void> {
  const full = path.join(OUTPUT_DIR, filename)
  await page.screenshot({ path: full, type: 'png', clip, scale: 'device' })
  console.log(`✓ ${filename}`)
}

function shouldRun(id: string): boolean {
  if (ONLY.length === 0) return true
  // Allow "03" to match "03a" + "03b" as a convenience.
  return ONLY.some((o) => id.startsWith(o))
}

// 01 — Dashboard stats cards row
async function captureDashboard(page: Page): Promise<void> {
  if (!shouldRun('01')) return
  await page.goto(`${BASE_URL}/`)
  await waitForDataLoad(page)

  const stats = page.locator('[data-testid="stats-cards"]')
  await stats.waitFor({ state: 'visible', timeout: 5_000 })
  await captureElement(stats, '01-dashboard-stats.png')
}

// 02 — Features list with active search filter
async function captureFeaturesFilter(page: Page): Promise<void> {
  if (!shouldRun('02')) return
  await page.goto(`${BASE_URL}/features`)
  await waitForDataLoad(page)

  // SearchInput debounces 300ms; wait a bit longer to let the filter settle.
  const search = page.locator('input[type="search"], input[placeholder*="earch" i], input[placeholder*="ìm" i]').first()
  await search.fill('cpu')
  await page.waitForTimeout(700)

  const list = page.locator('[data-testid="features-list"]')
  await list.waitFor({ state: 'visible', timeout: 5_000 })
  await captureElement(list, '02-features-filter.png')
}

// 03 — Feature detail modal (header + monitoring)
async function captureFeatureDetail(page: Page): Promise<void> {
  if (!shouldRun('03')) return
  await page.goto(`${BASE_URL}/features`)
  await waitForDataLoad(page)

  // The features list uses two table renderers — DataTable produces real
  // <tr> rows, VirtualizedTable produces clickable <div> grids. Both live
  // inside [data-testid="features-list"] and carry the `cursor-pointer`
  // class. Match by that class to handle either renderer.
  const rowSelector = '[data-testid="features-list"] [class*="cursor-pointer"]'
  const documented = page.locator(rowSelector, { has: page.locator('.lucide-check') }).first()
  let target = documented
  if ((await documented.count()) === 0) {
    console.warn('  ⚠ No documented features found; using the first row instead')
    target = page.locator(rowSelector).first()
  }
  await target.waitFor({ state: 'visible', timeout: 5_000 })
  await target.click()

  const dialog = page.locator('[role="dialog"]')
  await dialog.waitFor({ state: 'visible', timeout: 5_000 })
  await waitForDataLoad(page)

  // 03a — modal as a whole (header + metadata + health). Bounded by max-w-2xl
  // so it sits well in slides on its own.
  await captureElement(dialog, '03a-feature-detail.png')

  // 03b — monitoring section if present. We scroll the modal to the
  // monitoring heading, then crop a region around it. If the section can't
  // be found (no baseline / drift data), skip with a warning rather than
  // capturing a misleading placeholder.
  const monitoringHeading = dialog.locator('h3, h2', { hasText: /drift|monitor|psi/i }).first()
  if ((await monitoringHeading.count()) === 0) {
    console.warn('  ⚠ No monitoring section visible — skipping 03b')
    return
  }
  await monitoringHeading.scrollIntoViewIfNeeded()
  await page.waitForTimeout(250)

  const headingBox = await monitoringHeading.boundingBox()
  const dialogBox = await dialog.boundingBox()
  if (!headingBox || !dialogBox) {
    console.warn('  ⚠ Could not measure monitoring section bounds — skipping 03b')
    return
  }
  await captureRegion(
    page,
    {
      x: dialogBox.x,
      y: headingBox.y - 8,
      width: dialogBox.width,
      height: Math.min(360, dialogBox.y + dialogBox.height - headingBox.y),
    },
    '03b-feature-monitoring.png',
  )
}

// 04 — AI chat conversation with mocked tool call
async function captureAIChat(page: Page): Promise<void> {
  if (!shouldRun('04')) return

  // Mock the chat endpoint. The frontend dispatches on `type`:
  //   thinking_start | thinking | thinking_end | tool_call | tool_result |
  //   token | result | done | error
  // It reads SSE frames (`event:` and `data:` separated by blank lines).
  const sseBody = [
    'event: message',
    'data: {"type":"thinking_start"}',
    '',
    'event: message',
    'data: {"type":"thinking","content":"Đang tìm các feature liên quan đến churn..."}',
    '',
    'event: message',
    'data: {"type":"thinking_end"}',
    '',
    'event: message',
    'data: {"type":"tool_call","id":"t1","name":"search_features","input":{"query":"churn"}}',
    '',
    'event: message',
    'data: {"type":"tool_result","id":"t1","result":"Found 5 features: user_behavior.churn_label, user_behavior.contract_months, user_behavior.complaint_count, user_behavior.days_since_last_login, user_behavior.monthly_charge"}',
    '',
    'event: message',
    'data: {"type":"token","content":"Đây là 5 features phù hợp cho churn prediction:\\n\\n"}',
    '',
    'event: message',
    'data: {"type":"token","content":"1. `user_behavior.churn_label` — target variable\\n"}',
    '',
    'event: message',
    'data: {"type":"token","content":"2. `user_behavior.contract_months` — thời gian hợp đồng\\n"}',
    '',
    'event: message',
    'data: {"type":"token","content":"3. `user_behavior.complaint_count` — số lượng khiếu nại\\n"}',
    '',
    'event: message',
    'data: {"type":"token","content":"4. `user_behavior.days_since_last_login` — ngày từ lần đăng nhập cuối\\n"}',
    '',
    'event: message',
    'data: {"type":"token","content":"5. `user_behavior.monthly_charge` — phí hàng tháng"}',
    '',
    'event: message',
    'data: {"type":"done"}',
    '',
    '',
  ].join('\n')

  await page.route('**/api/ai/chat', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      headers: { 'Cache-Control': 'no-cache', 'X-Session-Id': 'mock-session' },
      body: sseBody,
    })
  })

  await page.goto(`${BASE_URL}/chat`)
  await page.waitForTimeout(300)

  const input = page.locator('textarea').first()
  await input.fill('Cho tôi danh sách feature liên quan đến churn')
  await input.press('Enter')

  // Wait for the mocked answer to render — the last token contains
  // "monthly_charge" which is distinctive enough to confirm streaming
  // finished.
  await page.waitForSelector('text=monthly_charge', { timeout: 8_000 })
  await page.waitForTimeout(400)

  const messages = page.locator('[data-testid="chat-messages"]')
  await captureElement(messages, '04-ai-chat-conversation.png')
}

// 05 — Group detail panel
async function captureGroup(page: Page): Promise<void> {
  if (!shouldRun('05')) return
  await page.goto(`${BASE_URL}/groups`)
  await waitForDataLoad(page)

  const firstGroup = page.locator('[data-testid="group-row"]').first()
  if ((await firstGroup.count()) === 0) {
    console.warn('  ⚠ No groups in catalog — capturing the empty groups page')
    await captureElement(page.locator('main'), '05-groups-empty.png')
    return
  }
  await firstGroup.click()

  const detail = page.locator('[data-testid="group-detail"]')
  await detail.waitFor({ state: 'visible', timeout: 5_000 })
  await waitForDataLoad(page)
  await captureElement(detail, '05-group-detail.png')
}

// 06 — Similarity matrix
async function captureSimilarityMatrix(page: Page): Promise<void> {
  if (!shouldRun('06')) return
  await page.goto(`${BASE_URL}/similarity?tab=matrix`)
  await waitForDataLoad(page)

  // Drop the threshold to 0 — TF-IDF similarity on this catalog peaks
  // around ~0.4, so the default 0.3 filters most pairs out and the page
  // renders blank padding. 0 shows every pair as a light heatmap cell,
  // which is what reads on a slide.
  const numericThreshold = page.locator('input[type="number"][aria-label]').first()
  if ((await numericThreshold.count()) > 0) {
    await numericThreshold.fill('0')
    await numericThreshold.press('Tab')
  } else {
    const slider = page.locator('input[type="range"]').first()
    if ((await slider.count()) > 0) await slider.fill('0')
  }

  const matrix = page.locator('[data-testid="similarity-matrix"]')
  if ((await matrix.count()) === 0) {
    console.warn('  ⚠ Similarity matrix container not found — skipping')
    return
  }

  // The matrix grid renders a <table> with <td> cells once features
  // resolve to ids and the /similarity-matrix request returns. Wait for
  // at least one scored cell (cells carry a `cursor-pointer` class — the
  // empty diagonal/lower-triangle cells don't).
  const scoredCell = matrix.locator('table td[class*="cursor-pointer"]').first()
  try {
    await scoredCell.waitFor({ state: 'visible', timeout: 15_000 })
  } catch {
    console.warn('  ⚠ No matrix cells rendered after 15s — capturing whatever is there')
  }
  // Let any in-flight cell coloring settle.
  await page.waitForTimeout(400)

  // Anchor the crop to the table (not the outer container's empty padding).
  const table = matrix.locator('table').first()
  const box = (await table.boundingBox()) ?? (await matrix.boundingBox())
  if (!box) {
    console.warn('  ⚠ Could not measure matrix bounds — skipping')
    return
  }

  await captureRegion(
    page,
    {
      x: box.x,
      y: box.y,
      width: Math.min(700, box.width),
      height: Math.min(550, box.height),
    },
    '06-similarity-matrix.png',
  )
}

// 08 — Audit / change history
async function captureAudit(page: Page): Promise<void> {
  if (!shouldRun('08')) return
  await page.goto(`${BASE_URL}/audit`)
  await waitForDataLoad(page)

  const audit = page.locator('[data-testid="audit-page"]')
  if ((await audit.count()) === 0) {
    console.warn('  ⚠ Audit page container not found — skipping')
    return
  }
  await captureElement(audit, '08-audit-page.png')
}

async function main(): Promise<void> {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true })
  console.log(`Target URL: ${BASE_URL}`)
  console.log(`Output:     ${OUTPUT_DIR}`)
  if (ONLY.length > 0) console.log(`Only:       ${ONLY.join(', ')}`)

  const browser = await chromium.launch()
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    colorScheme: 'dark',
  })
  const page = await context.newPage()
  await setupPage(page)

  // Persist a dark-theme preference so the UI flips even if `colorScheme:
  // 'dark'` alone isn't enough (the app reads localStorage and toggles a
  // class on documentElement).
  await context.addInitScript(() => {
    try {
      localStorage.setItem('theme', 'dark')
    } catch {
      /* ignore: incognito / blocked storage */
    }
  })

  const t0 = Date.now()
  try {
    await captureDashboard(page)
    await captureFeaturesFilter(page)
    await captureFeatureDetail(page)
    await captureAIChat(page)
    await captureGroup(page)
    await captureSimilarityMatrix(page)
    await captureAudit(page)
  } finally {
    await browser.close()
  }

  const files = fs.readdirSync(OUTPUT_DIR).filter((f) => f.endsWith('.png'))
  files.sort()
  console.log(`\nWrote ${files.length} file(s) in ${((Date.now() - t0) / 1000).toFixed(1)}s:`)
  for (const f of files) {
    const stats = fs.statSync(path.join(OUTPUT_DIR, f))
    console.log(`  ${f}  ${(stats.size / 1024).toFixed(0)} KB`)
  }
}

main().catch((err) => {
  console.error('Capture failed:', err)
  process.exit(1)
})
