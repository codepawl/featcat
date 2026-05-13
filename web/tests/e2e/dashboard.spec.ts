import { expect, test } from './fixtures/test'

test.describe('Dashboard', () => {
  test('loads with metrics and source stats', async ({ page, apiUrl }) => {
    const health = await fetch(`${apiUrl}/api/health`).then((r) => r.json())
    expect(health.status).toBeTruthy()

    await page.goto('/')

    await expect(page.getByRole('heading', { name: 'Dashboard', level: 1 })).toBeVisible()

    const main = page.getByRole('main')
    await expect(main.getByText('Features', { exact: true })).toBeVisible()
    await expect(main.getByText('Sources', { exact: true })).toBeVisible()
    await expect(main.getByText('Doc Coverage')).toBeVisible()
  })
})
