import { expect, test } from './fixtures/test'

test.describe('Export modal', () => {
  test('opens from Features after bulk select and shows format options', async ({ page }) => {
    await page.goto('/features')

    const firstCheckbox = page.getByRole('main').locator('input[type="checkbox"]').nth(1)
    await firstCheckbox.check()

    const exportBtn = page.getByRole('button', { name: /Export Selected/i })
    await expect(exportBtn).toBeVisible()
    await exportBtn.click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    await expect(dialog.getByText('Format')).toBeVisible()
    await expect(dialog.getByLabel(/Parquet/)).toBeChecked()
    await expect(dialog.getByText('Join column')).toBeVisible()
    await expect(dialog.getByText(/Features to include/)).toBeVisible()

    await dialog.getByLabel('CSV').check()
    await expect(dialog.getByLabel('CSV')).toBeChecked()
  })
})
