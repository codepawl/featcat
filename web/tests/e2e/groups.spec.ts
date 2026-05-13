import { expect, test } from './fixtures/test'
import { addMembers, createGroup } from './fixtures/seed'

test.describe('Groups', () => {
  test('create group via UI then add members', async ({ page }) => {
    await page.goto('/groups')
    await expect(page.getByRole('heading', { name: 'Feature Groups', level: 1 })).toBeVisible()

    await page.getByRole('button', { name: /New Group/ }).click()
    const createDialog = page.getByRole('dialog')
    await expect(createDialog).toBeVisible()

    await createDialog.getByPlaceholder('Group name').fill('cpu-pack')
    await createDialog.getByRole('button', { name: 'Create' }).click()

    await expect(page.getByText('cpu-pack', { exact: false })).toBeVisible()

    await page.getByText('cpu-pack', { exact: false }).first().click()

    await page.getByRole('button', { name: /Add Features/ }).click()
    const addDialog = page.getByRole('dialog')
    await expect(addDialog).toBeVisible()

    await addDialog.getByText(/device_performance\.cpu_usage/).first().click()
    await addDialog.getByRole('button', { name: /Add \(1\)/ }).click()

    await expect(addDialog).not.toBeVisible()
    await expect(
      page.getByRole('main').getByText('device_performance.cpu_usage'),
    ).toBeVisible()
  })

  test('group tabs (members, health, monitoring, docs) render', async ({ page, apiUrl }) => {
    await createGroup({ name: 'tabs-group', description: '' })
    await addMembers('tabs-group', ['device_performance.cpu_usage', 'device_performance.memory_usage'])

    const r = await fetch(`${apiUrl}/api/groups/tabs-group`).then((x) => x.json())
    expect(r.member_count).toBe(2)

    await page.goto('/groups')
    await page.getByText('tabs-group', { exact: false }).first().click()

    await expect(page.getByRole('main').getByRole('tab', { name: /Members \(2\)/ })).toBeVisible()

    await page.getByRole('main').getByRole('tab', { name: /Health/ }).click()
    await page.getByRole('main').getByRole('tab', { name: /Monitoring/ }).click()
    await page.getByRole('main').getByRole('tab', { name: /Docs/ }).click()
    await page.getByRole('main').getByRole('tab', { name: /Members/ }).click()
    await expect(page.getByRole('main').getByText('device_performance.cpu_usage')).toBeVisible()
  })
})
