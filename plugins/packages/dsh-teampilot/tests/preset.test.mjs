import assert from 'node:assert/strict'
import test from 'node:test'
import { Context } from '@deepseek-ai/cordis'
import { createScope } from '@deepseek-ai/dsh-scope'
import { SystemPrompt } from '@deepseek-ai/dsh-system-prompt'
import { ToolRuntime, defineTool } from '@deepseek-ai/dsh-tools'
import { UserQuestionService } from '@deepseek-ai/dsh-user-questions'
import * as askUser from '@deepseek-ai/dsh-tool-ask-user'
import * as policy from '../lib/preset.js'

// The deployment surface is independent of the policy being tested: registering
// its allow list as globals would incorrectly make a scoped ask-user name valid.
const businessTools = [
  'teampilot_projects', 'teampilot_context', 'teampilot_personnel', 'teampilot_person',
  'teampilot_workload', 'teampilot_report', 'teampilot_tasks', 'teampilot_progress',
  'teampilot_task', 'teampilot_members', 'teampilot_account',
  'teampilot_propose', 'teampilot_draft', 'teampilot_commit_draft',
]

function harness(t) {
  const ctx = new Context()
  t.after(() => ctx.fiber.dispose())
  new SystemPrompt(ctx, { includeHarnessIdentity: false })
  new ToolRuntime(ctx)
  new UserQuestionService(ctx)
  const executed = []
  for (const name of [...businessTools, 'shell']) {
    ctx.tools.register(defineTool({
      name,
      description: `Fixture for the deployment's ${name} tool`,
      parameters: {},
      output: {
        schema: { type: 'json' },
        render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }],
      },
      execute: () => {
        executed.push(name)
        return { tool: name }
      },
    }))
  }
  const agent = { id: 'preset-test-agent' }
  const scope = createScope(ctx, agent)
  const execute = name => ctx.tools.execute({
    name, arguments: {}, agent, callId: `test-${name}`,
    signal: new AbortController().signal,
  })
  return { ctx, agent, scope, execute, executed }
}

async function activate(ctx, plugin) {
  const fiber = ctx.plugin(plugin)
  await fiber.inertia
  assert.equal(fiber.state, 2, 'The real scoped plugin must activate')
  return fiber
}

test('restrict rejects the old allow list even with scoped ask-user registered', async t => {
  const { ctx, agent, scope } = harness(t)
  await activate(scope.ctx, askUser)
  assert.ok(ctx.tools.get('ask_user_question', agent))
  assert.equal(ctx.tools.get('ask_user_question'), undefined)
  assert.throws(
    () => scope.ctx.tools.restrict({ allow: [...businessTools, 'ask_user_question'] }),
    /tools\.restrict\(\) names unknown global tool "ask_user_question"/,
  )
  assert.ok(ctx.tools.get('shell', agent), 'A failed restriction must not install a mask')
})

test('production policy admits business queries and scoped ask-user, but prevents shell execution', async t => {
  const { ctx, agent, scope, execute, executed } = harness(t)
  // Match the production preset row order: policy before the scoped ask-user row.
  const policyFiber = await activate(scope.ctx, policy)
  await activate(scope.ctx, askUser)
  assert.deepEqual(
    ctx.tools.schemas(agent).map(tool => tool.name).sort(),
    [...businessTools, 'ask_user_question'].sort(),
  )
  assert.ok(ctx.tools.get('shell'), 'The shell exists in the deployment')
  assert.equal(ctx.tools.get('shell', agent), undefined)
  assert.ok(ctx.tools.resolveExecution('ask_user_question', agent, false))

  const query = await execute('teampilot_tasks')
  assert.equal(query.isError, false)
  assert.deepEqual(query.value, { tool: 'teampilot_tasks' })
  const shell = await execute('shell')
  assert.equal(shell.isError, true)
  assert.equal(shell.error?.info?.code, 'UNKNOWN_TOOL')
  assert.deepEqual(executed, ['teampilot_tasks'], 'Hidden shell bodies must never execute')

  await policyFiber.dispose()
  assert.ok(ctx.tools.get('shell', agent), 'Policy unload must release the scoped mask')
  assert.ok(ctx.tools.get('ask_user_question', agent), 'The separate ask-user row stays registered')
  await scope.dispose()
  assert.equal(ctx.tools.get('ask_user_question', agent), undefined)
  assert.ok(ctx.tools.get('shell'), 'Scope teardown must preserve deployment tools')
})
