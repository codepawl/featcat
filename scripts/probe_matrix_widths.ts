/**
 * One-shot Playwright probe: measure the actual rendered width of every cell
 * in /similarity?tab=matrix to confirm (or refute) the table-layout:fixed +
 * <colgroup> contract from MatrixGrid.tsx.
 *
 * Reads getBoundingClientRect().width (not clientWidth — that excludes
 * borders) on every <th> and <td> inside the matrix table. Buckets by
 * rounded width and prints a histogram. Outliers come with their column
 * indices so the offending CSS rule is easy to track down.
 *
 * Run:
 *   FEATCAT_URL=http://localhost:8000 bun run scripts/probe_matrix_widths.ts
 *
 * Exits non-zero only on probe error (matrix not rendering, no cells found),
 * NOT on width variance — the goal is to report, not gate.
 */

import { chromium } from '@playwright/test'

const BASE_URL = (process.env.FEATCAT_URL ?? 'http://localhost:5173').replace(/\/$/, '')

interface CellMeasurement {
  rowIndex: number
  colIndex: number
  tag: 'TD' | 'TH'
  width: number
}

interface ProbeResult {
  featureCount: number
  rowLabelColumnWidths: number[]
  headerCellWidths: number[]
  dataCellWidths: CellMeasurement[]
}

async function main(): Promise<void> {
  console.log(`Target: ${BASE_URL}/similarity?tab=matrix`)
  const browser = await chromium.launch()
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    colorScheme: 'dark',
  })
  const page = await context.newPage()

  try {
    await page.goto(`${BASE_URL}/similarity?tab=matrix`, { waitUntil: 'networkidle' })

    // Wait for skeletons to clear (the matrix is lazy-loaded).
    await page
      .waitForFunction(() => document.querySelectorAll('.animate-pulse').length === 0, undefined, {
        timeout: 15_000,
      })
      .catch(() => {
        console.warn('  ⚠ skeletons still present after 15s — continuing')
      })

    // Drop threshold to 0 so every cell renders, eliminating the
    // "upper-empty" rendering branch and letting us measure every cell.
    const numericThreshold = page.locator('input[type="number"][aria-label]').first()
    if ((await numericThreshold.count()) > 0) {
      await numericThreshold.fill('0')
      await numericThreshold.press('Tab')
    }
    await page.waitForTimeout(400)

    // Confirm the matrix table is present.
    const matrix = page.locator('[data-testid="similarity-matrix"] table')
    if ((await matrix.count()) === 0) {
      console.error('✗ matrix table not rendered — aborting')
      process.exit(2)
    }

    const result = await page.evaluate<ProbeResult>(() => {
      const table = document.querySelector('[data-testid="similarity-matrix"] table')
      if (!table) {
        throw new Error('no table')
      }
      const rows = Array.from(table.querySelectorAll('tr'))
      const headerRow = rows[0]
      const dataRows = rows.slice(1)
      // Header row: corner + N column headers. Skip the corner (index 0).
      const headerCells = Array.from(headerRow.querySelectorAll('th'))
      const headerCellWidths = headerCells.slice(1).map((el) => el.getBoundingClientRect().width)

      const rowLabelColumnWidths: number[] = []
      const dataCellWidths: { rowIndex: number; colIndex: number; tag: 'TD' | 'TH'; width: number }[] = []
      dataRows.forEach((tr, rowIndex) => {
        const rowCells = Array.from(tr.children) as HTMLElement[]
        // First cell is the row-label <th>; the rest are <td>s.
        rowCells.forEach((el, colIndex) => {
          const w = el.getBoundingClientRect().width
          const tag = (el.tagName === 'TH' ? 'TH' : 'TD') as 'TD' | 'TH'
          if (colIndex === 0) {
            rowLabelColumnWidths.push(w)
          } else {
            dataCellWidths.push({ rowIndex, colIndex, tag, width: w })
          }
        })
      })

      return {
        featureCount: headerCellWidths.length,
        rowLabelColumnWidths,
        headerCellWidths,
        dataCellWidths,
      }
    })

    report(result)
  } finally {
    await browser.close()
  }
}

function bucket(widths: number[]): Map<string, number> {
  const m = new Map<string, number>()
  for (const w of widths) {
    const key = w.toFixed(1)
    m.set(key, (m.get(key) ?? 0) + 1)
  }
  return m
}

function report(r: ProbeResult): void {
  console.log(`\nMatrix probe — ${r.featureCount} features\n`)

  // Row-label column.
  const rowLabelBuckets = bucket(r.rowLabelColumnWidths)
  if (rowLabelBuckets.size === 1) {
    const [key, count] = rowLabelBuckets.entries().next().value as [string, number]
    console.log(`  Row-label column: ${key} px ×${count} cells (expected ~176)`)
  } else {
    console.log(`  Row-label column: VARIANCE`)
    for (const [w, c] of rowLabelBuckets) console.log(`    ${w} px × ${c}`)
  }

  // Header row data cells.
  const headerBuckets = bucket(r.headerCellWidths)
  if (headerBuckets.size === 1) {
    const [key, count] = headerBuckets.entries().next().value as [string, number]
    console.log(`  Header data cells: ${key} px ×${count} (expected 40)`)
  } else {
    console.log(`  Header data cells: VARIANCE`)
    for (const [w, c] of headerBuckets) console.log(`    ${w} px × ${c}`)
  }

  // Data cells across the body.
  const dataWidths = r.dataCellWidths.map((c) => c.width)
  const dataBuckets = bucket(dataWidths)
  if (dataBuckets.size === 1) {
    const [key, count] = dataBuckets.entries().next().value as [string, number]
    console.log(`  Data cells:        ${key} px ×${count} (expected 40)`)
    console.log(`\n  ✓ No outliers — colgroup widths are honored.`)
  } else {
    console.log(`  Data cells: VARIANCE`)
    for (const [w, c] of dataBuckets) console.log(`    ${w} px × ${c}`)
    // Print outliers grouped by column.
    const sorted = Array.from(dataBuckets.entries()).sort((a, b) => Number(b[1]) - Number(a[1]))
    const dominant = Number(sorted[0][0])
    const outliers = r.dataCellWidths.filter((c) => Math.abs(c.width - dominant) > 0.1)
    const byCol = new Map<number, number[]>()
    for (const o of outliers) {
      const arr = byCol.get(o.colIndex) ?? []
      arr.push(Number(o.width.toFixed(1)))
      byCol.set(o.colIndex, arr)
    }
    console.log(`\n  Outlier columns (col index → distinct widths):`)
    for (const [col, widths] of [...byCol.entries()].sort((a, b) => a[0] - b[0])) {
      const distinct = [...new Set(widths)].sort()
      console.log(`    col ${col}: ${distinct.join(', ')} px`)
    }
  }
}

main().catch((err) => {
  console.error('Probe failed:', err)
  process.exit(1)
})
