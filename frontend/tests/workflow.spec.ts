import { test, expect } from '@playwright/test'
import { resolve } from 'node:path'
const root = resolve(import.meta.dirname, '../..')

test('真实模型六页面完整流程与移动布局', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '系统概览', exact: true })).toBeVisible()
  await expect(page.getByText('等待后端连接')).toHaveCount(0)
  await page.screenshot({ path: root + '/work/dashboard.png', fullPage: true })
  await page.getByRole('link', { name: /图像增强实验室/ }).click()
  await expect(page.getByRole('heading', { name: '图像增强实验室', exact: true })).toBeVisible()
  await page.getByLabel('上传图片', { exact: true }).setInputFiles(root + '/work/astronaut.png')
  await page.getByRole('button', { name: '分析并增强', exact: true }).click()
  await expect(page.getByRole('link', { name: /下载增强图像/ })).toBeVisible()
  await page.screenshot({ path: root + '/work/enhancement.png', fullPage: true })
  await page.getByRole('link', { name: /人脸检测/ }).click()
  await expect(page.getByRole('heading', { name: '人脸检测', exact: true })).toBeVisible()
  await page.getByLabel('上传图片', { exact: true }).setInputFiles(root + '/work/astronaut.png')
  await page.getByRole('button', { name: '运行双路检测' }).click()
  await expect(page.getByRole('heading', { name: '人脸明细与对齐裁剪' })).toBeVisible()
  await expect(page.getByAltText('对齐人脸裁剪').first()).toBeVisible()
  await page.screenshot({ path: root + '/work/detection.png', fullPage: true })
  await page.getByRole('link', { name: /身份库管理/ }).click()
  await expect(page.getByRole('heading', { name: '身份库管理', exact: true })).toBeVisible()
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
  await page.getByLabel('上传图片', { exact: true }).setInputFiles(root + '/work/astronaut.png')
  await page.getByRole('button', { name: '开始身份确认' }).click()
  await expect(page.getByText('身份确认成功', { exact: true })).toBeVisible()
  await page.screenshot({ path: root + '/work/recognition.png', fullPage: true })
  await page.getByLabel('上传图片', { exact: true }).setInputFiles(root + '/work/hopper.png')
  await page.getByRole('button', { name: '开始身份确认' }).click()
  await expect(page.getByText('未确认身份', { exact: true })).toBeVisible()
  await page.getByRole('link', { name: /实验评估/ }).click()
  await expect(page.getByRole('heading', { name: '实验评估', exact: true })).toBeVisible()
  const registered = (await (await page.request.get('/api/person')).json()).data.find(
    (person: { name: string; id: number }) => person.name === '浏览器测试参考身份',
  )
  const registeredDetail = (await (await page.request.get('/api/person/' + registered.id)).json())
    .data
  expect(registeredDetail.samples[0].capture_id).toMatch(/^enroll-[a-f0-9-]{36}$/)
  const { execFileSync } = await import('node:child_process')
  execFileSync(root + '/.venv/bin/python', [root + '/scripts/prepare_browser_fixtures.py'], {
    env: { ...process.env, LUMIFACE_TEST_PERSON_ID: String(registered.id) },
  })
  await page.getByLabel('导入数据集 ZIP').setInputFiles(root + '/work/browser-dataset.zip')
  await expect(page.getByText('浏览器流程验证数据', { exact: true }).first()).toBeVisible()
  await page.getByRole('button', { name: '开始批量评估' }).click()
  await expect(page.getByText('已完成', { exact: true }).first()).toBeVisible({ timeout: 90000 })
  await page.getByRole('tab', { name: '分场景统计' }).click()
  await expect(page.getByText('红外补光 · 目标 95.0%').last()).toBeVisible()
  await expect(page.locator('.target-grid').last().getByText('未评估')).toHaveCount(3)
  await page.getByRole('tab', { name: '逐样本结果' }).click()
  await page.getByRole('button', { name: '查看对比', exact: true }).first().click()
  await expect(page.getByRole('dialog').getByAltText('增强结果')).toBeVisible()
  await page.getByRole('button', { name: '关闭此对话框' }).click()
  await page.getByRole('tab', { name: '算法对比' }).click()
  await page.screenshot({ path: root + '/work/experiments.png', fullPage: true })
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: '导出逐样本 CSV' }).click()
  expect((await downloadPromise).suggestedFilename()).toMatch(/experiment-.*\.csv/)
  await page.goto('/')
  await expect(
    page.locator('.recent-tasks').getByRole('cell', { name: /浏览器流程验证数据/ }),
  ).toBeVisible()
  await expect(page.locator('.model-panel').getByText('已加载', { exact: true })).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await page.getByRole('button', { name: '打开导航' }).click()
  await page.getByRole('link', { name: /图像增强实验室/ }).click()
  await expect(page.getByRole('heading', { name: '图像增强实验室', exact: true })).toBeVisible()
  await page.screenshot({ path: root + '/work/mobile.png', fullPage: true })
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true)
  expect(errors).toEqual([])
})

