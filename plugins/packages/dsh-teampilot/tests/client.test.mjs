import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { runInNewContext } from 'node:vm'
import { Context, Service } from '@deepseek-ai/cordis'

const require = createRequire(import.meta.url)

function loadClient() {
  let client
  const styles = new Set()
  const document = {
    createElement(tag) {
      assert.equal(tag, 'style')
      return { textContent: '', remove() { styles.delete(this) } }
    },
    head: { append(style) { styles.add(style) } },
  }
  runInNewContext(readFileSync(new URL('../lib/client.js', import.meta.url), 'utf8'), {
    window: {
      __ModuleLoader__: {
        load(module) {
          assert.equal(module.id, 'dsh-teampilot')
          // Native UI atoms are supplied by DSH's browser loader. This contract
          // test mounts registrations only; browser acceptance covers rendering.
          client = module.factory(id => id === '@deepseek-ai/dsh-client-ui-primitives' ? { Button: () => null } : id === 'react'
            ? { ...require('react'), useSyncExternalStore: (_subscribe, snapshot) => snapshot() } : require(id))
        },
      },
    },
    document,
    AbortController,
    console,
    setTimeout,
    clearTimeout,
  }, { filename: 'dsh-teampilot/lib/client.js' })
  assert.equal(typeof client?.apply, 'function')
  return { client, styles }
}

async function mount(t) {
  const { client, styles } = loadClient()
  const ctx = new Context()
  const tabs = []
  const slots = []
  const mounted = []
  const injections = []
  const subscribers = new Map()
  const notify = name => subscribers.get(name)?.forEach(callback => callback())
  const register = (records, definition, component) => {
    const record = { definition, component, live: true, disposed: 0 }
    records.push(record)
    return () => {
      if (!record.live) return
      record.live = false
      record.disposed++
    }
  }
  // Match SlotRegistry's public lifetime contract: prototype Service methods
  // trace this.ctx to the calling plugin and register effects on its fiber.
  // The seats are already declared in this fixture, so inject runs immediately.
  class SlotsFixture extends Service {
    inject(name, callback) {
      injections.push(name)
      return this.ctx.effect(callback, `slots.inject(${name})`)
    }
    register(definition, component) {
      return this.ctx.effect(() => {
        const dispose = register(slots, definition, component)
        notify(definition.name)
        return () => { dispose(); notify(definition.name) }
      }, 'slots.register()')
    }
    entriesOfSlot(name) {
      return slots.filter(record => record.live && record.definition.name === name).map(record => ({ options: record.definition }))
    }
    subscribe(name, callback) {
      if (!subscribers.has(name)) subscribers.set(name, new Set())
      subscribers.get(name).add(callback)
      return () => subscribers.get(name).delete(callback)
    }
  }
  new SlotsFixture(ctx, 'slots')
  const teampilot = {}
  const agentPresets = {}
  ctx.provide('remote', {
    $mount: async contribution => { mounted.push(contribution) },
    teampilot,
    agentPresets,
  })
  ctx.provide('remote.teampilot', teampilot)
  ctx.provide('remote.agentPresets', agentPresets)
  ctx.provide('sessions', {})
  ctx.provide('uiWorkspace', {})
  ctx.provide('sidebarRightTabs', {
    register: definition => register(tabs, definition),
  })
  ctx.provide('sidebarRight', {})
  ctx.provide('layout', {})
  ctx.provide('pluginNavigation', { openBundle() {} })
  const fiber = ctx.plugin(client)
  t.after(() => ctx.fiber.dispose())
  await fiber.inertia
  assert.equal(fiber.state, 2, 'The real Cordis client fiber must activate')
  return { ctx, fiber, styles, tabs, slots, mounted, injections }
}

test('built client registers the native TeamPilot page and a matching keyed body', async t => {
  const { tabs, slots, mounted, injections } = await mount(t)
  assert.equal(mounted.length, 1, 'The generated remote contribution must mount')
  assert.equal(tabs.length, 1, 'TeamPilot must join the official sidebar tab registry')
  const definition = tabs[0].definition
  assert.equal(definition.id, 'dsh-teampilot')
  assert.equal(definition.kind, 'teampilot')
  assert.equal(definition.priority ?? 'extension', 'extension')
  assert.equal(definition.patterns?.length ?? 0, 0, 'TeamPilot is a page rather than a resource viewer')
  assert.equal(definition.title(), 'TeamPilot')
  assert.equal(definition.guide.length, 1)
  assert.equal(definition.guide[0].title(), 'TeamPilot')
  assert.ok(definition.guide[0].id, 'The native guide entry has a stable identity')
  assert.ok(Number.isFinite(definition.guide[0].order))
  assert.ok(definition.guide[0].icon, 'The entry supplies its business icon')
  assert.ok(injections.includes('sidebar.right.pane.tab'))
  const bodies = slots.filter(slot => slot.definition.name === 'sidebar.right.pane.tab')
  assert.equal(bodies.length, 1)
  assert.equal(bodies[0].definition.key, definition.id, 'The official keyed seat dispatches by tab implementation id')
  assert.equal(typeof bodies[0].component, 'function')
})

test('native plugin-manager navigation does not hide the business launcher; actual shared registration does', async t => {
  const { ctx, slots } = await mount(t)
  const launcher = slots.find(slot => slot.definition.name === 'sidebar.footer.action' && slot.definition.id === 'teampilot')
  assert.ok(launcher.component({ wide: true }), 'Built-in openBundle navigation is not a shared business entry')
  const removeShared = ctx.slots.register({ name: 'sidebar.footer.action', id: 'plugin-navigation' }, () => null)
  assert.equal(launcher.component({ wide: true }), null, 'Only a real shared navigation slot suppresses duplicate business entries')
  removeShared()
  assert.ok(launcher.component({ wide: true }), 'Removing shared navigation restores the fallback immediately')
})

test('native client contributes no overlay and releases its registrations on unload', async t => {
  const { fiber, tabs, slots, styles, injections } = await mount(t)
  assert.equal(injections.includes('shell.overlay'), false, 'Business content belongs in the native sidebar')
  assert.equal(slots.some(slot => slot.definition.name === 'shell.overlay'), false)
  assert.equal(styles.size, 1)
  assert.equal(tabs.length, 1)
  const body = slots.find(slot => slot.definition.name === 'sidebar.right.pane.tab')
  assert.ok(body)
  await fiber.dispose()
  assert.equal(tabs[0].live, false)
  assert.equal(tabs[0].disposed, 1)
  assert.equal(body.live, false)
  assert.equal(body.disposed, 1)
  assert.ok(slots.every(slot => !slot.live && slot.disposed === 1), 'Every native seat, including the fallback launcher, releases once')
  assert.equal(styles.size, 0)
})
