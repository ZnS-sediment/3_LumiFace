import { test, expect } from '@playwright/test'
import { mockDirectoryPicker } from './helpers/directory'
import { resolve } from 'node:path'
const root = resolve(import.meta.dirname, '../..')

test('真实模型五页面完整流程与移动布局', async ({ page }) => {
  const errors: string[] = []
  const modelRequests: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('request', (request) => {
    if (request.url().includes('/api/system/model')) modelRequests.push(request.url())
  })
  await page.goto('/')
  await expect(page).toHaveURL(/\/enhance$/)
  await expect(page.getByRole('navigation', { name: '主导航' }).getByRole('link')).toHaveCount(5)
  await expect(page.getByRole('link', { name: '系统概览', exact: true })).toHaveCount(0)
  await expect(page.locator('.page-heading p')).toHaveCount(0)
  await expect(page.getByLabel('人脸模型状态')).toHaveCount(0)
  await page
    .getByRole('navigation', { name: '主导航' })
    .getByRole('link', { name: '图像增强', exact: true })
    .click()
  await expect(page.getByRole('heading', { name: '图像增强', exact: true })).toBeVisible()
  await page.getByLabel('上传图片', { exact: true }).setInputFiles(root + '/work/astronaut.png')
  await page.getByRole('button', { name: '分析并增强', exact: true }).click()
  await expect(page.getByRole('link', { name: /下载增强图像/ })).toBeVisible()
  await page.screenshot({ path: root + '/work/enhancement.png', fullPage: true })
  await page.getByRole('link', { name: /人脸检测/ }).click()
  await expect(page.getByRole('heading', { name: '人脸检测', exact: true })).toBeVisible()
  await expect(page.getByLabel('人脸模型状态')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '加载模型', exact: true })).toHaveCount(0)
  await page.getByLabel('上传图片', { exact: true }).setInputFiles(root + '/work/astronaut.png')
  await page.getByRole('button', { name: '开始检测' }).click()
  await expect(page.getByRole('heading', { name: '人脸明细与对齐裁剪' })).toBeVisible()
  await expect(page.getByAltText('对齐人脸裁剪').first()).toBeVisible()
  await page.screenshot({ path: root + '/work/detection.png', fullPage: true })
  await page.getByRole('link', { name: /身份库管理/ }).click()
  await expect(page.getByRole('heading', { name: '身份库管理', exact: true })).toBeVisible()
  await expect(page.getByLabel('人脸模型状态')).toHaveCount(0)
  await page.getByRole('button', { name: '注册新身份' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('textbox').nth(0).fill('浏览器测试参考身份')
  await dialog.getByLabel('上传图片', { exact: true }).setInputFiles(root + '/work/astronaut.png')
  await dialog.getByRole('button', { name: '提取特征并注册' }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByText('浏览器测试参考身份', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '查看', exact: true }).first().click()
  await expect(page.getByAltText('注册参考照片')).toBeVisible()
  await page.getByRole('button', { name: '关闭此对话框' }).click()
  await page.getByRole('link', { name: /身份确认/ }).click()
  await expect(page.getByRole('heading', { name: '身份确认', exact: true })).toBeVisible()
  await expect(page.getByLabel('人脸模型状态')).toHaveCount(0)
  await page.getByLabel('上传图片', { exact: true }).setInputFiles(root + '/work/astronaut.png')
  await page.getByRole('button', { name: '开始身份确认' }).click()
  await expect(page.getByText('身份确认成功', { exact: true })).toBeVisible()
  await page.screenshot({ path: root + '/work/recognition.png', fullPage: true })
  await page.getByLabel('上传图片', { exact: true }).setInputFiles(root + '/work/hopper.png')
  await page.getByRole('button', { name: '开始身份确认' }).click()
  await expect(page.getByText('未确认身份', { exact: true })).toBeVisible()
  await page.getByLabel('上传图片', { exact: true }).setInputFiles(root + '/work/browser-group.png')
  const groupResponse = page.waitForResponse((r) => r.url().endsWith('/api/recognition/identify'))
  await page.getByRole('button', { name: '开始身份确认' }).click()
  const group = (await (await groupResponse).json()).data
  expect(group.faces.length).toBeGreaterThanOrEqual(2)
  expect(group.faces.some((f: any) => f.match.name === '浏览器测试参考身份')).toBe(true)
  expect(group.faces.some((f: any) => !f.match.confirmed)).toBe(true)
  await expect(page.locator('.face-decisions')).toBeVisible()
  await expect(page.locator('.face-decisions .el-table__body tr')).toHaveCount(group.faces.length)
  await page.screenshot({ path: root + '/work/multi-face-recognition.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.locator('.face-decisions')).toBeVisible()
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true)
  await page.screenshot({ path: root + '/work/multi-face-recognition-mobile.png', fullPage: true })
  await page.setViewportSize({ width: 1440, height: 1050 })
  await page.getByRole('link', { name: /实验评估/ }).click()
  await expect(page.getByRole('heading', { name: '实验评估', exact: true })).toBeVisible()
  await expect(page.getByRole('tab', { name: '新建测试', exact: true })).toBeVisible()
  await expect(page.getByRole('tab', { name: '测试结果', exact: true })).toBeVisible()
  await expect(page.getByRole('tab', { name: '历史记录', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '创建消融实验', exact: true })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: '真实公开数据评估', exact: true })).toHaveCount(0)
  await page.screenshot({ path: root + '/work/experiments.png', fullPage: true })
  await expect(page.getByLabel('人脸模型状态')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '加载模型', exact: true })).toHaveCount(0)
  await expect(page.getByRole('link', { name: /下载身份与光照数据/ })).toHaveCount(0)
  await expect(
    page.getByText('一次测试多张查询照片，自动汇总正确识别率，保留每次实验记录。', { exact: true }),
  ).toHaveCount(0)
  await expect(page.getByText(/每张图应为单人照片/)).toHaveCount(0)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await page.getByRole('button', { name: '打开导航' }).click()
  await page
    .getByRole('navigation', { name: '主导航' })
    .getByRole('link', { name: '图像增强', exact: true })
    .click()
  await expect(page.getByRole('heading', { name: '图像增强', exact: true })).toBeVisible()
  await page.screenshot({ path: root + '/work/mobile.png', fullPage: true })
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true)
  expect(modelRequests).toEqual([])
  expect(errors).toEqual([])
})

