import assert from 'node:assert/strict'
import test from 'node:test'
import { createServer } from 'node:http'
import { readFileSync } from 'node:fs'
import { load } from 'js-yaml'
import { composeEntries } from '@deepseek-ai/dsh-app-boot'
import { Context } from '@deepseek-ai/cordis'
import { ToolRuntime } from '@deepseek-ai/dsh-tools'
import { remoteMethods } from '@deepseek-ai/dsh-typert-protocol'
import * as plugin from '../lib/index.js'
import * as policy from '../lib/preset.js'
import { TeamPilotApi, validateBaseUrl } from '../lib/types/host/api.js'

const signal = () => new AbortController().signal
const draftId = '00000000-0000-4000-8000-000000000001'
const tokens = { access_token: 'test-access', refresh_token: 'test-refresh' }

test('native plugin installation declares and composes its bundle entry', () => {
  const manifest = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'))
  assert.equal(manifest.peerDependencies['@deepseek-ai/dsh'], '0.2.0-rc.2')
  const patch = load(readFileSync(new URL(`../${manifest.dsh.bundle.patch}`, import.meta.url), 'utf8'))
  const entries = composeEntries([patch])
  assert.equal(entries.length, 1)
  assert.equal(entries[0].id, 'teampilot')
  assert.equal(entries[0].name, 'dsh-teampilot')
  assert.ok(manifest.files.includes('cordis.patch.yml'))
})

