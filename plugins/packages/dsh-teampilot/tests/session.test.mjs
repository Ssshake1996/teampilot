import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { runInNewContext } from 'node:vm'
import { Context } from '@deepseek-ai/cordis'

const require = createRequire(import.meta.url)

function loadStartConversation() {
  let client
  runInNewContext(readFileSync(new URL('../lib/client.js', import.meta.url), 'utf8'), {
    window: {
      __ModuleLoader__: {
        load(module) {
          assert.equal(module.id, 'dsh-teampilot')
          // Controller tests never render. Native atoms are loaded by DSH in
          // the separate real-browser acceptance, not imported through Node.
          client = module.factory(id => id === '@deepseek-ai/dsh-client-ui-primitives' ? {} : require(id))
        },
      },
    },
    AbortController,
    console,
    setTimeout,
    clearTimeout,
  }, { filename: 'dsh-teampilot/lib/client.js' })
  assert.equal(typeof client?.startConversation, 'function', 'Exercise the exported built client entry point')
  return client.startConversation
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((onResolve, onReject) => { resolve = onResolve; reject = onReject })
  return { promise, resolve, reject }
}

// The loaded production client orchestrates these outward Controller faces.
// Host transport and model execution belong to the separate runtime acceptance.
function fixture(t, options = {}) {
  const ctx = new Context()
  t.after(() => ctx.fiber.dispose())
  const events = []
  const controller = new AbortController()
  const sessionId = 'session-teampilot-controller-test'
  const requestId = 'submission-teampilot-controller-test'
  let live = false
  let promptContent
  let submission
  const session = {
    beginSubmission(input) {
      assert.equal(live, true, 'The public Session face must have an owned reference')
      events.push('beginSubmission')
      submission = input
      return { requestId, abandon() { events.push('abandon') } }
    },
    async prompt(content, mode, signal, submittedRequestId) {
      assert.equal(live, true, 'The reference must remain live during admission')
      assert.equal(mode, 'queue')
      assert.equal(signal, controller.signal)
      assert.equal(submittedRequestId, requestId)
      assert.equal(submission.mode, mode)
      assert.equal(submission.text, content[0].text)
      assert.equal(submission.attachments.length, 0)
      promptContent = content
      events.push('prompt:start')
      const result = options.prompt
        ? await options.prompt({ signal, events })
        : { ok: true, value: { accepted: true } }
      events.push(result.ok ? 'prompt:accepted' : 'prompt:rejected')
      return result
    },
  }
  ctx.provide('remote', {
    agentPresets: {
      async select(id, preset) {
        assert.equal(id, sessionId)
        assert.equal(preset, 'teampilot')
        events.push('preset')
        return options.select
          ? options.select({ signal: controller.signal, events })
          : { ok: true, value: preset }
      },
    },
  })
  ctx.provide('sessions', {
    async create() {
      events.push('create')
      return options.create ? options.create({ signal: controller.signal, events }) : sessionId
    },
    async using(id, { source, signal }, operation) {
      assert.equal(id, sessionId)
      assert.equal(source, 'controllerOperation')
      assert.equal(signal, controller.signal)
      signal.throwIfAborted()
      events.push('retain')
      live = true
      const reference = {
        sessionId,
        get binding() {
          assert.equal(live, true, 'Access after reference release is forbidden')
          return { session }
        },
        ready: Promise.resolve().then(() => {
          signal.throwIfAborted()
          events.push('ready')
          if (options.readyError) throw options.readyError
          return { session }
        }),
      }
      try {
        await reference.ready
        return await operation(reference)
      } finally {
        live = false
        events.push('release')
        options.onRelease?.(controller)
      }
    },
  })
  ctx.provide('uiWorkspace', {
    openSession(id) {
      assert.equal(id, sessionId)
      assert.equal(live, false, 'The temporary reference is released after admission and before navigation')
      events.push('open')
    },
  })
  return {
    ctx, controller, events, sessionId,
    start: loadStartConversation(),
    get content() { return promptContent },
  }
}

test('conversation selects the business preset before admission and holds its reference until accepted', async t => {
  const admission = deferred()
  t.after(() => admission.resolve({ ok: true, value: { accepted: true } }))
  const f = fixture(t, { prompt: () => admission.promise })
  const request = { projectId: 'project-public-id', prompt: '  汇总当前项目的进展及延期依据  ' }
  const pending = f.start(f.ctx, request, f.controller.signal)
  await new Promise(resolve => setImmediate(resolve))
  assert.deepEqual(f.events, ['create', 'preset', 'retain', 'ready', 'beginSubmission', 'prompt:start'])
  assert.equal(f.content.length, 1)
  assert.equal(f.content[0].type, 'text')
  assert.match(f.content[0].text, /项目 ID project-public-id/)
  assert.match(f.content[0].text, /teampilot_account/)
  assert.match(f.content[0].text, /全部相关分页/)
  assert.match(f.content[0].text, /汇总当前项目的进展及延期依据$/)
  admission.resolve({ ok: true, value: { accepted: true } })
  assert.equal(await pending, f.sessionId)
  assert.deepEqual(f.events, ['create', 'preset', 'retain', 'ready', 'beginSubmission', 'prompt:start', 'prompt:accepted', 'release', 'open'])
})