test('网页批量导入预览、同名跳过、真实多参考注册与无人脸失败', async ({ page }) => {
  const chooseDirectory = await mockDirectoryPicker(page)
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  const people = await page.request.get('/api/person')
  if (!(await people.json()).data.some((p: any) => p.name === '浏览器测试参考身份')) {
    const { readFileSync } = await import('node:fs')
    const response = await page.request.post('/api/person/register', {
      multipart: {
        name: '浏览器测试参考身份',
        capture_id: 'batch-browser-reference',
        files: {
          name: 'ref.png',
          mimeType: 'image/png',
          buffer: readFileSync(root + '/work/astronaut.png'),
        },
      },
    })
    expect(response.status()).toBe(200)
  }
  await page.goto('/persons')
  await page.getByRole('button', { name: '批量导入身份', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '批量导入身份', exact: true })
  await expect(dialog.getByRole('link', { name: /AT&T|三类光照演示包/ })).toHaveCount(0)
  const archives: string[] = []
  for (const [label, filename] of [
    ['下载原数据包（120 人）', 'lfw_120_lighting.zip'],
    ['下载新数据包（280 人）', 'lfw_280_new_lighting.zip'],
  ]) {
    await expect(page.getByRole('link', { name: label, exact: true })).toHaveCount(1)
    const download = page.waitForEvent('download')
    await dialog.getByRole('link', { name: label, exact: true }).click()
    const archive = await download
    expect(archive.suggestedFilename()).toBe(filename)
    expect(await archive.failure()).toBeNull()
    archives.push((await archive.path())!)
  }
  await expect(dialog.getByRole('link')).toHaveCount(2)
  const { execFileSync } = await import('node:child_process')
  const counts = JSON.parse(execFileSync(root + '/.venv/bin/python', ['-c', `
import json, sys, zipfile
from collections import Counter
sets, counts = [], []
for path, expected in zip(sys.argv[1:], [120, 280]):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        photos = [name.split('/') for name in archive.namelist() if name.endswith('.png') and '/query/' in name]
        scenes = Counter(parts[2] for parts in photos)
        assert len(scenes) == 4 and set(scenes.values()) == {expected * 3}
        assert all(len(parts) == 5 for parts in photos)
        assert set(Counter((parts[2], parts[3]) for parts in photos).values()) == {3}
        people = {parts[3] for parts in photos}
        assert len(people) == expected
        assert len([n for n in archive.namelist() if '/gallery/' in n and n.endswith('.png')]) == expected * 2
        sets.append(people)
        counts.append(len(people))
assert not sets[0] & sets[1]
print(json.dumps(counts))
`, ...archives], { encoding: 'utf8' }))
  expect(counts).toEqual([120, 280])

  await chooseDirectory(
    root + '/work/browser-batch-invalid',
    dialog.getByRole('button', { name: '选择照片根目录', exact: true }),
  )
  await expect(dialog.getByText(/有 11 张照片，每人最多 10 张/)).toBeVisible()
  await expect(dialog.getByRole('button', { name: '开始导入', exact: true })).toBeEnabled()
  await chooseDirectory(
    root + '/work/browser-batch-identities',
    dialog.getByRole('button', { name: '选择照片根目录', exact: true }),
  )
  await expect(dialog.getByText('3 人 · 4 张照片', { exact: true })).toBeVisible()
  await expect(dialog.getByText('待导入', { exact: true })).toHaveCount(3)
  await expect(dialog.getByRole('button', { name: '开始导入', exact: true })).toBeEnabled()
  await expect(dialog.getByText('数据批次', { exact: true })).toHaveCount(0)
  await dialog.getByRole('button', { name: '开始导入', exact: true }).click()
  await expect(dialog.getByText('已注册', { exact: true })).toHaveCount(1)
  await expect(dialog.getByText('已跳过', { exact: true })).toHaveCount(1)
  await expect(dialog.getByText('失败', { exact: true })).toHaveCount(1)
  await expect(dialog.getByText('已处理 3 / 3 人', { exact: true })).toBeVisible()
  await expect(dialog.getByText('已注册，参考照片 2 张', { exact: true })).toBeVisible()
  await expect(dialog.getByText(/检测到 0 张人脸/)).toBeVisible()
  const download = page.waitForEvent('download')
  await dialog.getByRole('button', { name: '下载导入结果' }).click()
  const importReport = await download
  expect(importReport.suggestedFilename()).toBe('lumiface-identity-import.json')
  const { readFile } = await import('node:fs/promises')
  const report = JSON.parse(await readFile((await importReport.path())!, 'utf8'))
  expect(report.root_directory).toBe(root + '/work/browser-batch-identities')
  const importedRow = report.rows.find((row: any) => row.status === 'registered')
  expect(importedRow.capture_id).toMatch(/^enroll-[a-f0-9-]{36}$/)
  const imported = (await (await page.request.get('/api/person/' + importedRow.person_id)).json())
    .data
  expect(imported.samples.map((sample: any) => sample.capture_id)).toEqual([
    importedRow.capture_id,
    importedRow.capture_id,
  ])
  await page.screenshot({ path: root + '/work/batch-ui/web-batch-import.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.waitForTimeout(350)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
    true,
  )
  await dialog.getByRole('button', { name: '关闭', exact: true }).click()
  await expect(dialog).toBeHidden()
  await expect(
    page.locator('section.card').getByText('批量导入参考B', { exact: true }),
  ).toBeVisible()
  const updated = (await (await page.request.get('/api/person')).json()).data
  expect(updated.find((p: any) => p.name === '批量导入参考B').sample_count).toBe(2)
  expect(updated.some((p: any) => p.name === '批量导入无脸')).toBe(false)
  await page.getByRole('button', { name: '批量导入身份', exact: true }).click()
  await chooseDirectory(
    root + '/work/browser-batch-identities',
    dialog.getByRole('button', { name: '选择照片根目录', exact: true }),
  )
  await expect(dialog.getByText('待导入', { exact: true })).toHaveCount(3)
  await expect(dialog.getByRole('button', { name: '开始导入', exact: true })).toBeEnabled()
  await chooseDirectory(
    root + '/work/browser-batch-invalid',
    dialog.getByRole('button', { name: '重新选择', exact: true }),
  )
  await expect(dialog.getByText(/有 11 张照片，每人最多 10 张/)).toBeVisible()
  await expect(dialog.getByRole('status')).toHaveCount(0)
  await chooseDirectory(
    root + '/work/browser-batch-identities',
    dialog.getByRole('button', { name: '选择照片根目录', exact: true }),
  )
  await expect(dialog.getByRole('status')).toContainText(root + '/work/browser-batch-identities')
  await expect(dialog.getByText('待导入', { exact: true })).toHaveCount(3)
  await chooseDirectory(
    root + '/work/browser-batch-identities',
    dialog.getByRole('button', { name: '重新选择', exact: true }),
    ['浏览器测试参考身份', '批量导入参考B'],
  )
  await expect(dialog.getByText('2 人 · 3 张照片', { exact: true })).toBeVisible()
  await dialog.getByRole('button', { name: '开始导入', exact: true }).click()
  await expect(dialog).toBeHidden()
  await expect(page.locator('.el-message--success').last()).toContainText(
    '处理完成：注册 0 人，跳过 2 人',
  )
  await page.getByRole('button', { name: '批量导入身份', exact: true }).click()
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('status')).toHaveCount(0)
  await expect(dialog.getByText('待导入', { exact: true })).toHaveCount(0)
  expect(errors).toEqual([])
})