test('真实公开研究报告显示计数、证据限制与逐样本导出', async ({ page }) => {
  const response = await page.request.get('/api/research/benchmarks')
  expect(response.status()).toBe(200)
  const reports = (await response.json()).data
  test.skip(reports.length === 0, '未运行真实研究数据时不构造报告')
  await page.goto('/experiments')
  const card = page.locator('.research-card')
  await expect(card.getByText('真实公开数据评估', { exact: true })).toBeVisible()
  await expect(
    card.getByText(
      '真实主动近红外数据，夜间环境和跨会话信息未提供；结果验证 NIR → NIR 协议，尚不能代替夜间补光验收。',
    ),
  ).toBeVisible()
  await expect(card.getByText('已有实测，目标场景证据不足')).toBeVisible()
  await expect(card.getByText('Wilson 95% 区间')).toBeVisible()
  const download = page.waitForEvent('download')
  await card.getByRole('button', { name: '下载真实逐样本结果' }).click()
  expect((await download).suggestedFilename()).toBe('cbsr-nir-real-results.csv')
  await page.screenshot({ path: root + '/work/research-results.png', fullPage: true })
  const protocol = await page.request.get('/api/research/benchmarks/cbsr-nir/protocol')
  expect((await protocol.json()).data.archive_sha256).toBe(
    '066e385ac7469012f9c2574738c6b8bd15dcfcc5085e7eb97148e0b884b9fe53',
  )
  if (reports.some((r: any) => r.dataset === 'yale-b')) {
    await card.locator('.el-select__wrapper').click()
    await page.getByRole('option', { name: 'Yale B 真实受控光照评估 · 固定子集' }).click()
    await expect(
      card.getByText(
        '真实受控光照、紧裁剪输入；不同照明图像来自同次短时采集，不能代替独立实景逆光或夜间验收。',
      ),
    ).toBeVisible()
    await expect(card.getByText('89 张', { exact: true })).toBeVisible()
    await page.screenshot({ path: root + '/work/research-yale-results.png', fullPage: true })
  }
  await page.setViewportSize({ width: 390, height: 844 })
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true)
})

test('网页批量导入预览、同名跳过、真实多参考注册与无人脸失败', async ({ page }) => {
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
  const dataDownload = page.waitForEvent('download')
  await dialog.getByRole('link', { name: '下载 AT&T 演示数据包（40 人）', exact: true }).click()
  const dataArchive = await dataDownload
  expect(dataArchive.suggestedFilename()).toBe('att_faces_demo.zip')
  expect(await dataArchive.failure()).toBeNull()
  const simulatedDownload = page.waitForEvent('download')
  await dialog.getByRole('link', { name: '下载三类光照演示包（40 人）', exact: true }).click()
  const simulatedArchive = await simulatedDownload
  expect(simulatedArchive.suggestedFilename()).toBe('att_lighting_three_scenes.zip')
  expect(await simulatedArchive.failure()).toBeNull()
  await page
    .getByLabel('选择批量身份文件夹', { exact: true })
    .setInputFiles(root + '/work/browser-batch-invalid')
  await expect(dialog.getByText(/有 11 张照片，每人最多 10 张/)).toBeVisible()
  await expect(dialog.getByRole('button', { name: '开始导入', exact: true })).toBeEnabled()
  await page
    .getByLabel('选择批量身份文件夹', { exact: true })
    .setInputFiles(root + '/work/browser-batch-identities')
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
  const chooseAgain = page.waitForEvent('filechooser')
  await dialog.getByRole('button', { name: '选择照片根目录', exact: true }).click()
  await (await chooseAgain).setFiles(root + '/work/browser-batch-identities')
  await expect(dialog.getByText('待导入', { exact: true })).toHaveCount(3)
  await expect(dialog.getByRole('button', { name: '开始导入', exact: true })).toBeEnabled()
  const reselect = page.waitForEvent('filechooser')
  await dialog.getByRole('button', { name: '重新选择', exact: true }).click()
  await (await reselect).setFiles(root + '/work/browser-batch-invalid')
  await expect(dialog.getByText(/有 11 张照片，每人最多 10 张/)).toBeVisible()
  await expect(dialog.getByRole('status')).toHaveCount(0)
  const chooseValid = page.waitForEvent('filechooser')
  await dialog.getByRole('button', { name: '选择照片根目录', exact: true }).click()
  await (await chooseValid).setFiles(root + '/work/browser-batch-identities')
  await expect(dialog.getByRole('status')).toContainText('browser-batch-identities/')
  await expect(dialog.getByText('待导入', { exact: true })).toHaveCount(3)
  expect(errors).toEqual([])
})

test('AT&T 40 个匿名身份通过网页批量注册', async ({ page }) => {
  const { existsSync } = await import('node:fs')
  test.skip(
    !existsSync(root + '/datasets/att_faces_demo/gallery/ATT_s40/01.png'),
    '先运行 prepare_att_faces_demo.py 下载并准备公开数据',
  )
  await page.goto('/persons')
  await page.getByRole('button', { name: '批量导入身份', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '批量导入身份', exact: true })
  await page
    .getByLabel('选择批量身份文件夹', { exact: true })
    .setInputFiles(root + '/datasets/att_faces_demo/gallery')
  await expect(dialog.getByText('40 人 · 120 张照片', { exact: true })).toBeVisible()
  await dialog.getByRole('button', { name: '开始导入', exact: true }).click()
  await expect(dialog.getByText('已处理 40 / 40 人', { exact: true })).toBeVisible({
    timeout: 300000,
  })
  await expect(dialog.getByText('已注册', { exact: true })).toHaveCount(40)
  await expect(dialog.getByText('失败', { exact: true })).toHaveCount(0)
  await expect(dialog.getByText('待核对', { exact: true })).toHaveCount(0)
  const people = (await (await page.request.get('/api/person')).json()).data.filter((p: any) =>
    /^ATT_s\d{2}$/.test(p.name),
  )
  expect(people).toHaveLength(40)
  expect(people.every((p: any) => p.sample_count === 3)).toBe(true)
  await page.waitForTimeout(700)
  await page.screenshot({ path: root + '/work/batch-ui/att-web-import.png', fullPage: true })
})
