import { test, expect } from '@playwright/test'
import { resolve } from 'node:path'
const root = resolve(import.meta.dirname, '../..')

test('只选择增强算法，三种算法逐图计算参数并显示结果', async ({ page }) => {
  await page.goto('/enhance')
  await expect(page.getByRole('slider')).toHaveCount(0)
  await expect(page.getByRole('spinbutton')).toHaveCount(0)
  const cases = [
    ['gamma', 'Gamma 校正（低照度）', '03_低照度_Gamma', ['gamma']],
    ['clahe', 'CLAHE（逆光）', '01_逆光_CLAHE', ['clip_limit']],
    ['retinex', 'Retinex（光照不均）', '02_光照不均_Retinex', ['sigma', 'strength']],
  ] as const
  for (const [method, label, directory, parameters] of cases) {
    await page.locator('.method-select .el-select__wrapper').click()
    await page.getByRole('option', { name: label, exact: true }).click()
    await page
      .getByLabel('上传图片', { exact: true })
      .setInputFiles(root + `/work/browser-lighting-query/${directory}/多图测试参考/query.png`)
    const pending = page.waitForResponse((r) => r.url().endsWith('/api/enhance/process'))
    await page.getByRole('button', { name: '分析并增强', exact: true }).click()
    const response = await pending
    expect(response.ok()).toBe(true)
    const result = (await response.json()).data
    expect(result.parameter_mode).toBe('auto')
    expect(result.parameters.method).toBe(method)
    for (const parameter of parameters)
      expect(Number.isFinite(result.parameters[parameter])).toBe(true)
    await expect(page.locator('.result-panel .method-description')).toContainText('自动参数')
    await expect(page.getByRole('link', { name: /下载增强图像/ })).toBeVisible()
  }
  await page.screenshot({ path: root + '/work/automatic-enhancement.png', fullPage: true })
})
