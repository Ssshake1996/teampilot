import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-tools'

export const inject = ['tools']
export const BUSINESS_TOOLS = ['teampilot_projects', 'teampilot_context', 'teampilot_personnel', 'teampilot_person',
  'teampilot_workload', 'teampilot_report', 'teampilot_tasks', 'teampilot_progress', 'teampilot_task',
  'teampilot_members', 'teampilot_account', 'teampilot_propose', 'teampilot_draft', 'teampilot_commit_draft']

export function apply(ctx: Context): void {
  // restrict filters inherited global tools; the preset's scoped ask-user row
  // remains available without naming it as a global tool.
  ctx.tools.restrict({ allow: BUSINESS_TOOLS })
}
