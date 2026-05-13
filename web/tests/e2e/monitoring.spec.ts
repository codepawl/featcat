import { expect, test } from './fixtures/test'

test.describe('Monitoring', () => {
  test('page renders header and refresh-baseline confirmation modal', async ({ page }) => {
    await page.goto('/monitoring')

    await expect(page.getByRole('heading', { name: 'Monitoring', level: 1 })).toBeVisible()

    const refreshBaseline = page.getByRole('button', { name: /Refresh Baseline/i })
    await expect(refreshBaseline).toBeVisible()
    await refreshBaseline.click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole('button', { name: /Cancel/ })).toBeVisible()
    await dialog.getByRole('button', { name: /Cancel/ }).click()
    await expect(dialog).not.toBeVisible()
  })

  test('baseline POST then drift check renders drift table or empty hint', async ({
    page,
    apiUrl,
  }) => {
    await fetch(`${apiUrl}/api/monitor/baseline`, { method: 'POST' })

    await page.goto('/monitoring')
    await expect(page.getByRole('heading', { name: 'Monitoring' })).toBeVisible()

    await expect(
      page.getByText(/Healthy|Warnings|Critical/i).first(),
    ).toBeVisible()
  })
})