async function mockApi(t, handler) {
  const calls = []
  const server = createServer(async (request, response) => {
    let body = ''
    for await (const chunk of request) body += chunk
    calls.push({ path: request.url, method: request.method, authorization: request.headers.authorization, body: body ? JSON.parse(body) : null })
    response.setHeader('Content-Type', 'application/json')
    const result = await handler(calls.at(-1), response)
    if (!response.writableEnded) response.end(JSON.stringify(result))
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  t.after(() => new Promise(resolve => { server.closeAllConnections(); server.close(resolve) }))
  return { baseUrl: `http://127.0.0.1:${server.address().port}`, calls }
}

async function harness(t, baseUrl, config = {}) {
  const ctx = new Context()
  const presets = []
  ctx.provide('systemPrompt', { tools: () => () => {} })
  ctx.provide('agentPresets', { register: async preset => { presets.push(preset); return () => {} } })
  new ToolRuntime(ctx)
  const fiber = ctx.plugin(plugin, { baseUrl, ...config })
  await fiber.inertia
  assert.equal(fiber.state, 2, 'Host plugin must really activate')
  t.after(() => ctx.fiber.dispose())
  const execute = (name, args, abort = signal()) => ctx.tools.execute({ name, arguments: args, signal: abort, callId: 'test-call' })
  return { ctx, fiber, execute, presets }
}

test('origin validation rejects remote HTTP, credentials, paths and fragments', () => {
  assert.equal(validateBaseUrl('http://127.0.0.1:8000'), 'http://127.0.0.1:8000')
  assert.equal(validateBaseUrl('https://team.example'), 'https://team.example')
  for (const value of ['http://team.example', 'https://user:secret@team.example', 'https://team.example/api', 'https://team.example/#key']) {
    assert.throws(() => validateBaseUrl(value))
  }
})

test('real ToolRuntime reads canonical JSON, validates arguments and unloads cleanly', async t => {
  const api = await mockApi(t, call => call.path.endsWith('/auth/login') ? tokens : { items: [{ id: draftId, name: 'Project' }], total: 1 })
  const { ctx, execute, fiber, presets } = await harness(t, api.baseUrl)
  await ctx.teampilot.login({ username: 'member', password: 'private-test-password' }, signal())
  assert.equal(presets[0].id, 'teampilot')
  assert.equal(presets[0].plugins[0].name, 'dsh-teampilot/preset')
  const result = await execute('teampilot_projects', { page: 1 })
  assert.equal(result.isError, false)
  assert.equal(result.value.items[0].name, 'Project')
  assert.equal(JSON.stringify(result).includes('private-test-password'), false)
  assert.equal(JSON.stringify(result).includes(tokens.access_token), false)
  const count = api.calls.length
  for (const args of [{ page: '1' }, { page: 0 }, { page: 1.5 }]) assert.equal((await execute('teampilot_projects', args)).isError, true)
  assert.equal(api.calls.length, count)
  await fiber.dispose()
  assert.equal(ctx.get('teampilot'), undefined)
  assert.equal(ctx.tools.get('teampilot_projects'), undefined)
})

test('commit cannot bypass runtime approval or native panel review', async t => {
  const api = await mockApi(t, call => {
    if (call.path.endsWith('/auth/login')) return tokens
    if (call.path.endsWith('/approve')) return { confirmation_token: 'a'.repeat(64) }
    return { state: 'committed' }
  })
  const { ctx, execute } = await harness(t, api.baseUrl)
  const service = ctx.teampilot
  await service.login({ username: 'member', password: 'test' }, signal())
  await assert.rejects(() => service.commit(draftId, signal()), /Review and approve/)
  const review = await service.approve({ draftId, payloadHash: 'b'.repeat(64) }, signal())
  assert.deepEqual(review, { approved: true, draftId })
  assert.equal(remoteMethods(service).some(method => method.method === 'commit'), false)
  const result = await execute('teampilot_commit_draft', { draft_id: draftId })
  assert.equal(result.isError, true, 'Agent-less calls must be denied by the real Harness pipeline')
  assert.equal(api.calls.some(call => call.path.endsWith('/commit')), false)
  await service.logout(signal())
  await assert.rejects(() => service.commit(draftId, signal()), /Review and approve/)
})

test('request refreshes credentials but never exposes them in business results', async t => {
  let reads = 0
  const api = await mockApi(t, (call, response) => {
    if (call.path.endsWith('/auth/login')) return tokens
    if (call.path.endsWith('/auth/refresh')) return { access_token: 'renewed-access', refresh_token: 'renewed-refresh' }
    if (++reads === 1) { response.statusCode = 401; return { private: 'do-not-expose' } }
    return { items: [] }
  })
  const client = new TeamPilotApi(api.baseUrl)
  await client.login({ username: 'member', password: 'test' }, signal())
  assert.deepEqual(await client.request('/projects', signal()), { items: [] })
  assert.equal(api.calls.at(-1).authorization, 'Bearer renewed-access')
  assert.equal(api.calls.filter(call => call.path.endsWith('/auth/refresh')).length, 1)
})

test('draft list reports only in-memory approval availability and never its token', async t => {
  const api = await mockApi(t, call => {
    if (call.path.endsWith('/auth/login')) return tokens
    if (call.path.endsWith('/approve')) return { confirmation_token: 'c'.repeat(64) }
    return { items: [{ id: draftId, state: 'approved', approval_expires_at: '2099-01-01T00:00:00Z' }] }
  })
  const { ctx } = await harness(t, api.baseUrl)
  await ctx.teampilot.login({ username: 'member', password: 'test' }, signal())
  const read = async () => JSON.parse((await ctx.teampilot.read({ resource: 'drafts', page: 1 }, signal())).json)
  assert.equal((await read()).items[0].approval_available, false, 'Backend approved state alone is insufficient after Host restart')
  await ctx.teampilot.approve({ draftId, payloadHash: 'b'.repeat(64) }, signal())
  const value = await read()
  assert.equal(value.items[0].approval_available, true)
  assert.equal(JSON.stringify(value).includes('c'.repeat(64)), false)
  await ctx.teampilot.logout(signal())
  await ctx.teampilot.login({ username: 'member', password: 'test' }, signal())
  assert.equal((await read()).items[0].approval_available, false)
})

test('query tools use the logged-in account, bounded filters and canonical pagination', async t => {
  const account = { id: draftId, username: 'member', full_name: 'Member', role: 'member', is_active: true }
  const api = await mockApi(t, call => {
    if (call.path.endsWith('/auth/login')) return tokens
    if (call.path.endsWith('/auth/me')) return account
    return { items: [{ id: draftId }], total: 51, has_more: true, page: 1, page_size: 50 }
  })
  const { ctx, execute, presets } = await harness(t, api.baseUrl)
  await ctx.teampilot.login({ username: 'member', password: 'private-test-password' }, signal())
  const checks = [
    ['teampilot_tasks', { page: 1, project_id: draftId, assignee_id: draftId, status: 'in_progress', search: '计划... & 下一步?' }, '/integrations/dsh/tasks', { page: '1', page_size: '50', project_id: draftId, assignee_id: draftId, status: 'in_progress', search: '计划... & 下一步?' }],
    ['teampilot_progress', { page: 2, project_id: draftId, task_id: draftId, user_id: draftId, since: '2026-10-01T00:00:00Z', until: '2026-10-05T23:59:59+09:00' }, '/integrations/dsh/progress', { page: '2', page_size: '50', project_id: draftId, task_id: draftId, user_id: draftId, since: '2026-10-01T00:00:00Z', until: '2026-10-05T23:59:59+09:00' }],
    ['teampilot_task', { task_id: draftId }, `/tasks/${draftId}`, {}],
    ['teampilot_members', { project_id: draftId }, `/projects/${draftId}/members`, {}],
  ]
  for (const [name, args, path, query] of checks) {
    const result = await execute(name, args)
    assert.equal(result.isError, false, name)
    assert.equal(result.value.total, 51)
    assert.equal(result.value.has_more, true)
    const request = new URL(api.calls.at(-1).path, api.baseUrl)
    assert.equal(request.pathname, '/api/v1' + path)
    assert.deepEqual(Object.fromEntries(request.searchParams), query)
    assert.equal(api.calls.at(-1).authorization, 'Bearer test-access')
    assert.equal(api.calls.at(-1).method, 'GET')
    assert.equal(api.calls.at(-1).body, null)
  }
  const identity = await execute('teampilot_account', {})
  assert.equal(identity.isError, false)
  assert.deepEqual(identity.value.account, account)
  assert.equal(identity.value.connected, true)
  assert.equal(identity.value.username, 'member')
  assert.equal(identity.value.webUrl, api.baseUrl)
  assert.equal(api.calls.at(-1).path, '/api/v1/auth/me')
  assert.equal(JSON.stringify(identity).includes(tokens.access_token), false)
  assert.equal(JSON.stringify(identity).includes(tokens.refresh_token), false)
  assert.equal(JSON.stringify(identity).includes('private-test-password'), false)
  let restriction
  policy.apply({ tools: { restrict: value => { restriction = value } } })
  for (const name of checks.map(check => check[0]).concat('teampilot_account')) assert.ok(restriction.allow.includes(name), name)
  const persona = presets[0].plugins.find(entry => entry.id === 'persona').config.prefix
  assert.match(persona, /has_more/)
  assert.match(persona, /cached/i)
  assert.match(persona, /only when.*requests? .*change/i)
})

test('query tools reject invalid filters before sending a business request', async t => {
  const api = await mockApi(t, call => call.path.endsWith('/auth/login') ? tokens : { items: [] })
  const { ctx, execute } = await harness(t, api.baseUrl)
  await ctx.teampilot.login({ username: 'member', password: 'test' }, signal())
  const count = api.calls.length
  for (const [name, args] of [
    ['teampilot_tasks', { page: 0 }],
    ['teampilot_tasks', { page: 1, project_id: '../auth/me' }],
    ['teampilot_tasks', { page: 1, project_id: 'invalid', assignee_id: '', status: 'all' }],
    ['teampilot_tasks', { page: 1, status: 'deleted' }],
    ['teampilot_tasks', { page: 1, search: 'x'.repeat(301) }],
    ['teampilot_progress', { page: 1, user_id: 'not-an-id' }],
    ['teampilot_progress', { page: 1, since: 'yesterday' }],
    ['teampilot_progress', { page: 1, project_id: '', since: 'invalid', until: '' }],
    ['teampilot_progress', { page: 1, since: '2026-02-30' }],
    ['teampilot_progress', { page: 1, since: '2026-10-01T24:00:00Z' }],
    ['teampilot_progress', { page: 1, since: '2026-10-01T00:00:00+24:00' }],
    ['teampilot_progress', { page: 1, since: '2026-10-06T00:00:00Z', until: '2026-10-05T00:00:00Z' }],
    ['teampilot_progress', { page: 1, since: '2026-10-01T00:00:00', until: '2026-10-01T01:00:00+01:00' }],
    ['teampilot_task', { task_id: 'not-an-id' }],
    ['teampilot_members', { project_id: 'not-an-id' }],
  ]) assert.equal((await execute(name, args)).isError, true, name)
  assert.equal(api.calls.length, count)
})

test('empty optional filters query the full scope and object results carry the Host clock', async t => {
  const snapshot = { items: [{ id: draftId }], total: 1, has_more: false, generated_at: '2026-01-01T00:00:00Z' }
  const api = await mockApi(t, call => {
    if (call.path.endsWith('/auth/login')) return tokens
    if (call.path.endsWith('/auth/me')) return { id: draftId, username: 'member' }
    if (call.path.endsWith('/dashboard/team-workload')) return [{ user_id: draftId }]
    return snapshot
  })
  const { ctx, execute } = await harness(t, api.baseUrl)
  await ctx.teampilot.login({ username: 'member', password: 'test' }, signal())
  const start = Date.now()
  const checkClock = value => {
    assert.equal(value.query_clock, 'dsh_host')
    assert.match(value.queried_at, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/)
    assert.ok(Date.parse(value.queried_at) >= start && Date.parse(value.queried_at) <= Date.now())
  }
  for (const [name, args, path] of [
    ['teampilot_tasks', { page: 1 }, '/api/v1/integrations/dsh/tasks?page=1&page_size=50'],
    ['teampilot_tasks', { page: 1, project_id: '', assignee_id: '', status: 'all', search: '' }, '/api/v1/integrations/dsh/tasks?page=1&page_size=50'],
    ['teampilot_progress', { page: 1, project_id: '', task_id: '', user_id: '', since: '', until: '' }, '/api/v1/integrations/dsh/progress?page=1&page_size=50'],
    ['teampilot_projects', { page: 1 }, '/api/v1/projects?page=1&page_size=50'],
  ]) {
    const result = await execute(name, args)
    assert.equal(result.isError, false, name)
    assert.equal(api.calls.at(-1).path, path)
    assert.equal(api.calls.at(-1).method, 'GET')
    assert.equal(api.calls.at(-1).body, null)
    checkClock(result.value)
    assert.equal(result.value.generated_at, snapshot.generated_at, 'query time must not replace cached generation time')
  }
  checkClock((await execute('teampilot_account', {})).value)
  checkClock(JSON.parse((await ctx.teampilot.read({ resource: 'projects', page: 1 }, signal())).json))
  assert.deepEqual((await execute('teampilot_workload', {})).value, [{ user_id: draftId }], 'array result shape remains unchanged')
})

test('progress ranges preserve timezone and microsecond precision', async t => {
  const api = await mockApi(t, call => call.path.endsWith('/auth/login') ? tokens : { items: [] })
  const { ctx, execute } = await harness(t, api.baseUrl)
  await ctx.teampilot.login({ username: 'member', password: 'test' }, signal())
  const since = '2026-10-01T09:00:00.000001+09:00'
  const until = '2026-10-01T00:00:00.000002Z'
  assert.equal((await execute('teampilot_progress', { page: 1, since, until })).isError, false)
  const request = new URL(api.calls.at(-1).path, api.baseUrl)
  assert.equal(request.searchParams.get('since'), since)
  assert.equal(request.searchParams.get('until'), until)
  const count = api.calls.length
  assert.equal((await execute('teampilot_progress', { page: 1, since: until, until: since })).isError, true)
  assert.equal(api.calls.length, count)
})

test('query tools require login and preserve backend permission denials', async t => {
  const api = await mockApi(t, (call, response) => {
    if (call.path.endsWith('/auth/login')) return tokens
    response.statusCode = 403
    return { private: 'private-permission-body' }
  })
  const { ctx, execute } = await harness(t, api.baseUrl)
  for (const [name, args] of [
    ['teampilot_tasks', { page: 1 }], ['teampilot_progress', { page: 1 }], ['teampilot_account', {}],
  ]) assert.equal((await execute(name, args)).isError, true)
  assert.equal(api.calls.length, 0)
  await ctx.teampilot.login({ username: 'member', password: 'test' }, signal())
  const denied = await execute('teampilot_progress', { page: 1 })
  assert.equal(denied.isError, true)
  assert.match(JSON.stringify(denied), /HTTP 403/)
  assert.equal(JSON.stringify(denied).includes('private-permission-body'), false)
  assert.equal((await ctx.teampilot.status(signal())).connected, true)
  assert.equal(api.calls.length, 2)
  assert.equal(api.calls.at(-1).method, 'GET')
})

test('public status publishes a validated web origin without credentials', async t => {
  const { ctx } = await harness(t, 'http://127.0.0.1:8000')
  assert.equal((await ctx.teampilot.status(signal())).webUrl, 'http://127.0.0.1:5173')
  const custom = await harness(t, 'https://api.team.example', { webUrl: 'https://team.example' })
  assert.equal((await custom.ctx.teampilot.status(signal())).webUrl, 'https://team.example')
  for (const webUrl of ['http://team.example', 'https://user:secret@team.example', 'https://team.example/login?token=private']) {
    const invalid = new Context()
    assert.throws(() => new plugin.TeamPilotService(invalid, { baseUrl: 'https://api.team.example', webUrl }))
    await invalid.fiber.dispose()
  }
})

test('expired refresh credentials clear the account without exposing error bodies', async t => {
  const api = await mockApi(t, (call, response) => {
    if (call.path.endsWith('/auth/login')) return tokens
    response.statusCode = 401
    return { private: 'must-not-reach-agent' }
  })
  const client = new TeamPilotApi(api.baseUrl)
  await client.login({ username: 'member', password: 'test' }, signal())
  await assert.rejects(() => client.request('/projects', signal()), /HTTP 401/)
  assert.equal(client.connected, false)
  assert.equal(client.username, '')
  const count = api.calls.length
  await assert.rejects(() => client.request('/projects', signal()), /Log in/)
  assert.equal(api.calls.length, count)
})

test('a rejected refreshed access token clears login, while refresh outages preserve it', async t => {
  for (const mode of ['retry-401', 'refresh-503']) {
    const api = await mockApi(t, (call, response) => {
      if (call.path.endsWith('/auth/login')) return tokens
      if (call.path.endsWith('/auth/refresh') && mode === 'retry-401') return { access_token: 'renewed', refresh_token: 'renewed-refresh' }
      response.statusCode = call.path.endsWith('/auth/refresh') ? 503 : 401
      return { error: 'private-server-error' }
    })
    const client = new TeamPilotApi(api.baseUrl)
    await client.login({ username: 'member', password: 'test' }, signal())
    await assert.rejects(() => client.request('/projects', signal()), /HTTP/)
    assert.equal(client.connected, mode === 'refresh-503', mode)
  }
})

test('logout during a pending request discards the old account result', async t => {
  let release
  const ready = new Promise(resolve => { release = resolve })
  let received
  const started = new Promise(resolve => { received = resolve })
  const api = await mockApi(t, async call => {
    if (call.path.endsWith('/auth/login')) return tokens
    received(); await ready
    return { privateOldAccountData: true }
  })
  const client = new TeamPilotApi(api.baseUrl)
  await client.login({ username: 'member', password: 'test' }, signal())
  const request = client.request('/projects', signal())
  await started
  client.logout(); release()
  await assert.rejects(request, /Account changed/)
  assert.equal(client.connected, false)
})

test('malformed success responses and invalid token shapes never expose server content', async t => {
  for (const mode of ['json', 'access', 'refresh', 'header']) {
    const privateValue = 'private-malformed-response-secret'
    const api = await mockApi(t, (_call, response) => {
      if (mode === 'json') { response.end(privateValue); return }
      return { access_token: mode === 'access' ? { privateValue } : mode === 'header' ? privateValue + '\u0000' : 'valid',
        refresh_token: mode === 'refresh' ? { privateValue } : 'valid-refresh' }
    })
    const client = new TeamPilotApi(api.baseUrl)
    await assert.rejects(() => client.login({ username: 'member', password: 'test' }, signal()), error => {
      assert.equal(String(error).includes(privateValue), false)
      assert.match(String(error), /Invalid TeamPilot/)
      return true
    })
    assert.equal(client.connected, false)
    assert.equal(client.username, '')
  }
  const api = await mockApi(t, (call, response) => {
    if (call.path.endsWith('/auth/login')) return tokens
    response.end('private-business-response-secret')
  })
  const { ctx, execute } = await harness(t, api.baseUrl)
  await ctx.teampilot.login({ username: 'member', password: 'test' }, signal())
  const result = await execute('teampilot_tasks', { page: 1 })
  assert.equal(result.isError, true)
  assert.match(JSON.stringify(result), /Invalid TeamPilot JSON response/)
  assert.equal(JSON.stringify(result).includes('private-business-response-secret'), false)
})

test('optional refresh tokens do not prevent login or discard an existing refresh token', async t => {
  let reads = 0
  const api = await mockApi(t, (call, response) => {
    if (call.path.endsWith('/auth/login')) return tokens
    if (call.path.endsWith('/auth/refresh')) return { access_token: 'renewed-access' }
    if (++reads % 2) { response.statusCode = 401; return {} }
    return { items: [] }
  })
  const client = new TeamPilotApi(api.baseUrl)
  await client.login({ username: 'member', password: 'test' }, signal())
  await client.request('/projects', signal())
  await client.request('/projects', signal())
  assert.equal(api.calls.filter(call => call.path.endsWith('/auth/refresh')).length, 2)
  assert.deepEqual(api.calls.filter(call => call.path.endsWith('/auth/refresh')).map(call => call.body), [
    { refresh_token: tokens.refresh_token }, { refresh_token: tokens.refresh_token },
  ])

  const accessOnlyApi = await mockApi(t, (call, response) => {
    if (call.path.endsWith('/auth/login')) return { access_token: 'access-only', refresh_token: null }
    response.statusCode = 401; return {}
  })
  const accessOnlyClient = new TeamPilotApi(accessOnlyApi.baseUrl)
  await accessOnlyClient.login({ username: 'member', password: 'test' }, signal())
  assert.equal(accessOnlyClient.connected, true)
  await assert.rejects(() => accessOnlyClient.request('/projects', signal()), /HTTP 401/)
  assert.equal(accessOnlyClient.connected, false)
  assert.equal(accessOnlyApi.calls.length, 2)
})

test('redirect, cancellation, unsafe paths and oversized responses fail closed', async t => {
  const api = await mockApi(t, (call, response) => {
    if (call.path.endsWith('/auth/login')) return tokens
    if (call.path.endsWith('/redirect')) { response.writeHead(302, { Location: 'https://example.com' }); response.end(); return }
    return { oversized: 'x'.repeat(2 * 1024 * 1024) }
  })
  const client = new TeamPilotApi(api.baseUrl)
  await client.login({ username: 'member', password: 'test' }, signal())
  await assert.rejects(() => client.request('/redirect', signal()))
  await assert.rejects(() => client.request('/projects', signal()), /context limit/)
  await assert.rejects(() => client.request('//example.com', signal()), /Invalid API path/)
  await assert.rejects(() => client.request('/../auth/login', signal()), /Invalid API path/)
  await assert.rejects(() => client.request('/projects/%2e%2e/auth/login', signal()), /Invalid API path/)
  await assert.rejects(() => client.request('/projects/../auth/login', signal()), /Invalid API path/)
  await assert.rejects(() => client.request('/projects\\auth\\login', signal()), /Invalid API path/)
  const abort = new AbortController(); abort.abort()
  await assert.rejects(() => client.request('/projects', abort.signal))
})
