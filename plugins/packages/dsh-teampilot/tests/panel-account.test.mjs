import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { runInNewContext } from 'node:vm'

const require = createRequire(import.meta.url)
async function panelHarness() {
  const cells = [], dependencies = [], effects = []
  let cursor = 0, component, client, currentUser = 'alice', rejectReads = false, switchOnRead = '', statusReads = 0
  const hooks = { ...require('react'),
    useId: () => 'test-pane',
    useState(initial) {
      const index = cursor++
      if (!(index in cells)) cells[index] = initial
      return [cells[index], value => { cells[index] = typeof value === 'function' ? value(cells[index]) : value }]
    },
    useRef(initial) {
      const index = cursor++
      if (!(index in cells)) cells[index] = { current: initial }
      return cells[index]
    },
    useEffect(effect, deps) {
      const index = cursor++
      if (!dependencies[index] || deps.some((value, i) => !Object.is(value, dependencies[index][i]))) {
        dependencies[index] = deps; effects.push(effect)
      }
    },
  }
  runInNewContext(readFileSync(new URL('../lib/client.js', import.meta.url), 'utf8'), {
    window: { localStorage: { getItem: () => null, setItem() {} }, __ModuleLoader__: { load(module) {
      client = module.factory(id => id === 'react' ? hooks : id === '@deepseek-ai/dsh-client-ui-primitives' ? {} : require(id))
    } } },
    document: { createElement: () => ({ remove() {} }), head: { append() {} } },
    AbortController, console, setTimeout, clearTimeout, setInterval: () => 0, clearInterval() {},
  })
  const ok = value => ({ ok: true, value })
  const ctx = {
    remote: { $mount: async () => {}, teampilot: {
      status: async () => { statusReads++; return ok({ connected: true, username: currentUser, baseUrl: 'https://team.example', webUrl: 'https://team.example' }) },
      read: async request => {
        if (switchOnRead) { currentUser = switchOnRead; switchOnRead = '' }
        return rejectReads ? { ok: false, error: { message: 'read unavailable' } } : ok({ json: JSON.stringify({
        items: request.resource === 'projects' ? [{ id: `${currentUser}-project`, name: `${currentUser} private project` }] : [{ id: `${currentUser}-draft`, state: 'pending', expires_at: '2099-01-01', payload: { kind: 'progress' } }],
        total: 1, queried_at: '2026-10-31T10:00:00Z',
      }) }) },
    } },
    inject(keys, callback) { if (!keys.includes('pluginNavigation')) callback(ctx) },
    effect(fn) { return fn() },
    slots: { entriesOfSlot: () => [], subscribe: () => () => {}, inject(_seat, callback) { callback() }, register(definition, value) { if (definition.name === 'sidebar.right.pane.tab') component = value; return () => {} } },
    sidebarRightTabs: { register: () => () => {} },
  }
  await client.apply(ctx)
  function render() {
    cursor = 0
    const tree = component({ sessionId: 'session-current' })
    while (effects.length) effects.shift()()
    return tree
  }
  function find(element, predicate) {
    if (Array.isArray(element)) { for (const item of element) { const found = find(item, predicate); if (found) return found } }
    else if (element && typeof element === 'object') {
      if (predicate(element)) return element
      return find(element.props?.children, predicate)
    }
  }
  const tick = () => new Promise(resolve => setImmediate(resolve))
  return { render, find, tick, cells, setUser: value => { currentUser = value }, rejectReads: () => { rejectReads = true },
    switchOnNextRead: value => { switchOnRead = value }, statusCount: () => statusReads }
}

test('a failed first read after switching Host account clears the previous account lists', async () => {
  const f = await panelHarness()
  const { render, find, tick, cells } = f
  render(); await tick(); await tick()
  let tree = render()
  assert.ok(find(tree, item => item.type === 'option' && item.props.value === 'alice-project'))
  f.setUser('bob'); f.rejectReads()
  find(tree, item => item.props?.['aria-label'] === '刷新').props.onClick()
  await tick(); await tick()
  tree = render()
  assert.equal(find(tree, item => item.type === 'option' && item.props.value === 'alice-project'), undefined)
  const tabs = find(tree, item => item.props?.label === 'TeamPilot 功能')
  tabs.props.onChange('drafts')
  await tick(); await tick()
  tree = render()
  assert.equal(find(tree, item => item.props?.children === 'alice private project'), undefined)
  assert.equal(find(tree, item => item.props?.children === 'alice-draft'), undefined)
  assert.equal(cells.some(value => Array.isArray(value) && value.some(item => item?.id === 'alice-draft')), false)
})

test('a Host account switch between status and reads discards both results without recursive retries', async () => {
  const f = await panelHarness()
  f.switchOnNextRead('bob')
  f.render(); await f.tick(); await f.tick()
  const tree = f.render()
  assert.equal(f.statusCount(), 2, 'One initial status and one final identity check; no unbounded retry loop')
  assert.equal(f.find(tree, item => item.type === 'option' && item.props.value === 'bob-project'), undefined)
  assert.equal(f.cells.some(value => Array.isArray(value) && value.some(item => item?.id === 'bob-draft')), false)
  assert.ok(f.find(tree, item => item.type === 'p' && String(item.props?.children).includes('读取期间账号发生变化')))
})
