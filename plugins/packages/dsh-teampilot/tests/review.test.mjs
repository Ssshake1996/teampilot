import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { runInNewContext } from 'node:vm'

const require = createRequire(import.meta.url)
let client
runInNewContext(readFileSync(new URL('../lib/client.js', import.meta.url), 'utf8'), {
  window: { __ModuleLoader__: { load(module) {
    client = module.factory(id => id === '@deepseek-ai/dsh-client-ui-primitives' ? {} : require(id))
  } } }, AbortController, console, setTimeout, clearTimeout,
})

test('review uses named business fields and highlights only changed values without altering payloads', () => {
  const before = { assignee_ids: ['a'], estimated_hours: '8', priority: 'high', progress_pct: 20 }
  const after = { assignee_ids: ['b'], estimated_hours: 4, priority: 'high', progress_pct: 40 }
  const rows = client.buildReviewRows(before, after, { a: '赵磊', b: '刘洋' })
  assert.equal(rows[0].label, '负责人')
  assert.equal(rows[0].before, '赵磊')
  assert.equal(rows[0].after, '刘洋')
  assert.equal(rows[0].changed, true)
  assert.equal(rows.find(row => row.key === 'priority').after, '高')
  assert.equal(rows.find(row => row.key === 'priority').changed, false)
  assert.equal(rows.find(row => row.key === 'estimated_hours').after, '4 小时')
  assert.equal(rows.find(row => row.key === 'progress_pct').after, '40%')
  assert.equal(before.assignee_ids[0], 'a', 'Names are presentation only; the approval payload retains exact UUIDs')
  assert.equal(client.buildReviewRows(null, { title: '新增任务' })[0].before, '新增')
  const normalized = client.buildReviewRows({ priority: 'TaskPriority.HIGH', estimated_hours: '4.00', note: 'high' }, { priority: 'high', estimated_hours: 4, note: 'high' })
  assert.equal(normalized[0].changed, false)
  assert.equal(normalized[1].changed, false)
  assert.equal(normalized[2].after, 'high', 'Free-form notes must never be translated as priority enums')
})

test('approval distinguishes draft expiry, short approval expiry and lost Host credentials', () => {
  const now = Date.parse('2026-10-31T10:00:00Z')
  const draft = { state: 'approved', expires_at: '2026-10-31T11:00:00Z', approval_expires_at: '2026-10-31T10:05:00Z', approval_available: true }
  let state = client.approvalStatus(draft, now)
  assert.equal(state.ready, true)
  assert.equal(state.mayApprove, false)
  assert.match(state.label, /尚未写入/)
  state = client.approvalStatus(draft, now + 300000)
  assert.equal(state.ready, false)
  assert.equal(state.mayApprove, true)
  assert.match(state.label, /批准已过期/)
  state = client.approvalStatus({ ...draft, approval_available: false }, now)
  assert.match(state.label, /已无批准凭据/)
  assert.equal(state.mayApprove, true)
  state = client.approvalStatus(draft, now + 3600000)
  assert.equal(state.mayApprove, false)
  assert.match(state.label, /草稿已过期/)
  assert.equal(client.approvalStatus({ ...draft, state: 'committed' }, now).ready, false)
})

test('unfinished input survives reload per account and server without persisting approval or password', () => {
  const store = new Map()
  const storage = { getItem: key => store.get(key) ?? null, setItem: (key, value) => store.set(key, value) }
  const key = client.panelStorageKey('https://team.example', 'alice')
  client.savePanelState(storage, key, { projectId: 'p1', projectName: '项目一', prompt: '待提交需求', view: 'drafts',
    selected: 'd1', sessionId: 'session1', password: 'private-password', confirmation_token: 'approval-secret' })
  const restored = client.readPanelState(storage, key)
  assert.equal(restored.prompt, '待提交需求')
  assert.equal(restored.projectName, '项目一')
  assert.equal(restored.view, 'drafts')
  assert.equal(restored.selected, 'd1')
  assert.equal(restored.sessionId, 'session1')
  assert.equal(store.get(key).includes('private-password'), false)
  assert.equal(store.get(key).includes('approval-secret'), false)
  assert.equal(client.readPanelState(storage, client.panelStorageKey('https://team.example', 'bob')).prompt, '')
  assert.equal(client.readPanelState(storage, client.panelStorageKey('https://other.example', 'alice')).prompt, '')
  storage.setItem(key, 'broken JSON')
  assert.equal(client.readPanelState(storage, key).prompt, '')
  assert.doesNotThrow(() => client.savePanelState({ setItem() { throw Error('quota') } }, key, restored))
})

test('project pagination and filtering keep the exact selected project visible', () => {
  const selected = { id: 'first-page-id', name: '原选项目' }
  const page = [{ id: 'second-page-id', name: '第二页项目' }]
  const options = client.projectOptions(page, selected, '第二页')
  assert.equal(options[0].id, selected.id)
  assert.equal(options[0].name, selected.name)
  assert.equal(options.length, 2)
  assert.equal(client.projectOptions(page, page[0], '').length, 1)
  assert.match(client.commitInstruction('draft-123'), /draft-123/)
  assert.match(client.commitInstruction('draft-123'), /DSH 原生审批/)
})
