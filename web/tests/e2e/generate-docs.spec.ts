import { expect, test } from './fixtures/test'

test.describe('Generate docs flow', () => {
  test('starts batch generation with AI mocked', async ({ page, mockAi }) => {
    const jobId = 'mock-job-1'
    await mockAi.mockGenerateDocsBatch(jobId)
    await mockAi.mockBatchStatus(jobId, {
      status: 'success',
      total: 14,
      processed: 14,
      succeeded: 14,
      failed: 0,
      results: [],
    })

    await page.goto('/features')
    await expect(page.getByRole('heading', { name: 'Features', level: 1 })).toBeVisible()

    const generateBtn = page.getByRole('button', { name: /Generate docs/i }).first()
    await expect(generateBtn).toBeVisible()
    await generateBtn.click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    await dialog.getByLabel(/All features/).check()

    await dialog.getByRole('button', { name: /Generate \d+ Docs/ }).click()

    expect(mockAi.callCount('/api/docs/generate-batch')).toBeGreaterThanOrEqual(1)
  })
})