test('多图识别测试：多选、目录标签、逐图结果、连续测试更新及刷新保留', async ({ page }) => {
  test.skip(process.env.LUMIFACE_TEST_DELETE_ISOLATED !== '1', '仅使用隔离测试库')
  const { readFile } = await import('node:fs/promises')
  const people = (await (await page.request.get('/api/person')).json()).data
  if (!people.some((person: any) => person.name === '多图测试参考')) {
    const registration = await page.request.post('/api/person/register', {
      multipart: {
        name: '多图测试参考',
        capture_id: 'multi-browser-reference',
        files: {
          name: '01.png',
          mimeType: 'image/png',
          buffer: await readFile(root + '/work/browser-multi-reference.png'),
        },
      },
    })
    expect(registration.status(), await registration.text()).toBe(200)
  }
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/experiments')
  await expect(page.getByText(/阈值/)).toHaveCount(0)
  const form = page.locator('.image-batch-card')
  const current = page.locator('.current-experiment')
  await form.getByRole('button', { name: '开始多图测试', exact: true }).click()
  await expect(page.locator('.el-message--error').last()).toContainText('测试图片')
  await form
    .getByLabel('选择多张测试图片', { exact: true })
    .setInputFiles([
      root + '/work/browser-multi-query/多图测试参考/query1.png',
      root + '/work/browser-multi-query/多图测试参考/query2.png',
    ])
  await expect(form.getByRole('status')).toContainText('2 张待标注')
  await form.getByRole('button', { name: '开始多图测试', exact: true }).click()
  await expect(page.locator('.el-message--error').last()).toContainText('每张图片的真实身份')
  await form.getByRole('combobox', { name: '统一真实身份', exact: true }).click()
  await page.getByRole('option', { name: '多图测试参考', exact: true }).click()
  await form.getByRole('button', { name: '应用到全部图片', exact: true }).click()
  await expect(form.getByRole('status')).not.toContainText('待标注')
  const firstResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/experiment/images') && response.request().method() === 'POST',
  )
  await form.getByRole('button', { name: '开始多图测试', exact: true }).click()
  const first = (await (await firstResponse).json()).data
  await expect(current.getByRole('heading', { level: 2 })).toContainText(first.name)
  await expect(current.getByText('已完成', { exact: true })).toBeVisible()
  const firstSaved = (await (await page.request.get('/api/experiment/' + first.id)).json()).data
  expect(firstSaved.summary.original.overall.known).toBe(2)
  expect(firstSaved.name).toMatch(/^多图测试 /)
  await page.getByRole('tab', { name: '新建测试', exact: true }).click()
  await form
    .getByLabel('选择测试图片目录', { exact: true })
    .setInputFiles(root + '/work/browser-multi-query')
  await expect(form.getByRole('status')).toHaveText('已选择 3 张')
  await form.getByRole('textbox', { name: '测试名称', exact: true }).fill('自定义光照测试')
  await form.locator('label.el-checkbox').filter({ hasText: 'Gamma' }).click()
  const secondResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/experiment/images') && response.request().method() === 'POST',
  )
  await form.getByRole('button', { name: '开始多图测试', exact: true }).click()
  const second = (await (await secondResponse).json()).data
  expect(second.id).not.toBe(first.id)
  expect(second.name).toBe('自定义光照测试')
  await expect(current.getByRole('heading', { level: 2 })).toContainText(second.name)
  await expect(current.getByText('已完成', { exact: true })).toBeVisible()
  const latest = (await (await page.request.get('/api/experiment/' + second.id)).json()).data
  expect(latest.progress).toBe(6)
  expect(latest.summary.original.overall.known).toBe(3)
  expect(latest.summary.original.overall.no_face).toBe(1)
  expect(latest.summary.original.overall.confirmation_rate).toBe(
    latest.summary.original.overall.correct / 3,
  )
  await expect(current).toContainText(latest.summary.original.overall.correct + ' / 3')
  const errorsSection = current.getByRole('region', { name: '错误类型统计', exact: true })
  await expect(errorsSection.getByRole('article')).toHaveCount(2)
  const originalErrors = errorsSection.getByRole('article', {
    name: '不增强（对照组）',
    exact: true,
  })
  await expect(
    originalErrors.locator('.error-type').filter({ hasText: '未检测到人脸' }).locator('dd'),
  ).toHaveText('1 张')
  const errorStats = latest.error_summary.original.overall
  await expect(originalErrors.locator('.error-method-heading')).toContainText(
    errorStats.total_errors + ' 张异常 / 3 张',
  )
  const selectScene = async (name: string) => {
    await current.locator('.scene-filter .el-select__wrapper').click()
    await page.getByRole('option', { name, exact: true }).click()
  }
  await selectScene('低照度')
  await expect(originalErrors).toContainText('该场景没有测试图片')
  await selectScene('全部场景')
  await page.screenshot({
    path: root + '/work/batch-ui/error-summary-desktop.png',
    fullPage: true,
    animations: 'disabled',
  })
  await expect(current.getByText('未检测到人脸', { exact: true }).first()).toBeVisible()
  await expect(current.getByRole('link', { name: /导出逐图 CSV/ })).toHaveCount(0)
  await page.reload()
  await expect(current.getByRole('heading', { level: 2 })).toContainText(second.name)
  await expect(current).toContainText(latest.summary.original.overall.correct + ' / 3')
  const unchanged = (await (await page.request.get('/api/experiment/' + first.id)).json()).data
  expect(unchanged.summary).toEqual(firstSaved.summary)
  await page.getByRole('tab', { name: '历史记录', exact: true }).click()
  await expect(page.getByRole('heading', { name: '测试记录', exact: true })).toBeVisible()
  const history = page.locator('.experiment-history')
  const historyRows = history.locator('.el-table__body-wrapper tbody tr')
  const ids = async () =>
    Promise.all(
      (await historyRows.all()).map(async (row) =>
        Number(await row.locator('td').first().innerText()),
      ),
    )
  const descending = await ids()
  expect(descending).toEqual([...descending].sort((a, b) => b - a))
  await history.locator('.history-sort .el-select__wrapper').click()
  await page.getByRole('option', { name: '升序（从小到大）', exact: true }).click()
  await expect.poll(ids).toEqual([...descending].sort((a, b) => a - b))
  const renamedRow = historyRows.nth(
    (await historyRows.allTextContents()).findIndex((text) => text.includes(second.name)),
  )
  await expect(renamedRow).toContainText(second.name)
  await renamedRow.getByRole('button', { name: '重命名', exact: true }).click()
  const renameDialog = page.getByRole('dialog', { name: '重命名测试', exact: true })
  await renameDialog.getByRole('textbox', { name: '测试名称', exact: true }).fill('   ')
  await renameDialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.locator('.el-message--error').last()).toContainText('测试名称')
  await renameDialog.getByRole('textbox', { name: '测试名称', exact: true }).fill('逆光对比第一轮')
  await renameDialog.getByRole('button', { name: '取消', exact: true }).click()
  await expect(renamedRow).not.toContainText('逆光对比第一轮')
  await renamedRow.getByRole('button', { name: '重命名', exact: true }).click()
  await renameDialog.getByRole('textbox', { name: '测试名称', exact: true }).fill('逆光对比第一轮')
  await renameDialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(renameDialog).toBeHidden()
  await expect(renamedRow).toContainText('逆光对比第一轮')
  await renamedRow.getByRole('button', { name: '查看结果', exact: true }).click()
  await expect(current.getByRole('heading', { level: 2 })).toContainText('逆光对比第一轮')
  await page.reload()
  await expect(current.getByRole('heading', { level: 2 })).toContainText('逆光对比第一轮')
  await page.getByRole('tab', { name: '历史记录', exact: true }).click()
  await expect(history.getByRole('combobox', { name: '编号排序' })).toHaveAttribute(
    'aria-expanded',
    'false',
  )
  await expect(history.locator('.history-sort')).toContainText('升序（从小到大）')
  await expect.poll(ids).toEqual([...descending].sort((a, b) => a - b))
  await history.locator('.history-sort .el-select__wrapper').click()
  await page.getByRole('option', { name: '降序（从大到小）', exact: true }).click()
  await expect.poll(ids).toEqual(descending)
  await page.getByRole('tab', { name: '测试结果', exact: true }).click()
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(errorsSection).toBeVisible()
  const errorCards = await errorsSection.locator('.error-method').all()
  const firstCard = await errorCards[0].boundingBox()
  const nextCard = await errorCards[1].boundingBox()
  expect(nextCard!.y).toBeGreaterThanOrEqual(firstCard!.y + firstCard!.height)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
    true,
  )
  await page.screenshot({
    path: root + '/work/batch-ui/error-summary-mobile.png',
    fullPage: true,
    animations: 'disabled',
  })
  await page.getByRole('tab', { name: '新建测试', exact: true }).click()
  await expect(form.getByRole('link', { name: /下载身份与光照数据/ })).toHaveCount(0)
  await expect(form.getByRole('textbox', { name: '测试名称', exact: true })).toHaveValue('')
  await page.setViewportSize({ width: 390, height: 844 })
  await form
    .getByLabel('选择测试图片目录', { exact: true })
    .setInputFiles(root + '/work/browser-multi-query')
  await expect(form.getByRole('status')).toHaveText('已选择 3 张')
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true)
  await page.screenshot({
    path: root + '/work/batch-ui/multi-image-evaluation.png',
    fullPage: true,
  })
  expect(errors).toEqual([])
})

