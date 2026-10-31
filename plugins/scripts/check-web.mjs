import assert from 'node:assert/strict'
import { readFile, mkdir } from 'node:fs/promises'
import { execFileSync } from 'node:child_process'
import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE_PATH ? pathToFileURL(process.env.PLAYWRIGHT_MODULE_PATH).href : 'playwright')
const log = await readFile(process.env.DSH_LOG_PATH || path.join(root, 'output/dsh-web.log'), 'utf8')
const port = process.env.DSH_PORT || '5180'
const url = log.match(new RegExp(`http://127\\.0\\.0\\.1:${port}/\\?token=[^\\s\\u001b]+`))?.[0]
assert.ok(url, 'Missing local DSH browser authentication link')
const credentials = JSON.parse(execFileSync(process.env.PYTHON_BIN || 'python', ['-c', 'import json; from app.config import settings; print(json.dumps({"username":settings.ADMIN_USERNAME,"password":settings.ADMIN_PASSWORD}))'], {
  cwd: path.resolve(root, '../backend'), encoding: 'utf8',
}))
const output = path.join(root, 'output/ui')
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ headless: true, channel: process.env.BROWSER_CHANNEL || undefined })
const errors = []
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text().split('\n')[0]) })
  await page.goto(url)
  const notice = page.getByRole('button', { name: '继续', exact: true })
  await notice.waitFor({ timeout: 15000 }).catch(() => {})
  if (await notice.isVisible()) await notice.click()
  const later = page.getByRole('button', { name: '稍后配置', exact: true })
  await later.waitFor({ timeout: 5000 }).catch(() => {})
  if (await later.isVisible()) await later.click()
  console.log(JSON.stringify(await page.evaluate(() => ({ pluginInBoot: window.__DSH_BOOT__?.entries.some(entry => entry.id === 'dsh-teampilot') }))))
  await page.getByRole('button', { name: 'TeamPilot', exact: true }).waitFor({ timeout: 45000 })
  await page.getByRole('button', { name: 'TeamPilot', exact: true }).click()
  const panel = page.getByRole('region', { name: 'TeamPilot', exact: true })
  await panel.locator('.tp-login button, button[aria-label="退出账号"]').first().waitFor()
  if (await panel.getByRole('button', { name: '退出账号', exact: true }).isVisible()) {
    await panel.getByRole('button', { name: '退出账号', exact: true }).click()
  }
  await panel.getByLabel('用户名', { exact: true }).fill(credentials.username)
  await panel.getByLabel('密码', { exact: true }).fill(credentials.password)
  await panel.getByRole('button', { name: '登录', exact: true }).click()
  await panel.getByLabel('项目', { exact: true }).waitFor({ timeout: 20000 })
  await page.waitForFunction(() => document.querySelectorAll('.tp-compose select option').length > 1)
  let draft
  if (process.env.CHECK_DRAFT === '1') {
    const login = await page.request.post('http://127.0.0.1:8000/api/v1/auth/login', { data: credentials })
    assert.equal(login.status(), 200)
    const headers = { Authorization: `Bearer ${(await login.json()).access_token}` }
    const projectId = await panel.locator('select option').nth(1).getAttribute('value')
    const context = await (await page.request.get(`http://127.0.0.1:8000/api/v1/integrations/dsh/projects/${projectId}/context`, { headers })).json()
    const task = context.tasks[0]
    assert.ok(task, 'Draft review needs an existing task; it will never commit it')
    const create = await page.request.post('http://127.0.0.1:8000/api/v1/integrations/dsh/drafts', { headers, data: { payload: {
      kind: 'progress', project_id: projectId, revision: context.revision,
      updates: [{ task_id: task.id, progress_pct: task.progress_pct, note: 'DSH UI smoke draft; cancel without committing' }],
    } } })
    assert.equal(create.status(), 201)
    draft = await create.json()
    try {
      await panel.getByRole('button', { name: '刷新', exact: true }).click()
      await panel.getByRole('tab', { name: '草稿审阅', exact: true }).click()
      await panel.getByRole('navigation', { name: '草稿列表' }).getByRole('button').filter({ hasText: draft.id.slice(0, 8) }).click()
      await panel.locator('.tp-diff').waitFor()
      const approve = panel.getByRole('button', { name: '批准', exact: true })
      assert.equal(await approve.isDisabled(), true)
      await panel.getByLabel('确认此草稿内容').check()
      await approve.click()
      await panel.getByRole('navigation', { name: '草稿列表' }).getByText(`已批准 · ${draft.id.slice(0, 8)}`).waitFor()
      for (const width of [1440, 390]) {
        await page.setViewportSize({ width, height: 900 })
        assert.equal(await panel.evaluate(el => el.scrollWidth > el.clientWidth), false)
        await page.screenshot({ path: path.join(output, `dsh-review-${width}.png`) })
      }
      await panel.getByRole('button', { name: '取消草稿', exact: true }).click()
      await panel.getByRole('navigation', { name: '草稿列表' }).getByText(`已取消 · ${draft.id.slice(0, 8)}`).waitFor()
      const saved = await (await page.request.get(`http://127.0.0.1:8000/api/v1/integrations/dsh/drafts/${draft.id}`, { headers })).json()
      assert.equal(saved.state, 'cancelled')
      assert.equal(saved.result, null)
    } finally {
      // This mode only creates a draft record. It never invokes commit or changes a business task.
      await page.request.post(`http://127.0.0.1:8000/api/v1/integrations/dsh/drafts/${draft.id}/cancel`, { headers })
    }
  }
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 })
    const bounds = await panel.boundingBox()
    assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= width + 1)
    assert.equal(await panel.evaluate(el => el.scrollWidth > el.clientWidth), false, 'Panel horizontal overflow')
    await page.screenshot({ path: path.join(output, `dsh-${width}.png`) })
  }
  await panel.getByRole('button', { name: '退出账号', exact: true }).click()
  await panel.getByRole('button', { name: '登录', exact: true }).waitFor()
  assert.equal(await panel.getByLabel('密码', { exact: true }).inputValue(), '')
  assert.equal(await page.getByRole('dialog', { name: 'TeamPilot' }).count(), 0, 'No standalone overlay')
  assert.deepEqual(errors, [])
  console.log(JSON.stringify({ nativePanel: true, login: true, projectRead: true, draftReview: Boolean(draft), logout: true, viewports: [1440, 390], errors }))
} catch (error) {
  await browser.contexts()[0]?.pages()[0]?.screenshot({ path: path.join(output, 'dsh-failure.png') })
  // Never print the URL/session cookie or authentication payload.
  console.error(String(error).replace(/token=[^\s]+/g, 'token=[redacted]'))
  console.error(JSON.stringify({ pageErrors: errors }))
  process.exitCode = 1
} finally { await browser.close() }
