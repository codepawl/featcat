import { expect, test } from './fixtures/test'

const FEATURE_NAME_PATTERN = /device_performance\.|user_behavior_30d\./

const docWithGeneratedAt = (generatedAt: string, shortDesc: string) => ({
  short_description: shortDesc,
  long_description: 'Long description for E2E.',
  expected_range: null,
  potential_issues: null,
  generated_at: generatedAt,
  model_used: 'mock-model',
  hints_used: null,
  context_features: null,
})

test.describe('feature detail merged sections', () => {
  test('shows Specification before Data Profile and updates AI badge on regenerate', async ({ page }) => {
    let regenerated = false
    let generateCount = 0

    // React StrictMode double-fires mount effects, so the docs/by-name endpoint
    // gets called twice on initial render. Drive the mock by regenerate state
    // (not by call count) so all pre-regenerate fetches return the same payload.
    await page.route('**/api/docs/by-name**', async (route) => {
      const payload = regenerated
        ? docWithGeneratedAt('2026-05-14T10:00:00Z', 'Refreshed AI doc')
        : docWithGeneratedAt('2024-01-01T00:00:00Z', 'Original AI doc')
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(payload),
      })
    })

    // Override mockAiDefault's 503 on /api/docs/generate with a success response.
    await page.route('**/api/docs/generate', async (route) => {
      generateCount += 1
      regenerated = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      })
    })

    await page.goto('/features')
    await expect(page.getByRole('heading', { name: 'Features', level: 1 })).toBeVisible()

    const cell = page.getByRole('main').getByText(FEATURE_NAME_PATTERN).first()
    await expect(cell).toBeVisible()
    await cell.click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    const specHeading = dialog.getByRole('heading', { name: /specification/i })
    const profileHeading = dialog.getByRole('heading', { name: /data profile/i })
    await expect(specHeading).toBeVisible()
    await expect(profileHeading).toBeVisible()

    const specBox = await specHeading.boundingBox()
    const profileBox = await profileHeading.boundingBox()
    expect(specBox).not.toBeNull()
    expect(profileBox).not.toBeNull()
    expect(specBox!.y).toBeLessThan(profileBox!.y)

    // The Generation Hints section sits below Data Profile (it's metadata about the AI output).
    const hintsHeading = dialog.getByRole('heading', { name: /generation hints/i })
    await expect(hintsHeading).toBeVisible()
    const hintsBox = await hintsHeading.boundingBox()
    expect(hintsBox).not.toBeNull()
    expect(profileBox!.y).toBeLessThan(hintsBox!.y)

    // AI badge renders with original short description visible.
    await expect(dialog.getByText(/AI-generated/)).toBeVisible()
    await expect(dialog.getByText('Original AI doc')).toBeVisible()

    // Click Regenerate; handler refetches docs and updates the badge.
    await dialog.getByRole('button', { name: /regenerate/i }).click()

    await expect.poll(() => generateCount, { timeout: 5_000 }).toBeGreaterThan(0)
    await expect(dialog.getByText('Refreshed AI doc')).toBeVisible()
    await expect(dialog.getByText(/AI-generated/)).toBeVisible()
  })

  test('Data Profile shows empty-state CTA when documentation has never been generated', async ({ page }) => {
    await page.route('**/api/docs/by-name**', async (route) => {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'not found' }),
      })
    })

    await page.goto('/features')
    await expect(page.getByRole('heading', { name: 'Features', level: 1 })).toBeVisible()

    const cell = page.getByRole('main').getByText(FEATURE_NAME_PATTERN).first()
    await cell.click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText('No documentation yet')).toBeVisible()
    await expect(dialog.getByText(/AI will analyze stats, hints, and lineage/i)).toBeVisible()
    await expect(dialog.getByRole('button', { name: /^Generate$/ })).toBeVisible()
  })

  test('Specification section renders independently when documentation fetch fails', async ({ page }) => {
    await page.route('**/api/docs/by-name**', async (route) => {
      await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'boom' }) })
    })

    await page.goto('/features')
    const cell = page.getByRole('main').getByText(FEATURE_NAME_PATTERN).first()
    await cell.click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    // Specification section heading is still rendered even though the docs fetch failed.
    await expect(dialog.getByRole('heading', { name: /specification/i })).toBeVisible()
    // Data Profile section also still renders (just shows the empty state on error).
    await expect(dialog.getByRole('heading', { name: /data profile/i })).toBeVisible()
  })
})
