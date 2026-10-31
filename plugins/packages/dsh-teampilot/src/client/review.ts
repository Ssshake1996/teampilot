export interface ProjectOption { id: string; name: string }
export interface PanelState {
  projectId: string; projectName: string; prompt: string; view: 'query' | 'drafts'; selected: string; sessionId: string
}
export interface StorageLike { getItem(key: string): string | null; setItem(key: string, value: string): void }
const emptyState = (): PanelState => ({ projectId: '', projectName: '', prompt: '', view: 'query', selected: '', sessionId: '' })
export function panelStorageKey(baseUrl: string, username: string): string {
  return `teampilot.panel.v1:${encodeURIComponent(baseUrl)}:${encodeURIComponent(username)}`
}
export function readPanelState(storage: StorageLike | undefined, key: string): PanelState {
  try {
    const data = JSON.parse(storage?.getItem(key) ?? '{}')
    return { projectId: typeof data.projectId === 'string' ? data.projectId.slice(0, 100) : '',
      projectName: typeof data.projectName === 'string' ? data.projectName.slice(0, 300) : '',
      prompt: typeof data.prompt === 'string' ? data.prompt.slice(0, 20000) : '',
      view: data.view === 'drafts' ? 'drafts' : 'query',
      selected: typeof data.selected === 'string' ? data.selected.slice(0, 100) : '',
      sessionId: typeof data.sessionId === 'string' ? data.sessionId.slice(0, 200) : '' }
  } catch { return emptyState() }
}
export function savePanelState(storage: StorageLike | undefined, key: string, state: PanelState): void {
  // Explicit fields only: passwords, approval tokens and tool payloads never persist.
  const safe = { projectId: state.projectId, projectName: state.projectName, prompt: state.prompt.slice(0, 20000),
    view: state.view, selected: state.selected, sessionId: state.sessionId }
  try { storage?.setItem(key, JSON.stringify(safe)) } catch { /* Storage may be disabled or full. */ }
}
export function projectOptions(page: ProjectOption[], selected: ProjectOption | null, search: string): ProjectOption[] {
  const needle = search.trim().toLocaleLowerCase()
  const matches = page.filter(item => !needle || item.name.toLocaleLowerCase().includes(needle))
  return selected && !matches.some(item => item.id === selected.id) ? [selected, ...matches] : matches
}

const labels: Record<string, string> = { title: '任务名称', name: '项目名称', goal: '目标', description: '描述',
  assignee_ids: '负责人', estimated_hours: '预计工时', hours_spent: '本次实际工时', start_date: '开始时间',
  deadline: '截止时间', end_date: '项目截止时间', priority: '优先级', progress_pct: '进度', note: '进展说明',
  weight: '同级权重', parent_task_id: '父任务', status: '状态', source: '来源' }
const values: Record<string, string> = { low: '低', medium: '中', high: '高', urgent: '紧急',
  not_started: '待开始', in_progress: '进行中', done: '已完成', active: '进行中', planning: '规划中',
  completed: '已完成', archived: '已归档' }
function display(value: unknown, field: string, names: Record<string, string>): string {
  if (value === null || value === undefined || value === '') return '未设置'
  if (field === 'assignee_ids' && Array.isArray(value)) return value.length ? value.map(id => names[String(id)] ?? String(id)).join('、') : '未分配'
  if (field === 'progress_pct') return `${value}%`
  if (field === 'estimated_hours' || field === 'hours_spent') return `${Number(value)} 小时`
  if (field === 'weight') return `${Math.round(Number(value) * 10000) / 100}%`
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'object') return JSON.stringify(value)
  if (field === 'priority' || field === 'status') {
    const code = String(value).split('.').at(-1)!.toLowerCase()
    return values[code] ?? String(value)
  }
  return String(value)
}
export function buildReviewRows(before: unknown, after: unknown, names: Record<string, string> = {}) {
  const old = before && typeof before === 'object' ? before as Record<string, unknown> : {}
  const next = after && typeof after === 'object' ? after as Record<string, unknown> : {}
  return [...new Set([...Object.keys(next), ...Object.keys(old)])].filter(key => !['children', 'revision', 'kind'].includes(key)).map(key => ({
    key, label: labels[key] ?? key, before: before === null ? '新增' : display(old[key], key, names),
    after: display(next[key], key, names), changed: before === null || display(old[key], key, names) !== display(next[key], key, names),
  }))
}
export function approvalStatus(draft: { state: string; expires_at: string; approval_expires_at?: string | null; approval_available?: boolean }, now = Date.now()) {
  if (draft.state === 'committed') return { label: '已提交，业务数据已写入', mayApprove: false, ready: false }
  if (draft.state === 'cancelled') return { label: '草稿已取消', mayApprove: false, ready: false }
  if (Date.parse(draft.expires_at) <= now) return { label: '草稿已过期，请在对话中重新生成', mayApprove: false, ready: false }
  if (draft.state !== 'approved') return { label: '待审阅，尚未写入', mayApprove: true, ready: false }
  if (!draft.approval_expires_at || Date.parse(draft.approval_expires_at) <= now)
    return { label: '批准已过期，尚未写入；请重新审阅批准', mayApprove: true, ready: false }
  if (!draft.approval_available) return { label: '已批准，尚未写入；当前 DSH 已无批准凭据，请重新审阅批准', mayApprove: true, ready: false }
  return { label: '已批准，尚未写入', mayApprove: false, ready: true }
}
export function commitInstruction(draftId: string): string {
  return `请提交我刚在 TeamPilot 面板审阅批准的草稿 ${draftId}。只提交这份草稿，先检查其状态，再通过 teampilot_commit_draft 请求 DSH 原生审批；等待我确认，不创建其他草稿，不绕过审批。`
}