test('同一身份的三类光照输入自动匹配并完成统一评估', async ({ page }) => {
  test.skip(process.env.LUMIFACE_TEST_DELETE_ISOLATED !== '1', '仅使用隔离测试库')
  const { readFile } = await import('node:fs/promises')
  const people = (await (await page.request.get('/api/person')).json()).data
  if (!people.some((person: any) => person.name === '多图测试参考')) {
    const registration = await page.request.post('/api/person/register', {
      multipart: {
        name: '多图测试参考',
        capture_id: 'lighting-browser-reference',
        files: {
          name: 'reference.png',
          mimeType: 'image/png',
          buffer: await readFile(root + '/work/browser-multi-reference.png'),
        },
      },
    })
    expect(registration.status()).toBe(200)
  }
  await page.goto('/experiments')
  await expect(page.getByText(/阈值/)).toHaveCount(0)
  const form = page.locator('.image-batch-card')
  await form
    .getByLabel('选择测试图片目录', { exact: true })
    .setInputFiles(root + '/work/browser-lighting-query')
  await expect(form.getByRole('status')).toHaveText('已选择 3 张')
  for (const label of await form.locator('label.el-checkbox').all()) {
    if (!(await label.getByRole('checkbox').isChecked())) await label.click()
  }
  const response = page.waitForResponse(
    (r) => r.url().endsWith('/api/experiment/images') && r.request().method() === 'POST',
  )
  await form.getByRole('button', { name: '开始多图测试', exact: true }).click()
  const record = (await (await response).json()).data
  const current = page.locator('.current-experiment')
  await expect(current.getByText('已完成', { exact: true })).toBeVisible()
  const result = (await (await page.request.get('/api/experiment/' + record.id)).json()).data
  expect(result.total).toBe(12)
  for (const stats of Object.values(result.summary) as any[]) {
    expect(stats.overall.known).toBe(3)
    for (const scene of ['backlight', 'uneven', 'low_light'])
      expect(stats.scenes[scene].images).toBe(1)
  }
  await page.screenshot({
    path: root + '/work/batch-ui/lighting-unified-results.png',
    fullPage: true,
  })
})
