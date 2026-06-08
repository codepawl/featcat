import { expect, test } from './fixtures/test'
import { seedRegistryCatalog } from './fixtures/seed'

test.describe('Registry taxonomy', () => {
  test.beforeEach(async () => {
    await seedRegistryCatalog()
  })

  test('business metrics list supports taxonomy filters and detail mapping', async ({ page }) => {
    await page.goto('/business-metrics')

    await expect(page.getByRole('heading', { name: /Business Metrics|Chỉ số nghiệp vụ/, level: 1 })).toBeVisible()
    const main = page.getByRole('main')

    await expect(main.getByText('bad_signal_days_7d')).toBeVisible()
    await expect(main.getByText('payment_delay_count_30d')).toBeVisible()

    await page.getByRole('combobox', { name: /All domains|All metrics domains/i }).selectOption('billing')
    await expect(main.getByText('pay_delay_30d')).toBeVisible()
    await expect(main.getByText('bad_signal_7d')).toHaveCount(0)

    await main.getByText('pay_delay_30d', { exact: true }).click()
    const detail = page.getByTestId('business-metric-detail')
    await expect(detail).toBeVisible()
    await expect(detail.getByText('payment_delay_count_30d')).toBeVisible()
    await expect(detail.getByText('pay_delay_30d')).toBeVisible()
    await expect(detail.getByText('contract_id')).toBeVisible()
    await expect(detail.getByText('user_behavior_30d.complaint_count')).toBeVisible()
  })

  test('entity, relationship, feature view, and feature set pages render the registry flow', async ({ page }) => {
    await page.goto('/entities')
    await expect(page.getByRole('heading', { name: /Entities|Thực thể/, level: 1 })).toBeVisible()
    await expect(page.getByText('customer', { exact: true })).toBeVisible()
    await expect(page.getByText('contract', { exact: true })).toBeVisible()

    await page.getByText('contract', { exact: true }).first().click()
    await expect(page).toHaveURL(/\/entities\/contract$/)
    await expect(page.getByText('billing.contracts')).toBeVisible()
    await expect(page.getByRole('link', { name: /Open relationships|Mở quan hệ/i })).toBeVisible()

    await page.goto('/entity-relationships')
    await expect(page.getByRole('heading', { name: /Relationships|Quan hệ/, level: 1 })).toBeVisible()
    await page.getByPlaceholder(/Left entity|Thực thể trái/i).fill('contract')
    await expect(page.getByText('contract_has_devices', { exact: true })).toBeVisible()
    await page.getByText('contract_has_devices', { exact: true }).first().click()
    await expect(page).toHaveURL(/\/entity-relationships\/contract_has_devices$/)
    await expect(page.getByText('contract_id → contract_id')).toBeVisible()

    await page.goto('/feature-views')
    await expect(page.getByRole('heading', { name: /Feature Views|Feature Views/, level: 1 })).toBeVisible()
    await expect(page.getByText('contract_view', { exact: true })).toBeVisible()
    await page.getByText('contract_view', { exact: true }).first().click()
    await expect(page).toHaveURL(/\/feature-views\/contract_view$/)
    await expect(page.getByText('contract_has_devices')).toBeVisible()
    await expect(page.getByText('device_performance.error_count')).toBeVisible()

    await page.goto('/feature-sets')
    await expect(page.getByRole('heading', { name: /Feature Sets|Feature Sets/, level: 1 })).toBeVisible()
    await expect(page.getByText('cust_churn_set', { exact: true })).toBeVisible()
    await page.getByText('cust_churn_set', { exact: true }).first().click()
    await expect(page).toHaveURL(/\/feature-sets\/cust_churn_set$/)
    await expect(page.getByText('avg(device)->customer via contract')).toBeVisible()
    await expect(page.getByText(/high leakage risk/i)).toBeVisible()
    await expect(page.getByRole('link', { name: 'device_performance.cpu_usage' })).toHaveCount(2)
  })

  test('lineage graph includes business metrics and feature sets', async ({ page }) => {
    await page.goto('/lineage')

    await expect(page.getByRole('heading', { name: /Feature Lineage|Lineage/, level: 1 })).toBeVisible()
    await expect(page.getByPlaceholder(/Search nodes|Tìm node/i)).toBeVisible()
    await expect(page.getByText('contract_view')).toBeVisible()
    await expect(page.getByText('cust_churn_set')).toBeVisible()
    await expect(page.getByText('bad_signal_7d')).toBeVisible()

    await page.getByPlaceholder(/Search nodes|Tìm node/i).fill('cust_churn_set')
    await expect(page.getByText('cust_churn_set')).toBeVisible()
  })
})
