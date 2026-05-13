import { expect, test } from './fixtures/test'

test.describe('Jobs', () => {
  test('lists default scheduled jobs and exposes per-job actions', async ({ page }) => {
    await page.goto('/jobs')

    await expect(page.getByRole('heading', { name: 'Jobs', level: 1 })).toBeVisible()

    await expect(page.getByText(/monitor_check/i).first()).toBeVisible()
    await expect(page.getByText(/doc_generate/i).first()).toBeVisible()
    await expect(page.getByText(/source_scan/i).first()).toBeVisible()
    await expect(page.getByText(/baseline_refresh/i).first()).toBeVisible()

    const editScheduleBtn = page.getByRole('button', { name: /Edit Schedule/ }).first()
    await expect(editScheduleBtn).toBeVisible()
    await editScheduleBtn.click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole('button', { name: /Cancel/ })).toBeVisible()
    await dialog.getByRole('button', { name: /Cancel/ }).click()
    await expect(dialog).not.toBeVisible()
  })

  test('Run Now triggers scheduler runJob', async ({ page }) => {
    let triggered = false
    await page.route('**/api/scheduler/jobs/*/run', async (route) => {
      triggered = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'queued', job_name: 'mock', triggered_at: new Date().toISOString() }),
      })
    })

    await page.goto('/jobs')

    const runBtn = page.getByRole('button', { name: /Run Now/ }).first()
    await runBtn.click()

    await expect.poll(() => triggered).toBe(true)
  })
})
