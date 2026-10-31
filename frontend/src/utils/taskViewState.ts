export interface TaskListState {
  page: number
  pageSize: number
  status: string
  assignee: string
  priority: string
  sortBy: string
  sortOrder: 'asc' | 'desc'
  scrollTop: number
}

export const defaultTaskListState: TaskListState = {
  page: 1, pageSize: 20, status: '', assignee: '', priority: '',
  sortBy: 'created_at', sortOrder: 'desc', scrollTop: 0,
}

export function parseTaskListState(raw: string | null): TaskListState {
  try {
    const saved = JSON.parse(raw || '{}')
    const states = ['', 'not_started', 'in_progress', 'done']
    const priorities = ['', 'low', 'medium', 'high', 'urgent']
    const fields = ['created_at', 'title', 'status', 'priority', 'assignee_name', 'deadline', 'progress_pct']
    return {
      page: Number.isSafeInteger(saved.page) && saved.page > 0 ? saved.page : 1,
      pageSize: [10, 20, 50, 100].includes(saved.pageSize) ? saved.pageSize : 20,
      status: states.includes(saved.status) ? saved.status : '',
      assignee: typeof saved.assignee === 'string' ? saved.assignee : '',
      priority: priorities.includes(saved.priority) ? saved.priority : '',
      sortBy: fields.includes(saved.sortBy) ? saved.sortBy : 'created_at',
      sortOrder: saved.sortOrder === 'asc' ? 'asc' : 'desc',
      scrollTop: Number.isFinite(saved.scrollTop) && saved.scrollTop >= 0 ? saved.scrollTop : 0,
    }
  } catch { return { ...defaultTaskListState } }
}

export function taskViewKey(accountId: string, projectId: string, view = 'list') {
  return `teampilot.tasks.${accountId}.${projectId}.${view}`
}

// Return links are restricted to local product pages, never external destinations.
export function safeTaskReturnPath(value: unknown): string | null {
  return typeof value === 'string' && /^\/(?:dashboard|projects|personnel)(?:[/?#]|$)/.test(value)
    && !/[\r\n\\]/.test(value) ? value : null
}
