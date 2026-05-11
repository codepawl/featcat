import { expect, test } from './fixtures/test'

test.describe('Audit log', () => {
  test('renders filter UI and shows empty state on a fresh seed', async ({ page }) => {
    await page.goto('/audit')

    await expect(page.getByRole('heading', { name: 'Audit Log', level: 1 })).toBeVisible()
    await expect(page.getByText(/All metadata changes/i)).toBeVisible()

    const days = page.getByRole('combobox').nth(0)
    await days.selectOption('30')
    await expect(days).toHaveValue('30')

    const types = page.getByRole('combobox').nth(2)
    await types.selectOption('doc')
    await expect(types).toHaveValue('doc')

    await expect(page.getByText(/\d+ changes/).first()).toBeVisible()
  })

  test('reflects edits made via API after refresh', async ({ page, apiUrl }) => {
    await fetch(
      `${apiUrl}/api/features/by-name?name=${encodeURIComponent('device_performance.cpu_usage')}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ owner: 'audit-test-user' }),
      },
    )

    await page.goto('/audit')
    await expect(page.getByRole('heading', { name: 'Audit Log' })).toBeVisible()
  })
})
