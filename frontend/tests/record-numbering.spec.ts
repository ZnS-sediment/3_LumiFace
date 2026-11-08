import { test, expect } from '@playwright/test'
test.describe.configure({ timeout: 60000 })

// API fixtures keep deletion checks independent of the user's real gallery and history.
test('测试记录删除后连续编号，详情、排序与刷新保持一致', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const makeRecord = (id: number, name: string) => ({
    id, name, status: 'completed', progress: 1, total: 1,
    config: { methods: ['original'], dataset: { name } }, summary: {},
  })
  let records = [makeRecord(15, '光照不均'), makeRecord(9, '逆光'), makeRecord(4, '低照度')]
  const deleted: number[] = []
  await page.addInitScript(() => {
    if (!localStorage.getItem('lumiface-experiment-order'))
      localStorage.setItem('lumiface-experiment-order', 'asc')
  })
  await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
    const path = new URL(route.request().url()).pathname
    let data: unknown = []
    if (path === '/api/experiment') data = records
    else if (/^\/api\/experiment\/\d+$/.test(path)) {
      const id = Number(path.split('/').pop())
      if (route.request().method() === 'DELETE') {
        deleted.push(id)
        records = records.filter((record) => record.id !== id)
        data = { id }
      } else data = records.find((record) => record.id === id)
    }
    await route.fulfill({ json: { data } })
  })
  await page.goto('/experiments')
  await page.getByRole('tab', { name: '历史记录', exact: true }).click()
  const history = page.locator('.experiment-history')
  const rows = history.locator('.el-table__body-wrapper tbody tr')
  const numbers = () => rows.locator('td:first-child').allTextContents()
  const results = page.locator('.current-experiment')
  const remove = async (row: ReturnType<typeof rows.nth>) => {
    await row.getByRole('button', { name: '删除', exact: true }).click()
    await page.getByRole('dialog', { name: '删除测试', exact: true })
      .getByRole('button', { name: '确定', exact: true }).click()
  }
  await expect.poll(numbers).toEqual(['1', '2', '3'])
  await rows.nth(2).getByRole('button', { name: '查看结果', exact: true }).click()
  await expect(results).toContainText('编号 3 · 1 张图片')
  await expect(page).toHaveURL(/run=15/)
  await page.getByRole('tab', { name: '历史记录', exact: true }).click()
  await remove(rows.nth(1))
  await expect.poll(numbers).toEqual(['1', '2'])
  await expect(rows.nth(1)).toContainText('光照不均')
  await page.getByRole('tab', { name: '测试结果', exact: true }).click()
  await expect(results).toContainText('编号 2 · 1 张图片')
  await expect(results.getByRole('heading', { level: 2 })).toContainText('光照不均')
  await page.getByRole('tab', { name: '历史记录', exact: true }).click()
  await history.locator('.history-sort .el-select__wrapper').click()
  await page.getByRole('option', { name: '降序（从大到小）', exact: true }).click()
  await expect.poll(numbers).toEqual(['2', '1'])
  await expect(rows.first()).toContainText('光照不均')
  await remove(rows.first())
  await expect.poll(numbers).toEqual(['1'])
  await expect(rows.first()).toContainText('低照度')
  await remove(rows.first())
  await expect(rows).toHaveCount(0)
  await expect(history).toContainText('暂无测试记录')
  records = [makeRecord(42, '新测试')]
  await history.getByRole('button', { name: '刷新', exact: true }).click()
  await expect.poll(numbers).toEqual(['1'])
  await rows.first().getByRole('button', { name: '查看结果', exact: true }).click()
  await expect(results).toContainText('编号 1 · 1 张图片')
  await expect(page).toHaveURL(/run=42/)
  await page.reload()
  await expect(results).toContainText('编号 1 · 1 张图片')
  await expect(results.getByRole('heading', { level: 2 })).toContainText('新测试')
  expect(deleted).toEqual([9, 15, 4])
  expect(errors).toEqual([])
})

test('身份库单人和批量删除后自动重新编号', async ({ page }) => {
  let people = [7, 20, 42].map((id) => ({
    id, name: '身份' + id, sample_count: 2, note: '', created_at: '2026-11-01T10:00:00',
  }))
  const singleDeletes: number[] = []
  const batchDeletes: number[][] = []
  await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    let data: unknown = []
    if (path === '/api/person') data = people
    else if (path === '/api/person/batch-delete') {
      const ids: number[] = request.postDataJSON().person_ids
      batchDeletes.push(ids)
      people = people.filter((person) => !ids.includes(person.id))
      data = { cleanup: { pending_files: 0 } }
    } else if (request.method() === 'DELETE' && /^\/api\/person\/\d+$/.test(path)) {
      const id = Number(path.split('/').pop())
      singleDeletes.push(id)
      people = people.filter((person) => person.id !== id)
      data = { cleanup: { pending_files: 0 } }
    }
    await route.fulfill({ json: { data } })
  })
  await page.goto('/persons')
  const rows = page.locator('.el-table__body-wrapper tbody tr')
  const numbers = () => rows.locator('td:nth-child(2)').allTextContents()
  await expect.poll(numbers).toEqual(['1', '2', '3'])
  await rows.first().getByRole('button', { name: '删除', exact: true }).click()
  await page.getByRole('dialog', { name: '删除身份', exact: true })
    .getByRole('button', { name: '确认删除', exact: true }).click()
  await expect.poll(numbers).toEqual(['1', '2'])
  await expect(rows.first()).toContainText('身份20')
  await page.reload()
  await expect.poll(numbers).toEqual(['1', '2'])
  await page.locator('.el-table__header-wrapper label.el-checkbox').click()
  await page.getByRole('button', { name: /^批量删除/ }).click()
  await page.getByRole('dialog', { name: '批量删除身份', exact: true })
    .getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(rows).toHaveCount(0)
  await expect(page.locator('.person-selection')).toContainText('已选择 0 个身份')
  expect(singleDeletes).toEqual([7])
  expect(batchDeletes).toEqual([[20, 42]])
})
