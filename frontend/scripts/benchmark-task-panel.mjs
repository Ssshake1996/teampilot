import assert from 'node:assert/strict'
import { pathToFileURL } from 'node:url'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const playwrightModule = process.env.PLAYWRIGHT_MODULE_PATH
const { chromium } = await import(playwrightModule ? pathToFileURL(playwrightModule).href : 'playwright')
const baseUrl = process.env.BASE_URL || 'http://127.0.0.1:5173'
const taskCount = Number(process.env.TASK_COUNT || 200)
const userCount = Number(process.env.USER_COUNT || 100)
const checkInteractions = process.env.CHECK_INTERACTIONS === '1'
const readOnly = process.env.READ_ONLY === '1'
assert.ok(Number.isInteger(taskCount) && taskCount > 0, 'TASK_COUNT must be a positive integer')
assert.ok(Number.isInteger(userCount) && userCount > 0, 'USER_COUNT must be a positive integer')
if (checkInteractions && !readOnly) assert.ok(taskCount >= 40 && userCount >= 2, 'admin interaction checks require at least 40 tasks and 2 users')
const projectId = 'performance-project'
const users = Array.from({ length: userCount }, (_, i) => ({
  id: `user-${i}`, username: `user${i}`, full_name: `Member ${i}`, role: i ? 'member' : 'admin',
}))
const project = {
  id: projectId, name: 'Task Panel Benchmark', status: 'active', task_count: taskCount,
  completed_count: 0, member_count: userCount, owner_id: users[0].id,
  owner_name: users[0].full_name, contact_names: [users[0].full_name],
  start_date: '2026-01-01', end_date: '2027-12-31',
}
const task = (i, parentId = null) => ({
  id: `task-${i}`, project_id: projectId, title: `Task ${i}`, status: 'in_progress', priority: 'medium',
  parent_task_id: parentId, assignee_ids: [users[0].id], assignee_name: users[0].full_name,
  estimated_hours: 8, weight: parentId ? 1 / 19 : 1, progress_pct: 25,
  created_at: '2026-01-01T00:00:00', start_date: '2026-01-01', deadline: '2027-12-31',
  subtask_done: 0, subtask_total: parentId ? 0 : Math.min(19, taskCount - i - 1),
  is_deleted: false, latest_note: 'Benchmark progress note', children: [],
})
const roots = []
for (let i = 0; i < taskCount; i += 20) {
  const root = task(i)
  root.children = Array.from({ length: Math.min(19, taskCount - i - 1) }, (_, j) => task(i + j + 1, root.id))
  roots.push(root)
}

