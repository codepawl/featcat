import { expect, test } from './fixtures/test'
import { BACKEND_URL, FIXTURES_PARQUET_DIR } from './fixtures/constants'
import { resolve } from 'node:path'

const FIXTURE_PARQUET = resolve(FIXTURES_PARQUET_DIR, 'device_performance.parquet')

/** Cleanup helper — drops any source whose name starts with the given prefix
 *  so e2e-created sources don't leak between tests. The seeded fixtures
 *  (`device_performance`, `user_behavior_30d`) survive because they don't
 *  share the prefix.
 */
async function deleteSourcesWithPrefix(prefix: string): Promise<void> {
  const all: Array<{ name: string }> = await fetch(`${BACKEND_URL}/api/sources`).then((r) =>
    r.json(),
  )
  await Promise.all(
    all
      .filter((s) => s.name.startsWith(prefix))
      .map((s) =>
        fetch(`${BACKEND_URL}/api/sources/${encodeURIComponent(s.name)}`, { method: 'DELETE' }),
      ),
  )
}

test.describe('Sources', () => {
  test.afterEach(async () => {
    await deleteSourcesWithPrefix('e2e-')
  })

  test('lists pre-seeded sources and renders detail on click', async ({ page }) => {
    await page.goto('/sources')
    await expect(page.getByRole('heading', { name: /Data Sources|Nguồn dữ liệu/, level: 1 })).toBeVisible()

    // Both fixture sources are seeded by the worker fixture.
    await expect(page.getByText('device_performance', { exact: false }).first()).toBeVisible()
    await expect(page.getByText('user_behavior_30d', { exact: false }).first()).toBeVisible()

    // Click the device_performance row — detail panel should populate with
    // the source's metadata + extracted features.
    await page.getByText('device_performance', { exact: false }).first().click()
    await expect(page).toHaveURL(/\/sources\/device_performance$/)

    const main = page.getByRole('main')
    // FeatureSelector enumerates this fixture's columns under the detail
    // panel — `cpu_usage` is unique to FeatureSelector output (the row's
    // truncated path doesn't include column names), so this both proves the
    // detail panel rendered AND that features arrived from the API.
    await expect(main.getByText(/device_performance\.cpu_usage/).first()).toBeVisible()
  })

  test('add source via modal: appears in list and renders in detail', async ({ page }) => {
    await page.goto('/sources')

    await page.getByRole('button', { name: /Add source|Thêm nguồn/ }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    // Fill path. The name field auto-suggests from path basename when empty.
    await dialog.getByPlaceholder(/parquet|s3:/).fill(FIXTURE_PARQUET)
    // Then explicitly set our prefixed test name (override the suggestion).
    // The path is the only field with a placeholder containing 'parquet';
    // the name input has placeholder containing 'e.g.' (en) or 'vd:' (vi).
    await dialog.getByPlaceholder(/e\.g\.|vd:/).fill('e2e-added')

    // Disable scan-after so the test stays fast and deterministic.
    const scanAfter = dialog.getByRole('checkbox', { name: /Scan immediately|Quét ngay/ })
    if (await scanAfter.isChecked()) await scanAfter.click()

    await dialog.getByRole('button', { name: /^Add$|^Thêm$/ }).click()
    await expect(dialog).not.toBeVisible()

    // Row appears in the list, and clicking it lands on the detail URL.
    await expect(page.getByText('e2e-added', { exact: false }).first()).toBeVisible()
    await page.getByText('e2e-added', { exact: false }).first().click()
    await expect(page).toHaveURL(/\/sources\/e2e-added$/)
  })

  test('add modal disables submit when path is relative', async ({ page }) => {
    await page.goto('/sources')

    await page.getByRole('button', { name: /Add source|Thêm nguồn/ }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByPlaceholder(/parquet|s3:/).fill('relative/path.parquet')

    // Inline validation message + submit disabled.
    await expect(dialog.getByText(/Invalid path|Đường dẫn không hợp lệ/)).toBeVisible()
    const submit = dialog.getByRole('button', { name: /^Add$|^Thêm$/ })
    await expect(submit).toBeDisabled()
  })

  test('bulk scan two selected sources updates scan history', async ({ page }) => {
    // Pre-create two test sources so we can scan them together without
    // touching the seeded ones.
    for (const name of ['e2e-bulk-a', 'e2e-bulk-b']) {
      await fetch(`${BACKEND_URL}/api/sources`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, path: FIXTURE_PARQUET }),
      })
    }

    await page.goto('/sources')

    // Check both rows. The first checkbox sits inside the row; locate it
    // via the label's aria-label which we set on the row component.
    await page.getByLabel('Select e2e-bulk-a for bulk scan').check()
    await page.getByLabel('Select e2e-bulk-b for bulk scan').check()

    // Bulk-scan banner appears with the correct count, then the action button.
    await expect(page.getByText(/Scan 2 selected|Quét 2 đã chọn/)).toBeVisible()
    await page.getByRole('button', { name: /^Scan now$|^Quét ngay$/ }).first().click()

    // Once the bulk loop completes, the selection clears and both sources
    // record a scan log; verify by hitting the API directly.
    await expect(page.getByText(/Scan 2 selected|Quét 2 đã chọn/)).not.toBeVisible({ timeout: 15_000 })

    for (const name of ['e2e-bulk-a', 'e2e-bulk-b']) {
      const logs = await fetch(`${BACKEND_URL}/api/sources/${name}/scan-logs`).then((r) =>
        r.json(),
      )
      expect(Array.isArray(logs)).toBeTruthy()
      // One log row per scan — the source was created above without scan-after.
      expect(logs.length).toBeGreaterThanOrEqual(1)
      expect(logs[0].status).toBe('success')
    }
  })
})
