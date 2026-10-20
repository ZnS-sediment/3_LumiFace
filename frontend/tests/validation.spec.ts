import { test, expect } from '@playwright/test'
import { resolve } from 'node:path'
const root = resolve(import.meta.dirname, '../..')

test('必填校验：批量导入只需选择目录，缺少目录时提示且不提交', async ({ page }) => {
  const mutations: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'POST') mutations.push(request.url())
  })
  await page.goto('/persons')
  await page.getByRole('button', { name: '批量导入身份', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '批量导入身份', exact: true })
  await expect(dialog.locator('.required-mark')).toHaveCount(1)
  await expect(dialog.getByText('数据批次', { exact: true })).toHaveCount(0)
  await expect(dialog.getByText('统一备注', { exact: true })).toBeVisible()
  await expect(dialog.getByText(/（选填）/)).toHaveCount(0)
  await dialog.getByRole('button', { name: '开始导入', exact: true }).click()
  await expect(page.locator('.el-message--error').last()).toContainText(
    '请补全必填项：照片根目录。',
  )
  await page
    .getByLabel('选择批量身份文件夹', { exact: true })
    .setInputFiles(root + '/work/browser-batch-identities')
  await expect(dialog.getByText('3 人 · 4 张照片', { exact: true })).toBeVisible()
  await expect(dialog.getByRole('textbox')).toHaveCount(1)
  await expect(dialog.getByRole('button', { name: '开始导入', exact: true })).toBeEnabled()
  await page.screenshot({ path: root + '/work/batch-ui/required-validation.png', fullPage: true })
  expect(mutations).toEqual([])
})

test('必填校验：注册身份具体列出缺项且不提交', async ({ page }) => {
  const mutations: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'POST') mutations.push(request.url())
  })
  await page.goto('/persons')
  await page.getByRole('button', { name: '注册新身份', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '注册新身份', exact: true })
  await expect(dialog.locator('.required-mark')).toHaveCount(2)
  await expect(dialog.getByText('采集会话编号', { exact: true })).toHaveCount(0)
  await expect(dialog.getByText('备注', { exact: true })).toBeVisible()
  await dialog.getByRole('button', { name: '提取特征并注册', exact: true }).click()
  await expect(page.locator('.el-message--error').last()).toContainText(
    '请补全必填项：姓名、参考照片。',
  )
  await dialog.getByRole('textbox').nth(0).fill('测试人员')
  await dialog.getByRole('button', { name: '提取特征并注册', exact: true }).click()
  await expect(page.locator('.el-message--error').last()).toContainText('请补全必填项：参考照片。')
  expect(mutations).toEqual([])
})

test('必填校验：图像处理、身份验证及实验缺项不提交', async ({ page }) => {
  const mutations: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'POST') mutations.push(request.url())
  })
  for (const [route, button] of [
    ['/enhance', '分析并增强'],
    ['/detect', '运行双路检测'],
    ['/recognition', '开始身份确认'],
  ]) {
    await page.goto(route)
    await expect(page.locator('.upload-field-label .required-mark')).toBeVisible()
    await page.getByRole('button', { name: button, exact: true }).click()
    await expect(page.locator('.el-message--error').last()).toContainText(
      '请补全必填项：输入图像。',
    )
  }
  await page.getByText('1:1 身份验证', { exact: true }).click()
  await page.getByRole('button', { name: '开始身份确认', exact: true }).click()
  await expect(page.locator('.el-message--error').last()).toContainText(
    '请补全必填项：输入图像、目标身份。',
  )
  await page.goto('/experiments')
  const form = page
    .locator('section.card')
    .filter({ has: page.getByRole('heading', { name: '创建消融实验', exact: true }) })
  await expect(form.getByRole('checkbox')).toHaveCount(4)
  for (const checkbox of await form.locator('label.el-checkbox').all()) await checkbox.click()
  await form.getByRole('button', { name: '开始批量评估', exact: true }).click()
  await expect(page.locator('.el-message--error').last()).toContainText(
    '请补全必填项：数据集、实验组。',
  )
  expect(mutations).toEqual([])
})
