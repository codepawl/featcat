import { expect, test } from './fixtures/test'

test.describe('Search', () => {
  test('returns results for a TF-IDF query and toggles a source facet', async ({ page }) => {
    await page.goto('/search')

    await expect(page.getByRole('heading', { name: 'Search', level: 1 })).toBeVisible()

    const input = page.getByPlaceholder(/Search features/i)
    await input.fill('device')
    await input.press('Enter')

    await expect(page.getByText(/results? for/i)).toBeVisible()
    await expect(
      page.getByRole('main').getByText(/device_performance\./).first(),
    ).toBeVisible()

    const userBehaviorFacet = page
      .getByRole('main')
      .getByRole('button', { name: /user_behavior_30d/ })
    if (await userBehaviorFacet.count()) {
      await userBehaviorFacet.first().click()
    }
  })

  test('shows empty-prompt when no query', async ({ page }) => {
    await page.goto('/search')
    await expect(page.getByText(/Type a query to search/i)).toBeVisible()
  })
})
