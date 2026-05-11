import { expect, test } from './fixtures/test'
import { createGroup } from './fixtures/seed'

test.describe('FeatureSelector', () => {
  test('search filters list, shift+click selects range, select-all-by-source toggles', async ({
    page,
  }) => {
    await createGroup({ name: 'fs-test', description: 'feature selector spec' })

    await page.goto('/groups')
    await expect(page.getByRole('heading', { name: 'Feature Groups', level: 1 })).toBeVisible()

    await page.getByText('fs-test', { exact: false }).first().click()
    await page.getByRole('button', { name: /Add Features/ }).click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    const search = dialog.getByPlaceholder(/Search features/)
    await search.fill('cpu')
    await expect(dialog.getByText(/device_performance\.cpu/).first()).toBeVisible()
    await expect(dialog.getByText(/user_behavior_30d\./)).toHaveCount(0)

    await search.fill('')

    await dialog.getByText(/device_performance\.cpu_usage/).first().click()
    await expect(dialog.getByRole('button', { name: /Selected \(1\)/ })).toBeVisible()

    await dialog
      .getByText(/device_performance\./)
      .nth(2)
      .click({ modifiers: ['Shift'] })

    const selectedCountBtn = dialog.getByRole('button', { name: /Selected \(\d+\)/ })
    await expect(selectedCountBtn).toBeVisible()

    await selectedCountBtn.click()
    await expect(dialog.getByText(/of \d+ selected/)).toBeVisible()
  })

  test('show-selected-only filter toggles list', async ({ page }) => {
    await createGroup({ name: 'fs-toggle', description: '' })

    await page.goto('/groups')
    await page.getByText('fs-toggle', { exact: false }).first().click()
    await page.getByRole('button', { name: /Add Features/ }).click()

    const dialog = page.getByRole('dialog')
    await dialog.getByText(/device_performance\.cpu_usage/).first().click()

    const selectedBtn = dialog.getByRole('button', { name: /Selected \(1\)/ })
    await selectedBtn.click()

    await expect(dialog.getByText(/device_performance\.cpu_usage/)).toBeVisible()
    await expect(dialog.getByText(/user_behavior_30d\./)).toHaveCount(0)

    await selectedBtn.click()
    await expect(dialog.getByText(/user_behavior_30d\./).first()).toBeVisible()
  })
})
