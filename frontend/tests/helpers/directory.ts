import type { Page, Locator } from '@playwright/test'
import { readdir, readFile } from 'node:fs/promises'
import { basename } from 'node:path'
import { randomUUID } from 'node:crypto'

// Replace only the OS selection and its lazy disk reads; real registration still runs.
export async function directoryFixture(page: Page, directory: string, display = directory) {
  const token = randomUUID()
  const files = []
  const buffers: Buffer[] = []
  for (const person of await readdir(directory)) {
    for (const name of await readdir(directory + '/' + person)) {
      const buffer = await readFile(directory + '/' + person + '/' + name)
      files.push({
        path: basename(directory) + '/' + person + '/' + name,
        size: buffer.length,
        url: `/api/system/directory-picker/${token}/photos/${buffers.length}`,
        type: 'image/png',
      })
      buffers.push(buffer)
    }
  }
  await page.route(`**/api/system/directory-picker/${token}/photos/*`, (route) => {
    const index = Number(new URL(route.request().url()).pathname.split('/').pop())
    return route.fulfill({ body: buffers[index], contentType: 'image/png' })
  })
  await page.route(`**/api/system/directory-picker/${token}`, (route) =>
    route.fulfill({ json: { data: true } }),
  )
  return { path: display, token, files }
}

export async function mockDirectoryPicker(page: Page) {
  let selection: unknown = null
  await page.route('**/api/system/directory-picker', async (route) => {
    await route.fulfill({
      json: { data: route.request().method() === 'GET' ? { available: true } : selection },
    })
  })
  return async (directory: string, button: Locator, names?: string[]) => {
    const selected = await directoryFixture(page, directory)
    if (names) selected.files = selected.files.filter((file) => names.includes(file.path.split('/')[1]))
    selection = selected
    await button.click()
  }
}