const browser = await chromium.launch({ headless: true, channel: process.env.BROWSER_CHANNEL || undefined })
let page
let phase = 'expand'
try {
  page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  page.setDefaultTimeout(10000)
  const errors = []
  let treeRequests = 0
  const mutations = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.routeWebSocket('**/ws', socket => socket.onMessage(() => {}))
  await page.addInitScript(() => {
    localStorage.setItem('token', 'benchmark-token')
    window.__longTasks = []
    new PerformanceObserver((entries) => {
      window.__longTasks.push(...entries.getEntries().map((entry) => entry.duration))
    }).observe({ type: 'longtask', buffered: true })
  })
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    let response
    if (path.endsWith('/auth/me')) response = { ...users[0], role: readOnly ? 'member' : 'admin' }
    else if (path.endsWith('/permissions/me')) response = { permissions: [] }
    else if (path.endsWith('/task-tree')) { response = roots; treeRequests++ }
    else if (path.endsWith('/projects')) response = { items: [project], total: 1, page: 1, page_size: 100 }
    else if (path.endsWith(`/projects/${projectId}`)) response = project
    else if (path.endsWith('/users')) {
      const params = new URL(route.request().url()).searchParams
      const size = Number(params.get('page_size') || 50)
      const number = Number(params.get('page') || 1)
      response = { items: users.slice((number - 1) * size, number * size), total: users.length, page: number, page_size: size }
    }
    else if (route.request().method() === 'PATCH') {
      const body = route.request().postDataJSON()
      mutations.push({ path, body })
      if (path.endsWith('/tasks/reorder')) {
        const byOrder = new Map(body.map((item) => [item.task_id, item.sort_order]))
        const moved = roots.flatMap((root) => [root, ...root.children]).find((row) => row.id === body[0].task_id)
        const group = moved.parent_task_id ? roots.find((root) => root.id === moved.parent_task_id).children : roots
        group.sort((a, b) => byOrder.get(a.id) - byOrder.get(b.id))
        response = {}
      } else {
        response = roots.flatMap((root) => [root, ...root.children]).find((row) => row.id === path.split('/')[4])
        Object.assign(response, body, { updated_at: new Date().toISOString() })
        if (body.assignee_ids) response.assignee_name = body.assignee_ids.map((id) => users.find((user) => user.id === id).full_name).join(', ')
      }
    }
    else response = []
    await route.fulfill({ json: response })
  })
  await page.goto(`${baseUrl}/projects`)
  await page.locator('.prow').waitFor()
  await page.locator('.el-loading-mask').waitFor({ state: 'hidden' })
  const expand = async () => {
    await page.evaluate(() => { window.__expandStart = performance.now(); window.__longTasks = []; document.querySelector('.prow').click() })
    await page.locator('.trow').first().waitFor({ timeout: 120000 })
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))))
    return page.evaluate(() => ({
      expandMs: Math.round(performance.now() - window.__expandStart),
      renderedRows: document.querySelectorAll('.trow .task-link').length,
      rowSlots: document.querySelectorAll('.trow').length,
      domNodes: document.querySelectorAll('*').length,
      assigneeSelects: document.querySelectorAll('.isel').length,
      longestTaskMs: Math.round(Math.max(0, ...window.__longTasks)),
    }))
  }
  const first = await expand()
  await page.locator('.prow').click()
  await page.locator('.trow').first().waitFor({ state: 'hidden' })
  const cached = await expand()
  assert.equal(treeRequests, 1, 'reopening a loaded project must reuse the task tree')
  if (checkInteractions) {
    const row = (id) => page.locator(`[data-task-id="task-${id}"]`)
    const viewport = page.locator('.task-list-viewport')
    if (taskCount > 100) {
      await viewport.evaluate((element) => { element.scrollTop = element.scrollHeight })
      await row(taskCount - 1).locator('.task-link').waitFor()
      assert.ok(await row(taskCount - 1).locator('.task-link').isVisible(), 'the last task must render after scrolling')
      const dimensions = await row(taskCount - 1).evaluate((element) => ({ height: element.getBoundingClientRect().height, overflow: element.scrollHeight > element.clientHeight }))
      assert.equal(dimensions.height, 44, 'virtual row height must remain stable')
      assert.equal(dimensions.overflow, false, 'row content must fit its reserved height')
      await viewport.evaluate((element) => { element.scrollTop = 0 })
      await row(0).locator('.task-link').waitFor()
    }
    if (taskCount > 1) {
      await row(0).locator('.task-collapse-toggle').click()
      await page.waitForFunction((count) => document.querySelectorAll('.trow').length === count, taskCount - Math.min(19, taskCount - 1))
      await row(0).locator('.task-collapse-toggle').click()
      await page.waitForFunction((count) => document.querySelectorAll('.trow').length === count, taskCount)
    }
    if (readOnly) {
      assert.equal(await page.locator('.task-inline-trigger').count(), 0, 'read-only users must not see edit controls')
      assert.equal(await page.locator('.task-drag-handle').count(), 0, 'read-only users must not see drag controls')
    } else {
      await row(0).locator('.col-who .task-inline-trigger').click()
      await page.locator('.task-inline-editor .isel').waitFor()
      assert.equal(await page.locator('.isel').count(), 1, 'only the active assignee editor should be mounted')
      await page.locator('.task-inline-editor .el-select__wrapper').click()
      const assigned = page.waitForResponse((response) => response.url().endsWith('/tasks/task-0/assign'))
      await page.getByRole('option', { name: 'Member 1', exact: true }).click()
      await assigned
      await page.waitForFunction(() => document.querySelector('[data-task-id="task-0"] .col-who').textContent.includes('Member 1'))
      await page.keyboard.press('Escape')
      await page.locator('.task-inline-editor').waitFor({ state: 'hidden' })

      for (const [id, column, field, value] of [
        [0, 'col-hrs', 'estimated_hours', '9.5'],
        [1, 'col-weight', 'weight', '0.2'],
        [0, 'col-sd', 'start_date', '2026-02-03'],
        [0, 'col-ed', 'deadline', '2027-08-09'],
      ]) {
        phase = `edit ${field}`
        await row(id).locator(`.${column} .task-inline-trigger`).click()
        const input = page.locator('.task-inline-editor input').first()
        await input.fill(value)
        const updated = page.waitForResponse((response) => response.url().endsWith(`/tasks/task-${id}`) && response.request().method() === 'PATCH')
        await input.press('Enter')
        await page.keyboard.press('Tab')
        await updated
        await page.waitForFunction(({ id, column, value }) => document.querySelector(`[data-task-id="task-${id}"] .${column}`)?.textContent.includes(value), { id, column, value })
        await page.keyboard.press('Escape')
      }

      if (taskCount > 100) {
        phase = 'refresh without losing scroll position'
        const id = Math.floor(taskCount / 40) * 20 + 1
        await viewport.evaluate((element, index) => { element.scrollTop = index * 44 }, id)
        await row(id).locator('.col-weight .task-inline-trigger').waitFor()
        const previousTop = await viewport.evaluate((element) => element.scrollTop)
        await row(id).locator('.col-weight .task-inline-trigger').click()
        const input = page.locator('.task-inline-editor input').first()
        await input.fill('0.3')
        const refreshed = page.waitForResponse((response) => response.url().endsWith('/task-tree'))
        await input.press('Enter')
        await refreshed
        await page.waitForFunction((id) => document.querySelector(`[data-task-id="task-${id}"] .col-weight`)?.textContent.includes('0.3'), id)
        assert.equal(await viewport.evaluate((element) => element.scrollTop), previousTop, 'refreshing weights must preserve the current scroll position')
        await page.locator('.ttree .el-loading-mask').waitFor({ state: 'hidden' })
        await viewport.evaluate((element) => { element.scrollTop = 0 })
        await row(0).locator('.task-link').waitFor()
      }

      const startDrag = async (source) => {
        await page.waitForFunction(() => Array.from(document.querySelectorAll('.task-row-slot')).every((element) => !element.animated))
        await source.hover()
        const from = await source.boundingBox()
        const startX = from.x + from.width / 2
        const startY = from.y + from.height / 2
        await page.mouse.move(startX, startY)
        await page.mouse.down()
        await page.mouse.move(startX + 10, startY + 10)
        await page.mouse.move(startX + 15, startY + 15)
        await page.waitForFunction(() => document.querySelector('.ghost-row'))
      }
      const dropOn = async (target, position = { x: 30, y: 5 }) => {
        const to = await target.boundingBox()
        const saved = page.waitForResponse((response) => response.url().endsWith('/tasks/reorder'))
        await page.mouse.move(to.x + position.x, to.y + position.y)
        await page.mouse.move(to.x + position.x + 1, to.y + position.y)
        await page.mouse.up()
        await saved
      }
      const drag = async (source, target) => { await startDrag(source); await dropOn(target) }
      phase = 'sibling drag'
      await drag(row(2).locator('.task-drag-handle'), row(1))
      await page.waitForFunction(() => document.querySelectorAll('.trow')[1]?.dataset.taskId === 'task-2')
      assert.equal(await page.locator('.trow').count(), taskCount, 'sorting must preserve every task')

      if (taskCount > 100) {
        phase = 'drag across render window'
        await startDrag(row(2).locator('.task-drag-handle'))
        await viewport.evaluate((element) => { element.scrollTop = 8 * 44 })
        await row(19).locator('.task-link').waitFor()
        await dropOn(row(19), { x: 30, y: 40 })
        await page.waitForFunction(() => document.querySelectorAll('.trow')[19]?.dataset.taskId === 'task-2')
        await viewport.evaluate((element) => { element.scrollTop = 0 })
        await row(0).locator('.task-link').waitFor()
      }

      await row(0).locator('.task-collapse-toggle').click()
      phase = 'collapsed parent drag'
      await drag(row(20).locator('.task-drag-handle'), row(0))
      await page.waitForFunction(() => document.querySelector('.trow')?.dataset.taskId === 'task-20')
      await row(0).locator('.task-collapse-toggle').click()
      assert.equal(await page.locator('.trow').count(), taskCount, 'sorting a collapsed parent must preserve hidden descendants')
      const statuses = await page.locator('.trow .col-act .el-tag').allTextContents()
      assert.ok(statuses.length > 0 && statuses.every((status) => status.trim() === '\u8fdb\u884c\u4e2d'), 'sorting must preserve the task status display')
    }
    const screenshots = []
    for (const [width, height] of [[1440, 900], [390, 844]]) {
      await page.setViewportSize({ width, height })
      const path = join(tmpdir(), `teampilot-task-panel-${width}-${readOnly ? 'readonly' : 'admin'}.png`)
      await page.screenshot({ path, fullPage: true })
      screenshots.push(path)
    }
    console.log(JSON.stringify({ interactions: 'passed', mutationCount: mutations.length, screenshots }, null, 2))
  }
  assert.deepEqual(errors, [], 'the task panel must not produce browser errors')
  console.log(JSON.stringify({ taskCount, userCount, first, cached, treeRequests, errors }, null, 2))
} catch (error) {
  const screenshot = join(tmpdir(), 'teampilot-task-panel-failure.png')
  await page?.screenshot({ path: screenshot, fullPage: true })
  console.error(JSON.stringify({ phase, screenshot, rowOrder: await page?.locator('.trow').evaluateAll((rows) => rows.slice(0, 25).map((row) => row.dataset.taskId)) }))
  throw error
} finally {
  await browser.close()
}
