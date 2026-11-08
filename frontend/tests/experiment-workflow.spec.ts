import { test, expect } from '@playwright/test'
import { mkdtemp, mkdir, writeFile, rm, readFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
test.describe.configure({ timeout: 60000 })
const makeRecord = (id: number, name: string, status = 'completed') => ({
  id, name, status, progress: status === 'completed' ? 10 : 2, total: 10,
  config: { methods: ['original'], dataset: { name } }, summary: {},
})

test('1200张目录快速预览、跨页标注和完整提交', async ({ page }) => {
  const folder = await mkdtemp(join(tmpdir(), 'lumiface-query-'))
  const png = process.env.LUMIFACE_BATCH_IMAGE ? await readFile(process.env.LUMIFACE_BATCH_IMAGE) : Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jP1sAAAAASUVORK5CYII=', 'base64')
  const people = Array.from({ length: 400 }, (_, index) => ({ id: index + 1, name: 'LFW_Person_' + String(index).padStart(3, '0') }))
  let record: any = null
  let labels: any = null
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
    const path = new URL(route.request().url()).pathname
    let data: unknown = []
    if (path === '/api/person') data = people
    else if (path === '/api/experiment') data = record ? [record] : []
    else if (path === '/api/experiment/images') {
      const body = route.request().postDataBuffer()!.toString('utf8')
      const match = body.match(/name="labels"\r\n\r\n([\s\S]*?)\r\n--/)
      labels = JSON.parse(match![1])
      record = { ...makeRecord(9, '1200张测试', 'queued'), progress: 0, total: labels.items.length * labels.methods.length,
        config: { methods: labels.methods, dataset: { name: '1200张测试' } } }
      data = record
    } else if (path === '/api/experiment/9') data = record
    await route.fulfill({ json: { data } })
  })
  try {
    for (const person of people) {
      const dir = join(folder, '03_低照度_Gamma', person.name)
      await mkdir(dir, { recursive: true })
      await Promise.all([1, 2, 3].map((i) => writeFile(join(dir, i + '.png'), png)))
    }
    await page.goto('/experiments')
    const form = page.locator('.image-batch-card')
    await expect(form.getByRole('button', { name: '选择查询目录', exact: true })).toBeEnabled()
    const started = Date.now()
    await form.getByLabel('选择测试图片目录', { exact: true }).setInputFiles(folder)
    await expect(form.getByRole('status')).toHaveText('已选择 1200 张')
    const elapsed = Date.now() - started
    const rows = form.locator('.image-batch-inputs .el-table__body-wrapper tbody tr')
    await expect(rows).toHaveCount(25)
    await expect(rows.first().locator('td').first()).toHaveText('1')
    await expect(rows.last().locator('td').first()).toHaveText('25')
    await expect(form.getByAltText('测试图片预览')).toHaveCount(25)
    console.log(`1200张/400人目录：读取到可操作预览 ${elapsed}ms，渲染25行`)
    expect(elapsed).toBeLessThan(10000)
    const pagination = form.getByLabel('测试图片分页')
    await pagination.locator('.btn-next').click()
    await expect(rows.first().locator('td').first()).toHaveText('26')
    await rows.first().getByRole('combobox', { name: /^真实身份/ }).fill('未知')
    await page.getByRole('option', { name: '未知身份（不在身份库）', exact: true }).click()
    await form.locator('.image-batch-labels .el-select__wrapper').last().click()
    await page.getByRole('option', { name: '逆光', exact: true }).click()
    await form.getByRole('button', { name: '应用场景', exact: true }).click()
    await form.locator('.el-checkbox-group label').filter({ hasText: 'Gamma' }).click()
    await page.setViewportSize({ width: 390, height: 844 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
    await form.getByRole('button', { name: '开始多图测试', exact: true }).click()
    await expect(page.locator('.current-experiment')).toContainText('1200张测试')
    expect(labels.items).toHaveLength(1200)
    expect(labels.methods).toEqual(['original', 'gamma'])
    expect(labels.items.every((item: any, index: number) => {
      const name = item.filename.split('/').at(-2)
      return item.person_id === (index === 25 ? null : people.find((person) => person.name === name)!.id)
    })).toBe(true)
    expect(labels.items[25].person_id).toBeNull()
    expect(labels.items.every((item: any) => item.scene === 'backlight')).toBe(true)
    await page.getByRole('tab', { name: '新建测试', exact: true }).click()
    await expect(page.getByRole('region', { name: '当前运行测试' })).toContainText('1200张测试')
    await expect(page.getByRole('button', { name: '开始多图测试', exact: true })).toHaveCount(0)
    expect(errors).toEqual([])
  } finally { await rm(folder, { recursive: true, force: true }) }
})

test('运行中查看旧结果不串页，新建页保留当前任务直至结束和刷新', async ({ page }) => {
  const active = makeRecord(8, '当前低照度任务', 'running')
  const previous = makeRecord(3, '已有逆光结果')
  let hold = false
  let started = false
  let release!: () => void
  const pending = new Promise<void>((resolve) => { release = resolve })
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
    const path = new URL(route.request().url()).pathname
    let data: unknown = []
    if (path === '/api/experiment') data = [active, previous]
    else if (path === '/api/experiment/8') {
      if (hold) { hold = false; started = true; await pending }
      data = active
    } else if (path === '/api/experiment/3') data = previous
    await route.fulfill({ json: { data } })
  })
  await page.goto('/experiments')
  const task = page.getByRole('region', { name: '当前运行测试' })
  await expect(task).toContainText('当前低照度任务')
  await expect(task.getByRole('status')).toHaveText('已处理 2 / 10 项')
  await expect(page.getByRole('button', { name: '选择查询目录', exact: true })).toHaveCount(0)
  await expect.poll(async () => page.evaluate(() => document.querySelectorAll('.current-experiment').length)).toBe(0)
  // Wait for the initial selection to finish before holding the next polling response.
  await page.getByRole('tab', { name: '测试结果', exact: true }).click()
  await expect(page.locator('.current-experiment')).toContainText('当前低照度任务')
  hold = true
  await expect.poll(() => started, { timeout: 10000 }).toBe(true)
  await page.getByRole('tab', { name: '历史记录', exact: true }).click()
  await page.locator('.experiment-history .el-table__body-wrapper tbody tr')
    .filter({ hasText: '已有逆光结果' }).getByRole('button', { name: '查看结果', exact: true }).click()
  const result = page.locator('.current-experiment')
  await expect(result.getByRole('heading', { level: 2 })).toContainText('已有逆光结果')
  const response = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/experiment/8')
  release()
  await response
  await expect(result.getByRole('heading', { level: 2 })).toContainText('已有逆光结果')
  await expect(page).toHaveURL(/run=3/)
  await page.getByRole('tab', { name: '新建测试', exact: true }).click()
  await expect(task).toContainText('当前低照度任务')
  await expect(page.getByRole('button', { name: '开始多图测试', exact: true })).toHaveCount(0)
  await page.reload()
  await expect(task).toContainText('当前低照度任务')
  active.progress = 7
  await expect(task.getByRole('status')).toHaveText('已处理 7 / 10 项')
  active.status = 'completed'
  active.progress = 10
  await expect(task).toHaveCount(0)
  await expect(page.getByRole('button', { name: '开始多图测试', exact: true })).toBeEnabled()
  await expect(page.getByRole('textbox', { name: '测试名称', exact: true })).toHaveValue('')
  expect(errors).toEqual([])
})