test('blank demand is rejected before creating a session', async t => {
  const f = fixture(t)
  await assert.rejects(f.start(f.ctx, { projectId: '', prompt: ' \n ' }, f.controller.signal), /请输入需求/)
  assert.deepEqual(f.events, [])
})

test('admitted session is persisted before workspace navigation unmounts its panel', async t => {
  const f = fixture(t)
  const id = await f.start(f.ctx, { projectId: '', prompt: '汇总', onAdmitted(sessionId) {
    assert.equal(sessionId, f.sessionId)
    f.events.push('persist')
  } }, f.controller.signal)
  assert.equal(id, f.sessionId)
  assert.deepEqual(f.events.slice(-3), ['release', 'persist', 'open'])
})

test('session creation errors propagate unchanged and prevent preset selection and navigation', async t => {
  const error = new Error('session create unavailable')
  const f = fixture(t, { create: () => { throw error } })
  await assert.rejects(f.start(f.ctx, { projectId: '', prompt: '汇总' }, f.controller.signal), reason => reason === error)
  assert.deepEqual(f.events, ['create'])
})

test('preset rejection retains its business error and never admits a default-preset prompt', async t => {
  const f = fixture(t, { select: () => ({ ok: false, error: { code: 'agent-preset/broken', message: 'TeamPilot preset is unavailable' } }) })
  await assert.rejects(f.start(f.ctx, { projectId: '', prompt: '汇总' }, f.controller.signal), /TeamPilot preset is unavailable/)
  assert.deepEqual(f.events, ['create', 'preset'])
})

test('initial session opening failures release the reference and propagate unchanged', async t => {
  const error = new Error('session history could not open')
  const f = fixture(t, { readyError: error })
  await assert.rejects(f.start(f.ctx, { projectId: '', prompt: '汇总' }, f.controller.signal), reason => reason === error)
  assert.deepEqual(f.events, ['create', 'preset', 'retain', 'ready', 'release'])
})

test('prompt rejection keeps the host reason, releases the reference and does not navigate', async t => {
  const f = fixture(t, { prompt: () => ({ ok: false, error: { code: 'session/model-unavailable', message: 'Selected model is unavailable' } }) })
  await assert.rejects(f.start(f.ctx, { projectId: '', prompt: '汇总' }, f.controller.signal), /Selected model is unavailable/)
  assert.deepEqual(f.events, ['create', 'preset', 'retain', 'ready', 'beginSubmission', 'prompt:start', 'prompt:rejected', 'release'])
})

test('admission transport exceptions propagate unchanged after reference release', async t => {
  const error = new Error('prompt transport disconnected')
  const f = fixture(t, { prompt: () => { throw error } })
  await assert.rejects(f.start(f.ctx, { projectId: '', prompt: '汇总' }, f.controller.signal), reason => reason === error)
  assert.deepEqual(f.events, ['create', 'preset', 'retain', 'ready', 'beginSubmission', 'prompt:start', 'release'])
})

test('an already cancelled invocation neither creates nor navigates', async t => {
  const f = fixture(t)
  const reason = new Error('panel closed before submission')
  f.controller.abort(reason)
  await assert.rejects(f.start(f.ctx, { projectId: '', prompt: '汇总' }, f.controller.signal), error => error === reason)
  assert.deepEqual(f.events, [])
})

test('cancellation while selecting the preset prevents admission and navigation', async t => {
  const reason = new Error('panel closed during preset selection')
  const f = fixture(t, { select: ({ signal }) => {
    f.controller.abort(reason)
    assert.equal(signal.aborted, true)
    return { ok: true, value: 'teampilot' }
  } })
  await assert.rejects(f.start(f.ctx, { projectId: '', prompt: '汇总' }, f.controller.signal), error => error === reason)
  assert.deepEqual(f.events, ['create', 'preset'])
})

test('cancellation during prompt admission releases the reference and preserves the cancellation reason', async t => {
  const reason = new Error('panel closed during admission')
  const f = fixture(t, { prompt: ({ signal }) => {
    f.controller.abort(reason)
    signal.throwIfAborted()
  } })
  await assert.rejects(f.start(f.ctx, { projectId: '', prompt: '汇总' }, f.controller.signal), error => error === reason)
  assert.deepEqual(f.events, ['create', 'preset', 'retain', 'ready', 'beginSubmission', 'prompt:start', 'release'])
})

test('cancellation after durable admission prevents navigation from a disposed panel', async t => {
  const reason = new Error('panel closed after admission')
  const f = fixture(t, { onRelease: controller => controller.abort(reason) })
  await assert.rejects(f.start(f.ctx, { projectId: '', prompt: '汇总' }, f.controller.signal), error => error === reason)
  assert.deepEqual(f.events, ['create', 'preset', 'retain', 'ready', 'beginSubmission', 'prompt:start', 'prompt:accepted', 'release'])
})
