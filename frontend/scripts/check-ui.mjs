import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { mkdir } from 'node:fs/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { resolve } from 'node:path'

const modulePath = process.env.PLAYWRIGHT_MODULE_PATH
const { chromium } = await import(modulePath ? pathToFileURL(modulePath).href : 'playwright')
const base = process.env.BASE_URL || 'http://127.0.0.1:5173'
const checkAudit = process.env.CHECK_AUDIT !== '0'
const backend = fileURLToPath(new URL('../../backend', import.meta.url))
const credentials = JSON.parse(execFileSync(process.env.PYTHON_BIN || 'python', ['-c', 'import json; from app.config import settings; print(json.dumps({"username":settings.ADMIN_USERNAME,"password":settings.ADMIN_PASSWORD}))'], { cwd: backend, encoding: 'utf8' }))
const browser = await chromium.launch({ headless: true, channel: process.env.BROWSER_CHANNEL || undefined })
const output = resolve('output/ui')
await mkdir(output, { recursive: true })
try {
  const context = await browser.newContext()
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto(`${base}/login`)
    await page.locator('.login-btn').waitFor()
    await page.screenshot({ path: `${output}/login-${width}.png` })
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
  }
  const login = await context.request.post(`${base}/api/v1/auth/login`, { data: credentials })
  assert.equal(login.status(), 200)
  const tokens = await login.json()
  await page.evaluate(tokens => { localStorage.setItem('token', tokens.access_token); localStorage.setItem('refresh_token', tokens.refresh_token) }, tokens)
  const projectsResponse = await context.request.get(`${base}/api/v1/projects`, { headers: { Authorization: `Bearer ${tokens.access_token}` } })
  assert.equal(projectsResponse.status(), 200)
  const projects = (await projectsResponse.json()).items
  const project = projects.find(item => item.task_count > 0) || projects[0]
  const paths = ['/dashboard', '/projects', '/personnel', '/settings']
  if (project) paths.push(`/projects/${project.id}`, `/projects/${project.id}/board`, `/projects/${project.id}/tasks`)
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 })
    for (const path of paths) {
      await page.goto(`${base}${path}`)
      await page.getByText('实时同步', { exact: true }).waitFor()
      await page.waitForFunction(() => !document.querySelector('.el-loading-mask'))
      const name = path.includes('/board') ? 'board' : path.includes('/tasks') ? 'tasks' : path.startsWith('/projects/') ? 'project-detail' : path.split('/')[1]
      await page.screenshot({ path: `${output}/${name}-${width}.png`, fullPage: true })
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `page overflow: ${path}, ${width}`)
      if (width === 390) {
        await page.getByRole('button', { name: '打开导航' }).click()
        await page.getByRole('navigation', { name: '主导航' }).waitFor()
        await page.keyboard.press('Escape')
      }
      if (checkAudit && path.endsWith('/board')) {
        if (width === 390 && !(await page.locator('.task-card:visible').count())) {
          const title = await page.locator('.board-column').evaluateAll(columns => columns.find(column => column.querySelector('.task-card'))?.querySelector('.column-title')?.textContent)
          if (title) await page.locator('.board-status-tabs .el-radio-button').filter({ hasText: title }).click()
        }
        if (await page.locator('.task-card:visible').count()) {
          await page.locator('.task-card:visible').first().click()
          await page.locator('.task-audit h4').waitFor()
          await page.waitForFunction(() => !document.querySelector('.task-audit .el-loading-mask'))
          assert.equal(await page.locator('.task-audit').getByText('加载失败', { exact: false }).count(), 0)
          await page.locator('.el-drawer:visible').evaluate(async drawer => {
            await Promise.all(drawer.getAnimations().map(animation => animation.finished.catch(() => {})))
          })
          const bounds = await page.locator('.el-drawer:visible').boundingBox()
          assert.ok(bounds.x >= -1 && bounds.x + bounds.width <= width + 1, `drawer overflow: ${width}, ${JSON.stringify(bounds)}`)
          await page.screenshot({ path: `${output}/task-detail-${width}.png` })
          await page.keyboard.press('Escape')
        }
      }
    }
  }
  assert.deepEqual(errors, [])
  console.log(JSON.stringify({ pages: paths.length, viewports: [1440, 390], auditChecked: checkAudit, errors, output }, null, 2))
} finally { await browser.close() }
