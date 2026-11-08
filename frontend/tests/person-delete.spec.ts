import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
const root = resolve(import.meta.dirname, '../..')

test('身份批量删除：全选、搜索清空、取消、失败重试与实际删除', async ({ page }) => {
  test.skip(
    process.env.LUMIFACE_TEST_DELETE_ISOLATED !== '1',
    '只允许显式启用的隔离数据库运行删除测试',
  )
  // Refuse to run on an existing gallery, even if the isolation flag was set by mistake.
  expect((await (await page.request.get('/api/person')).json()).data).toEqual([])
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const identities = []
  for (let i = 1; i <= 3; i++) {
    const response = await page.request.post('/api/person/register', {
      timeout: 180000,
      multipart: {
        name: `批量删除测试${i}`,
        capture_id: `delete-browser-${i}`,
        files: {
          name: 'ref.png',
          mimeType: 'image/png',
          buffer: execFileSync(root + '/.venv/bin/python', [
            '-c',
            'import sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); names=sorted(n for n in z.namelist() if "/gallery/" in n); sys.stdout.buffer.write(z.read(names[int(sys.argv[2])*2]))',
            root + '/datasets/lfw_120_demo.zip',
            String(i - 1),
          ]),
        },
      },
    })
    expect(response.status(), await response.text()).toBe(200)
    identities.push((await response.json()).data)
  }
  await page.goto('/persons')
  const rows = page.locator('.el-table__body-wrapper tbody tr')
  const bulk = page.getByRole('button', { name: /^批量删除/ })
  await expect(rows).toHaveCount(3)
  for (let i = 0; i < 3; i++)
    await expect(rows.nth(i).locator('td').nth(1)).toHaveText(String(i + 1))
  await expect(bulk).toBeDisabled()
  await rows.nth(0).locator('label.el-checkbox').click()
  await expect(bulk).toHaveText('批量删除（1）')
  await page.getByPlaceholder('搜索姓名').fill('批量删除测试3')
  await expect(rows).toHaveCount(1)
  await expect(rows.locator('td').nth(1)).toHaveText('1')
  await expect(page.getByText('已选择 0 个身份', { exact: false })).toBeVisible()
  await expect(bulk).toBeDisabled()
  await page.getByPlaceholder('搜索姓名').fill('')
  await expect(rows).toHaveCount(3)
  const header = page.locator('.el-table__header-wrapper label.el-checkbox')
  await header.click()
  await expect(bulk).toHaveText('批量删除（3）')
  await header.click()
  await expect(bulk).toBeDisabled()
  await rows.nth(0).locator('label.el-checkbox').click()
  await rows.nth(1).locator('label.el-checkbox').click()
  const mutations: string[] = []
  page.on('request', (r) => {
    if (r.url().endsWith('/api/person/batch-delete')) mutations.push(r.postData() || '')
  })
  await bulk.click()
  const confirm = page.getByRole('dialog', { name: '批量删除身份', exact: true })
  await expect(confirm).toContainText('所选 2 个身份')
  await expect(confirm).toContainText('无法恢复')
  await expect(confirm).toContainText('下载的演示包和原始照片保留')
  await confirm.getByRole('button', { name: '取消', exact: true }).click()
  await expect(confirm).toBeHidden()
  await expect(rows).toHaveCount(3)
  expect(mutations).toEqual([])
  // An explicit failure fixture verifies that errors keep the selection and do not claim success.
  await page.route('**/api/person/batch-delete', (route) =>
    route.fulfill({
      status: 409,
      contentType: 'application/json',
      body: JSON.stringify({ data: null, message: '测试错误：请刷新列表后重新选择' }),
    }),
  )
  await bulk.click()
  await confirm.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(page.locator('.el-message--error')).toContainText('测试错误：请刷新列表后重新选择')
  await expect(rows).toHaveCount(3)
  await expect(bulk).toHaveText('批量删除（2）')
  await expect(page.locator('.el-message--success')).toHaveCount(0)
  await page.unroute('**/api/person/batch-delete')
  await bulk.click()
  await confirm.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(rows).toHaveCount(1)
  await expect(rows).toContainText('批量删除测试3')
  await expect(rows.locator('td').nth(1)).toHaveText('1')
  await expect(page.getByText('已选择 0 个身份', { exact: true })).toBeVisible()
  await expect(bulk).toBeDisabled()
  const remaining = (await (await page.request.get('/api/person')).json()).data
  expect(remaining.map((p: any) => p.id)).toEqual([identities[2].id])
  expect(mutations.map((payload) => JSON.parse(payload).person_ids)).toEqual([
    [identities[0].id, identities[1].id],
    [identities[0].id, identities[1].id],
  ])
  // The original single-person action remains usable after a batch deletion.
  await rows.getByRole('button', { name: '删除', exact: true }).click()
  await page
    .getByRole('dialog', { name: '删除身份', exact: true })
    .getByRole('button', { name: '确认删除', exact: true })
    .click()
  await expect(rows).toHaveCount(0)
  expect((await (await page.request.get('/api/person')).json()).data).toEqual([])
  expect(errors).toEqual([])
})
