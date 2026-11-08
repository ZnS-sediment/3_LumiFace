import { test, expect } from '@playwright/test'
import { directoryFixture } from './helpers/directory'
import { resolve } from 'node:path'

const root = resolve(import.meta.dirname, '../..')

test('系统目录选择自动填写完整路径与照片，取消保留与错误重试，仅保留系统选择', async ({ page }) => {
  const fullPath = String.raw`C:\Users\演示\Downloads\browser-batch-identities`
  const selection = await directoryFixture(page, root + '/work/browser-batch-identities', fullPath)
  const rawReads: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/photos/') && !request.url().includes('?preview=true'))
      rawReads.push(request.url())
  })
  let calls = 0
  await page.route('**/api/system/directory-picker', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ json: { data: { available: true } } })
      return
    }
    expect(route.request().headers()['x-lumiface-picker']).toBe('1')
    calls++
    if (calls === 1) await route.fulfill({ json: { data: selection } })
    else if (calls === 2) await route.fulfill({ json: { data: null } })
    else if (calls === 3) await route.fulfill({ status: 400, json: { message: '目录无法读取' } })
    else await route.fulfill({ json: { data: selection } })
  })
  await page.goto('/persons')
  await page.getByRole('button', { name: '批量导入身份', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '批量导入身份', exact: true })
  await dialog.getByRole('button', { name: '选择照片根目录', exact: true }).click()
  await expect(dialog.getByRole('status')).toContainText(fullPath)
  await expect(dialog.getByRole('status')).toContainText('3 人 · 4 张照片')
  await expect(dialog.getByRole('textbox', { name: '照片根目录完整路径' })).toHaveCount(0)
  await expect(dialog.getByRole('button', { name: '补全路径', exact: true })).toHaveCount(0)
  await expect(dialog.getByAltText('参考照片预览')).toHaveCount(3)
  expect(rawReads).toEqual([])
  await dialog.getByRole('button', { name: '重新选择', exact: true }).click()
  await expect.poll(() => calls).toBe(2)
  await expect(dialog.getByRole('status')).toContainText(fullPath)
  await dialog.getByRole('button', { name: '重新选择', exact: true }).click()
  await expect(page.locator('.el-message--error')).toContainText('目录无法读取')
  await expect(dialog.getByRole('status')).toContainText(fullPath)
  await expect(dialog.getByRole('button', { name: '开始导入', exact: true })).toBeEnabled()
  await dialog.getByRole('button', { name: '重新选择', exact: true }).click()
  await expect.poll(() => calls).toBe(4)
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(dialog.getByRole('status')).toContainText(fullPath)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
    true,
  )
  await expect(dialog.getByRole('button', { name: '浏览器选择', exact: true })).toHaveCount(0)
  await expect(dialog.locator('input[type=file]')).toHaveCount(0)
  await dialog.getByRole('button', { name: '关闭', exact: true }).click()
  await expect(dialog).toBeHidden()
})

test('系统目录选择不可用时说明原因，不退回无法获取完整路径的浏览器选择', async ({ page }) => {
  await page.route('**/api/system/directory-picker', (route) =>
    route.fulfill({ json: { data: { available: false } } }),
  )
  await page.goto('/persons')
  await page.getByRole('button', { name: '批量导入身份', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '批量导入身份', exact: true })
  await expect(dialog.getByRole('button', { name: '选择照片根目录', exact: true })).toBeDisabled()
  await expect(dialog.getByRole('alert')).toContainText('系统目录选择不可用')
  await expect(dialog.getByRole('button', { name: '浏览器选择', exact: true })).toHaveCount(0)
  await expect(dialog.locator('input[type=file]')).toHaveCount(0)
})
