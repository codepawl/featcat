import { expect, test } from './fixtures/test'

test.describe('Features list', () => {
  test('renders rows from seeded backend and filters by source', async ({ page }) => {
    await page.goto('/features')

    await expect(page.getByRole('heading', { name: 'Features', level: 1 })).toBeVisible()

    const main = page.getByRole('main')
    await expect(main.getByText(/device_performance\./).first()).toBeVisible()
    await expect(main.getByText(/user_behavior_30d\./).first()).toBeVisible()

    const sourceSelect = main.getByRole('combobox').first()
    await sourceSelect.selectOption('device_performance')

    await expect(main.getByText(/device_performance\./).first()).toBeVisible()
    await expect(main.getByText(/user_behavior_30d\./)).toHaveCount(0)

    await sourceSelect.selectOption('')
    await expect(main.getByText(/user_behavior_30d\./).first()).toBeVisible()
  })

  test('opens feature detail modal on row click', async ({ page }) => {
    await page.goto('/features')

    // VirtualizedTable rows are divs with cursor-pointer + onClick. Click the
    // cell containing the feature name so the click bubbles to the row's onClick.
    const cell = page
      .getByRole('main')
      .getByText(/device_performance\.|user_behavior_30d\./)
      .first()
    await expect(cell).toBeVisible()
    await cell.click()

    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByRole('dialog').getByText('Metadata').first()).toBeVisible()
  })
})
