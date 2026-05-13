import { expect, test } from './fixtures/test'

test.describe('Similarity graph', () => {
  test('page renders with title, threshold slider, and SVG canvas', async ({ page }) => {
    await page.goto('/similarity')

    await expect(page.getByRole('heading', { name: /Feature Similarity/i })).toBeVisible()
    await expect(page.getByText(/Similarity threshold/)).toBeVisible()

    await expect(page.getByRole('main').locator('svg').first()).toBeVisible()
  })

  test('threshold slider triggers a refetch', async ({ page, apiUrl }) => {
    await page.goto('/similarity')

    const slider = page.getByRole('slider')
    await expect(slider).toBeVisible()

    let calls = 0
    await page.route(`**/api/features/similarity-graph*`, async (route) => {
      calls++
      const r = await fetch(`${apiUrl}${route.request().url().split('/api')[1]}`)
      await route.fulfill({ status: r.status, body: await r.text(), contentType: 'application/json' })
    })

    await slider.fill('0.7')

    await expect.poll(() => calls).toBeGreaterThan(0)
  })
})
