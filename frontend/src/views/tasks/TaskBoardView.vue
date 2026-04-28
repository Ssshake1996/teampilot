<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus, Warning } from '@element-plus/icons-vue'
import draggable from 'vuedraggable'
import { projectsApi } from '@/api/projects'
import { tasksApi } from '@/api/tasks'
import { aiApi } from '@/api/ai'
import { usersApi } from '@/api/users'
import TaskDataSkillPanel from '@/components/tasks/TaskDataSkillPanel.vue'
import { useTaskStore } from '@/stores/task'
import { useAuthStore } from '@/stores/auth'
import { TaskStatus, TaskPriority, TaskStatusLabel, TaskPriorityLabel, PriorityColor } from '@/types/enums'
import type { Project, Task, TaskProgress, User } from '@/types/models'
import type { FormInstance } from 'element-plus'

const route = useRoute()
const projectId = route.params.id as string
const taskStore = useTaskStore()
const auth = useAuthStore()

const loading = ref(false)
const project = ref<Project | null>(null)
const users = ref<User[]>([])
const canCreateTask = computed(() => auth.can('task.create'))
const canSignoffTask = computed(() => auth.can('task.signoff'))
const canSubmitProgress = computed(() => auth.can('progress.submit'))
const canUseAiRisk = computed(() => auth.can('ai.risk'))
const canUseAiEstimate = computed(() => auth.can('ai.estimate'))

// Kanban columns config
const columns = [
  { status: TaskStatus.NOT_STARTED, label: TaskStatusLabel[TaskStatus.NOT_STARTED] },
  { status: TaskStatus.IN_PROGRESS, label: TaskStatusLabel[TaskStatus.IN_PROGRESS] },
  { status: TaskStatus.DONE, label: TaskStatusLabel[TaskStatus.DONE] },
]

const columnHeaderColors: Record<string, string> = {
  [TaskStatus.NOT_STARTED]: '#909399',
  [TaskStatus.IN_PROGRESS]: '#E6A23C',
  [TaskStatus.DONE]: '#67C23A',
}

// Reactive column data: each column is an array of tasks
const columnTasks = ref<Record<string, Task[]>>({
  [TaskStatus.NOT_STARTED]: [],
  [TaskStatus.IN_PROGRESS]: [],
  [TaskStatus.DONE]: [],
})

function syncColumnsFromStore() {
  for (const col of columns) {
    columnTasks.value[col.status] = taskStore.tasksByStatus(col.status)
  }
}

function columnCount(status: TaskStatus): number {
  return columnTasks.value[status]?.length ?? 0
}

// Create Task Dialog
const createDialogVisible = ref(false)
const createFormRef = ref<FormInstance>()
const creating = ref(false)
const createForm = ref({
  title: '',
  description: '',
  priority: TaskPriority.MEDIUM,
  assignee_ids: [] as string[],
  estimated_hours: null as number | null,
  deadline: '',
})
const createAiEstimating = ref(false)
const createAiStatusMsg = ref('')
const createAiEstimateInfo = ref<any>(null)
const createAiRecommendations = ref<any[]>([])

const createRules = {
  title: [{ required: true, message: '请输入任务标题', trigger: 'blur' }],
}

function openCreateDialog() {
  createForm.value = {
    title: '',
    description: '',
    priority: TaskPriority.MEDIUM,
    assignee_ids: [],
    estimated_hours: null,
    deadline: '',
  }
  createAiStatusMsg.value = ''
  createAiEstimateInfo.value = null
  createAiRecommendations.value = []
  createDialogVisible.value = true
}

async function handleCreateAiEstimate() {
  if (!createForm.value.title.trim()) {
    ElMessage.warning('请先填写任务标题')
    return
  }
  createAiEstimating.value = true
  createAiStatusMsg.value = '正在启动 AI...'
  createAiEstimateInfo.value = null
  createAiRecommendations.value = []
  try {
    const data = await aiApi.estimateTask(
      projectId,
      createForm.value.title,
      '',
      createForm.value.description,
      (msg: string) => { createAiStatusMsg.value = msg },
    )
    createAiEstimateInfo.value = data
    createAiRecommendations.value = data.recommended_assignees || []
    if (data.estimated_hours != null && createForm.value.estimated_hours == null) {
      createForm.value.estimated_hours = data.estimated_hours
    }
    createAiStatusMsg.value = ''
  } catch {
    createAiStatusMsg.value = ''
    ElMessage.error('AI 评估失败')
  } finally {
    createAiEstimating.value = false
  }
}

function applyCreateRecommendation(rec: any) {
  createForm.value.assignee_ids = rec.user_id ? [rec.user_id] : []
  ElMessage.success('已采纳推荐人选')
}

async function handleCreateTask() {
  if (!createFormRef.value) return
  await createFormRef.value.validate()
  creating.value = true
  try {
    const payload: Partial<Task> = {
      title: createForm.value.title,
      priority: createForm.value.priority,
    }
    if (createForm.value.description) payload.description = createForm.value.description
    if (createForm.value.assignee_ids.length) payload.assignee_ids = createForm.value.assignee_ids
    if (createForm.value.estimated_hours !== null) payload.estimated_hours = createForm.value.estimated_hours
    if (createForm.value.deadline) payload.deadline = createForm.value.deadline
    await tasksApi.create(projectId, payload)
    ElMessage.success('任务创建成功')
    createDialogVisible.value = false
    await loadTasks()
  } catch {
    ElMessage.error('任务创建失败')
  } finally {
    creating.value = false
  }
}

// Task Detail Drawer
const drawerVisible = ref(false)
const selectedTask = ref<Task | null>(null)
const progressHistory = ref<TaskProgress[]>([])
const loadingProgress = ref(false)
const signoffAssistLoading = ref(false)
const signoffAssistStatus = ref('')
const signoffAssistResult = ref<any>(null)
const progressForm = ref({
  progress_pct: 0,
  note: '',
  hours_spent: null as number | null,
})

function getPriorityColor(priority: TaskPriority): string {
  return PriorityColor[priority] || '#909399'
}

function priorityTagType(priority: TaskPriority): string {
  const map: Record<string, string> = {
    [TaskPriority.LOW]: 'success',
    [TaskPriority.MEDIUM]: 'warning',
    [TaskPriority.HIGH]: 'danger',
    [TaskPriority.URGENT]: 'danger',
  }
  return map[priority] || 'info'
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  return dateStr.slice(0, 10)
}

function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return '-'
  return dateStr.replace('T', ' ').slice(0, 16)
}

function isOverdue(task: Task): boolean {
  if (!task.deadline || task.status === TaskStatus.DONE) return false
  return new Date(task.deadline) < new Date()
}

function taskStatusType(status: TaskStatus | string): string {
  const map: Record<string, string> = {
    [TaskStatus.NOT_STARTED]: 'info',
    [TaskStatus.IN_PROGRESS]: 'warning',
    [TaskStatus.DONE]: 'success',
  }
  return map[status] || 'info'
}

function needsSignoff(task: Task): boolean {
  return task.status !== TaskStatus.DONE && (task.progress_pct || 0) >= 100
}

function canSignoff(task: Task): boolean {
  return canSignoffTask.value && needsSignoff(task)
}

async function openTaskDrawer(task: Task) {
  selectedTask.value = task
  signoffAssistStatus.value = ''
  signoffAssistResult.value = null
  progressForm.value = {
    progress_pct: task.progress_pct || 0,
    note: '',
    hours_spent: null,
  }
  drawerVisible.value = true
  await Promise.all([
    loadProgressHistory(task.id),
    loadSubtasks(task.id),
  ])
}

async function loadProgressHistory(taskId: string) {
  loadingProgress.value = true
  try {
    const res = await tasksApi.getProgress(taskId)
    progressHistory.value = res.data
  } catch {
    progressHistory.value = []
  } finally {
    loadingProgress.value = false
  }
}

async function handleLogProgress() {
  if (!selectedTask.value) return
  if (selectedTask.value.is_deleted) {
    ElMessage.warning('已删除任务不支持反馈进展')
    return
  }
  if (!progressForm.value.note.trim()) {
    ElMessage.warning('请填写进展说明')
    return
  }
  try {
    const data: { progress_pct: number; note?: string; hours_spent?: number } = {
      progress_pct: progressForm.value.progress_pct,
    }
    if (progressForm.value.note) data.note = progressForm.value.note
    if (progressForm.value.hours_spent !== null) data.hours_spent = progressForm.value.hours_spent
    await tasksApi.logProgress(selectedTask.value.id, data)
    ElMessage.success('进度已更新')
    taskStore.updateTaskLocally(selectedTask.value.id, { progress_pct: progressForm.value.progress_pct })
    selectedTask.value = { ...selectedTask.value, progress_pct: progressForm.value.progress_pct }
    syncColumnsFromStore()
    progressForm.value.note = ''
    progressForm.value.hours_spent = null
    await loadProgressHistory(selectedTask.value.id)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '更新进度失败')
  }
}

async function handleDataSkillProgressAdopted(entry: TaskProgress) {
  if (!selectedTask.value) return
  taskStore.updateTaskLocally(selectedTask.value.id, { progress_pct: entry.progress_pct })
  selectedTask.value = { ...selectedTask.value, progress_pct: entry.progress_pct }
  syncColumnsFromStore()
  await loadProgressHistory(selectedTask.value.id)
}

async function handleSignoffTask(task: Task) {
  try {
    const res = await tasksApi.signoff(task.id)
    taskStore.updateTaskLocally(task.id, res.data)
    if (selectedTask.value?.id === task.id) selectedTask.value = res.data
    syncColumnsFromStore()
    ElMessage.success('任务已会签完成')
  } catch {
    ElMessage.error('会签失败，请确认进度已达到 100%')
  }
}

async function handleSignoffAssist() {
  if (!selectedTask.value) return
  signoffAssistLoading.value = true
  signoffAssistStatus.value = '正在生成会签建议...'
  signoffAssistResult.value = null
  try {
    signoffAssistResult.value = await aiApi.signoffAssist(
      selectedTask.value.id,
      (msg: string) => { signoffAssistStatus.value = msg },
    )
    signoffAssistStatus.value = ''
  } catch {
    signoffAssistStatus.value = ''
    ElMessage.error('会签建议生成失败')
  } finally {
    signoffAssistLoading.value = false
  }
}

async function loadTasks() {
  loading.value = true
  try {
    await taskStore.fetchTasks(projectId, { page_size: 500 })
    syncColumnsFromStore()
  } catch {
    ElMessage.error('加载任务失败')
  } finally {
    loading.value = false
  }
}

async function fetchUsers() {
  try {
    const res = await usersApi.list(1, 100)
    users.value = res.data.items
  } catch {
    // silent
  }
}

async function fetchProject() {
  try {
    const res = await projectsApi.get(projectId)
    project.value = res.data
  } catch {
    project.value = null
  }
}

// ========== Feature 1: Subtask Decomposition ==========

interface SubtaskItem {
  id?: string
  title: string
  assignee_name: string | null
  estimated_hours: number | null
  deadline: string | null
  status: TaskStatus
}

const subtasks = ref<SubtaskItem[]>([])
const loadingSubtasks = ref(false)
const showSubtaskForm = ref(false)
const creatingSubtask = ref(false)

const subtaskForm = ref({
  title: '',
  assignee_ids: [] as string[],
  estimated_hours: null as number | null,
  deadline: '',
})

async function loadSubtasks(taskId: string) {
  loadingSubtasks.value = true
  try {
    const res = await tasksApi.getSubtasks(taskId)
    subtasks.value = res.data
  } catch {
    subtasks.value = []
  } finally {
    loadingSubtasks.value = false
  }
}

function openSubtaskForm() {
  subtaskForm.value = { title: '', assignee_ids: [], estimated_hours: null, deadline: '' }
  showSubtaskForm.value = true
}

function cancelSubtaskForm() {
  showSubtaskForm.value = false
}

async function handleCreateSubtask() {
  if (!selectedTask.value || !subtaskForm.value.title.trim()) {
    ElMessage.warning('请输入子任务标题')
    return
  }
  creatingSubtask.value = true
  try {
    const payload: Partial<Task> = {
      title: subtaskForm.value.title.trim(),
    }
    if (subtaskForm.value.assignee_ids.length) payload.assignee_ids = subtaskForm.value.assignee_ids
    if (subtaskForm.value.estimated_hours !== null) payload.estimated_hours = subtaskForm.value.estimated_hours
    if (subtaskForm.value.deadline) payload.deadline = subtaskForm.value.deadline
    await tasksApi.createSubtask(selectedTask.value.id, payload)
    ElMessage.success('子任务创建成功')
    showSubtaskForm.value = false
    await loadSubtasks(selectedTask.value.id)
  } catch {
    ElMessage.error('子任务创建失败')
  } finally {
    creatingSubtask.value = false
  }
}

// AI Decompose
interface AIDecomposeItem {
  title: string
  description: string
  recommended_assignee: string | null
  estimated_hours: number | null
  reason: string
  selected: boolean
}

const decomposeDialogVisible = ref(false)
const decomposing = ref(false)
const decomposeResults = ref<AIDecomposeItem[]>([])
const adoptingSubtasks = ref(false)

async function handleAIDecompose() {
  if (!selectedTask.value) return
  decomposing.value = true
  decomposeDialogVisible.value = true
  decomposeResults.value = []
  try {
    const res = await aiApi.decomposeTask(selectedTask.value.id)
    const items = (res as any)?.subtasks || (res as any) || []
    decomposeResults.value = (Array.isArray(items) ? items : []).map((item: any) => ({
      title: item.title || '',
      description: item.description || '',
      recommended_assignee: item.recommended_assignee || null,
      estimated_hours: item.estimated_hours ?? null,
      reason: item.reason || '',
      selected: true,
    }))
  } catch {
    ElMessage.error('AI 分解任务失败，请稍后重试')
    decomposeDialogVisible.value = false
  } finally {
    decomposing.value = false
  }
}

const allDecomposeSelected = ref(true)

function toggleSelectAllDecompose(val: boolean) {
  allDecomposeSelected.value = val
  decomposeResults.value.forEach(item => {
    item.selected = val
  })
}

function onDecomposeItemChange() {
  allDecomposeSelected.value = decomposeResults.value.every(item => item.selected)
}

async function handleAdoptAll() {
  if (!selectedTask.value) return
  const selected = decomposeResults.value.filter(item => item.selected)
  if (selected.length === 0) {
    ElMessage.warning('请至少选择一个子任务')
    return
  }
  adoptingSubtasks.value = true
  try {
    const payload: Partial<Task>[] = selected.map(item => {
      const sub: Partial<Task> = { title: item.title }
      if (item.description) sub.description = item.description
      if (item.estimated_hours !== null) sub.estimated_hours = item.estimated_hours
      return sub
    })
    await tasksApi.batchCreateSubtasks(selectedTask.value.id, payload)
    ElMessage.success(`成功创建 ${selected.length} 个子任务`)
    decomposeDialogVisible.value = false
    await loadSubtasks(selectedTask.value.id)
  } catch {
    ElMessage.error('批量创建子任务失败')
  } finally {
    adoptingSubtasks.value = false
  }
}

function subtaskStatusType(status: TaskStatus): string {
  const map: Record<string, string> = {
    [TaskStatus.NOT_STARTED]: 'info',
    [TaskStatus.IN_PROGRESS]: 'warning',
    [TaskStatus.DONE]: 'success',
  }
  return map[status] || 'info'
}

// ========== Feature 2: AI Risk Analysis ==========

interface RiskItem {
  severity: string
  type: string
  title: string
  description: string
  affected_tasks: string[]
  affected_users: string[]
  suggestion: string
}

interface RiskAnalysis {
  overall_health: string
  summary: string
  risks: RiskItem[]
  progress_summary?: {
    overall_status?: string
    key_points?: string[]
    blockers?: string[]
  }
  priority_recommendations?: Array<{
    urgency?: string
    title: string
    reason: string
    affected_tasks?: string[]
    affected_users?: string[]
    suggestion?: string
  }>
}

interface PriorityInsightItem {
  id: string
  title: string
  reason: string
  urgency: string
  assigneeText: string
  deadline: string | null
  progressPct: number
}

const riskDrawerVisible = ref(false)
const loadingRisk = ref(false)
const riskAnalysis = ref<RiskAnalysis | null>(null)

const projectOverview = computed(() => {
  const tasks = taskStore.tasks.filter((task) => !task.is_deleted)
  const total = tasks.length
  const done = tasks.filter((task) => task.status === TaskStatus.DONE).length
  const inProgress = tasks.filter((task) => task.status === TaskStatus.IN_PROGRESS).length
  const notStarted = tasks.filter((task) => task.status === TaskStatus.NOT_STARTED).length
  const overdue = tasks.filter((task) => task.status !== TaskStatus.DONE && !!task.deadline && new Date(task.deadline).getTime() < Date.now()).length
  const signoffPending = tasks.filter((task) => needsSignoff(task)).length
  const avgProgress = total
    ? Math.round(tasks.reduce((sum, task) => sum + (task.progress_pct || 0), 0) / total)
    : 0
  const completionRate = total ? Math.round((done / total) * 100) : 0

  return {
    total,
    done,
    inProgress,
    notStarted,
    overdue,
    signoffPending,
    avgProgress,
    completionRate,
  }
})

const projectProgressNarrative = computed(() => {
  const aiStatus = riskAnalysis.value?.progress_summary?.overall_status?.trim()
  if (aiStatus) return aiStatus

  const overview = projectOverview.value
  if (!overview.total) return '当前项目还没有任务数据。'

  return `当前共 ${overview.total} 项任务，已完成 ${overview.done} 项，进行中 ${overview.inProgress} 项，整体平均进度 ${overview.avgProgress}%，完成率 ${overview.completionRate}%。`
})

const progressHighlights = computed(() => {
  const aiPoints = riskAnalysis.value?.progress_summary?.key_points?.filter(Boolean) || []
  if (aiPoints.length) return aiPoints

  const overview = projectOverview.value
  const points: string[] = []
  if (overview.inProgress) points.push(`${overview.inProgress} 项任务正在推进`)
  if (overview.done) points.push(`${overview.done} 项任务已完成`)
  if (overview.notStarted) points.push(`${overview.notStarted} 项任务尚未开始`)
  if (overview.signoffPending) points.push(`${overview.signoffPending} 项任务待会签确认`)

  return points.length ? points.slice(0, 4) : ['当前暂无可提炼的进展要点']
})

const progressBlockers = computed(() => {
  const aiBlockers = riskAnalysis.value?.progress_summary?.blockers?.filter(Boolean) || []
  if (aiBlockers.length) return aiBlockers

  const overview = projectOverview.value
  const blockers: string[] = []
  if (overview.overdue) blockers.push(`${overview.overdue} 项任务已逾期，需要立即处理`)
  if (overview.signoffPending) blockers.push(`${overview.signoffPending} 项任务达到 100% 但仍待会签`)

  return blockers.length ? blockers.slice(0, 3) : ['当前没有明显阻塞项']
})

const aiPriorityRecommendations = computed(() => riskAnalysis.value?.priority_recommendations || [])

function highestRiskLevel(levels: string[]): string {
  if (levels.includes('high')) return 'high'
  if (levels.includes('medium')) return 'medium'
  return levels.includes('low') ? 'low' : 'low'
}

function urgencyLabel(level: string): string {
  const map: Record<string, string> = {
    high: '高优先',
    medium: '中优先',
    low: '常规关注',
  }
  return map[level] || level
}

function taskAssigneeText(task: Task): string {
  return task.assignee_names?.join('、') || task.assignee_name || '未分配'
}

function buildPriorityInsights(tasks: Task[], risks: RiskItem[]): { actionItems: PriorityInsightItem[]; keyNodes: PriorityInsightItem[] } {
  const activeTasks = tasks.filter((task) => !task.is_deleted && task.status !== TaskStatus.DONE)
  const childMap = new Map<string, Task[]>()
  const riskMap = new Map<string, string[]>()
  const now = Date.now()

  for (const risk of risks || []) {
    for (const taskTitle of risk.affected_tasks || []) {
      const current = riskMap.get(taskTitle) || []
      current.push(risk.severity)
      riskMap.set(taskTitle, current)
    }
  }

  for (const task of activeTasks) {
    if (!task.parent_task_id) continue
    const children = childMap.get(task.parent_task_id) || []
    children.push(task)
    childMap.set(task.parent_task_id, children)
  }

  const scoreTask = (task: Task, asNode: boolean) => {
    const parts: string[] = []
    let score = 0
    const deadlineMs = task.deadline ? new Date(task.deadline).getTime() : null
    const daysLeft = deadlineMs ? Math.ceil((deadlineMs - now) / 86400000) : null
    const riskLevel = highestRiskLevel(riskMap.get(task.title) || [])

    if (deadlineMs !== null && deadlineMs < now) {
      score += 80
      parts.push('已逾期')
    } else if (daysLeft !== null && daysLeft <= 2) {
      score += 45
      parts.push('临近截止')
    } else if (daysLeft !== null && daysLeft <= 5) {
      score += 20
      parts.push('截止时间较近')
    }

    if (task.priority === TaskPriority.URGENT) {
      score += 35
      parts.push('任务紧急')
    } else if (task.priority === TaskPriority.HIGH) {
      score += 25
      parts.push('优先级高')
    } else if (task.priority === TaskPriority.MEDIUM) {
      score += 10
    }

    if (task.status === TaskStatus.IN_PROGRESS) {
      score += 20
      if ((task.progress_pct || 0) < 50) parts.push('进行中但进度偏慢')
    } else {
      score += 8
      parts.push('尚未启动')
    }

    if (!task.assignee_ids?.length && !task.assignee_name) {
      score += 20
      parts.push('尚未明确负责人')
    }

    if (riskLevel === 'high') {
      score += 40
      parts.push('存在高风险')
    } else if (riskLevel === 'medium') {
      score += 20
      parts.push('存在中风险')
    } else if (riskLevel === 'low') {
      score += 8
    }

    if (asNode) {
      const children = childMap.get(task.id) || []
      const overdueChildren = children.filter((child) => child.deadline && new Date(child.deadline).getTime() < now).length
      if (children.length > 0) {
        score += children.length * 8
        parts.push(`${children.length} 个子任务待收口`)
      }
      if (overdueChildren > 0) {
        score += overdueChildren * 12
        parts.push(`${overdueChildren} 个子任务已逾期`)
      }
    }

    return {
      score,
      urgency: score >= 120 ? 'high' : score >= 70 ? 'medium' : 'low',
      reason: parts.filter(Boolean).slice(0, 3).join('，') || '建议关注当前推进情况',
    }
  }

  const actionItems = activeTasks
    .filter((task) => !childMap.has(task.id))
    .map((task) => {
      const insight = scoreTask(task, false)
      return {
        id: task.id,
        title: task.title,
        reason: insight.reason,
        urgency: insight.urgency,
        assigneeText: taskAssigneeText(task),
        deadline: task.deadline,
        progressPct: task.progress_pct || 0,
        _score: insight.score,
      }
    })
    .sort((a, b) => b._score - a._score)
    .slice(0, 5)
    .map(({ _score, ...item }) => item)

  const keyNodes = activeTasks
    .filter((task) => childMap.has(task.id))
    .map((task) => {
      const insight = scoreTask(task, true)
      return {
        id: task.id,
        title: task.title,
        reason: insight.reason,
        urgency: insight.urgency,
        assigneeText: taskAssigneeText(task),
        deadline: task.deadline,
        progressPct: task.progress_pct || 0,
        _score: insight.score,
      }
    })
    .sort((a, b) => b._score - a._score)
    .slice(0, 4)
    .map(({ _score, ...item }) => item)

  return { actionItems, keyNodes }
}

const priorityInsights = computed(() => buildPriorityInsights(taskStore.tasks, riskAnalysis.value?.risks || []))

async function openProjectAnalysis() {
  riskDrawerVisible.value = true
  loadingRisk.value = true
  riskAnalysis.value = null
  try {
    const res = await aiApi.analyzeProject(projectId)
    riskAnalysis.value = res as any
  } catch {
    riskAnalysis.value = {
      overall_health: 'warning',
      summary: 'AI 当前不可用，已基于任务进展、风险线索和优先级规则生成本地项目分析。',
      progress_summary: {
        overall_status: projectProgressNarrative.value,
        key_points: progressHighlights.value,
        blockers: progressBlockers.value,
      },
      priority_recommendations: [],
      risks: [],
    }
    ElMessage.warning('AI 当前不可用，已展示本地项目分析')
  } finally {
    loadingRisk.value = false
  }
}

function healthColor(health: string): string {
  const map: Record<string, string> = {
    healthy: '#67C23A',
    warning: '#E6A23C',
    critical: '#F56C6C',
  }
  return map[health] || '#909399'
}

function healthLabel(health: string): string {
  const map: Record<string, string> = {
    healthy: '健康',
    warning: '警告',
    critical: '严重',
  }
  return map[health] || health
}

function severityTagType(severity: string): string {
  const map: Record<string, string> = {
    high: 'danger',
    medium: 'warning',
    low: '',
  }
  return map[severity] || 'info'
}

function severityLabel(severity: string): string {
  const map: Record<string, string> = {
    high: '高',
    medium: '中',
    low: '低',
  }
  return map[severity] || severity
}

// ========== Feature 3: Subtask count on task cards ==========

function hasSubtasks(task: Task): boolean {
  return task.parent_task_id === null
}

// ========== Init ==========

onMounted(async () => {
  await Promise.all([loadTasks(), fetchUsers(), fetchProject()])
})
</script>

<template>
  <div v-loading="loading" class="task-board-view">
    <div v-if="project" class="project-summary-card">
      <div class="project-summary-head">
        <h2>{{ project.name }}</h2>
      </div>
      <div class="project-summary-grid">
        <div class="project-summary-section">
          <span class="project-summary-label">项目目标</span>
          <p>{{ project.goal || '暂无项目目标' }}</p>
        </div>
        <div class="project-summary-section">
          <span class="project-summary-label">项目描述</span>
          <p>{{ project.description || '暂无项目描述' }}</p>
        </div>
      </div>
    </div>
    <div class="board-container">
      <div v-for="col in columns" :key="col.status" class="board-column">
        <div class="column-header" :style="{ borderTopColor: columnHeaderColors[col.status] }">
          <span class="column-title">{{ col.label }}</span>
          <el-badge :value="columnCount(col.status)" type="info" class="column-count" />
        </div>

        <draggable
          v-model="columnTasks[col.status]"
          group="tasks"
          item-key="id"
          class="column-body"
          ghost-class="ghost-card"
          :animation="200"
          :disabled="true"
        >
          <template #item="{ element: task }">
            <div
              class="task-card"
              :style="{ borderLeftColor: getPriorityColor(task.priority) }"
              @click="openTaskDrawer(task)"
            >
              <div class="task-title">
                <span>{{ task.title }}</span>
                <el-tag
                  v-if="hasSubtasks(task)"
                  size="small"
                  type="info"
                  effect="plain"
                  class="subtask-badge"
                >
                  子
                </el-tag>
              </div>
              <div class="task-meta">
                <el-tag
                  :type="(priorityTagType(task.priority) as any)"
                  size="small"
                  effect="light"
                >
                  {{ TaskPriorityLabel[task.priority as TaskPriority] || task.priority }}
                </el-tag>
                <span v-if="task.assignee_names?.length || task.assignee_name" class="assignee">
                  {{ task.assignee_names?.join('、') || task.assignee_name }}
                </span>
              </div>
              <div v-if="task.deadline" class="task-deadline" :class="{ overdue: isOverdue(task) }">
                {{ formatDate(task.deadline) }}
              </div>
              <el-progress
                v-if="task.progress_pct > 0"
                :percentage="task.progress_pct"
                :stroke-width="4"
                :show-text="false"
                class="task-progress"
              />
              <div v-if="needsSignoff(task)" class="signoff-row">
                <el-tag type="warning" size="small" effect="plain">待会签</el-tag>
                <el-button
                  v-if="canSignoff(task)"
                  type="success"
                  link
                  size="small"
                  @click.stop="handleSignoffTask(task)"
                >
                  会签确认
                </el-button>
              </div>
            </div>
          </template>
        </draggable>
      </div>
    </div>

    <!-- Floating Create Button -->
    <el-tooltip v-if="canCreateTask" content="新建任务" placement="left">
      <el-button
        class="fab-button"
        type="primary"
        :icon="Plus"
        circle
        size="large"
        @click="openCreateDialog"
      />
    </el-tooltip>

    <!-- AI Project Analysis Floating Button -->
    <el-tooltip
      v-if="canUseAiRisk"
      content="项目分析：汇总项目进展、风险和优先级建议"
      placement="left"
    >
      <el-button
        class="fab-button-risk"
        type="warning"
        :icon="Warning"
        circle
        size="large"
        @click="openProjectAnalysis"
      />
    </el-tooltip>

    <!-- Create Task Dialog -->
    <el-dialog
      v-model="createDialogVisible"
      title="新建任务"
      width="560px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="createFormRef"
        :model="createForm"
        :rules="createRules"
        label-width="90px"
      >
        <el-form-item label="任务标题" prop="title">
          <el-input v-model="createForm.title" placeholder="请输入任务标题" />
        </el-form-item>
        <el-form-item label="任务描述">
          <el-input
            v-model="createForm.description"
            type="textarea"
            :rows="3"
            placeholder="请输入任务描述"
          />
        </el-form-item>
        <el-form-item v-if="canUseAiEstimate" label="AI 评估">
          <div class="create-ai-wrap">
            <div class="create-ai-row">
              <el-button
                type="warning"
                :loading="createAiEstimating"
                :disabled="!createForm.title.trim()"
                @click="handleCreateAiEstimate"
              >
                AI 推荐人选 + 预估工时
              </el-button>
              <span v-if="createAiStatusMsg" class="create-ai-status">{{ createAiStatusMsg }}</span>
            </div>
            <div v-if="createAiEstimateInfo" class="create-ai-box">
              <div class="create-ai-head">AI 评估结果</div>
              <div class="create-ai-estimate">
                预估工时:
                <strong>{{ createAiEstimateInfo.estimated_hours ?? '-' }}h</strong>
                <el-tag
                  v-if="createAiEstimateInfo.confidence"
                  :type="createAiEstimateInfo.confidence === 'high' ? 'success' : createAiEstimateInfo.confidence === 'medium' ? 'warning' : 'info'"
                  size="small"
                >
                  {{ createAiEstimateInfo.confidence === 'high' ? '高置信' : createAiEstimateInfo.confidence === 'medium' ? '中置信' : '低置信' }}
                </el-tag>
              </div>
              <div v-if="createAiEstimateInfo.reasoning" class="create-ai-reason">
                {{ createAiEstimateInfo.reasoning }}
              </div>
              <div v-if="createAiRecommendations.length" class="create-ai-recs">
                <div class="create-ai-recs-title">推荐人选</div>
                <div v-for="(rec, idx) in createAiRecommendations" :key="idx" class="create-ai-rec">
                  <span class="create-ai-rank">#{{ idx + 1 }}</span>
                  <span class="create-ai-name">{{ rec.name }}</span>
                  <el-tag v-if="rec.score != null" size="small" type="warning">{{ rec.score }}分</el-tag>
                  <el-button type="primary" size="small" link @click="applyCreateRecommendation(rec)">采纳</el-button>
                  <div v-if="rec.reason" class="create-ai-rec-reason">{{ rec.reason }}</div>
                </div>
              </div>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="createForm.priority" style="width: 100%">
            <el-option
              v-for="p in [TaskPriority.LOW, TaskPriority.MEDIUM, TaskPriority.HIGH, TaskPriority.URGENT]"
              :key="p"
              :label="TaskPriorityLabel[p]"
              :value="p"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="指派给">
          <el-select
            v-model="createForm.assignee_ids"
            placeholder="选择负责人"
            clearable
            filterable
            multiple
            collapse-tags
            collapse-tags-tooltip
            style="width: 100%"
          >
            <el-option
              v-for="user in users"
              :key="user.id"
              :label="user.full_name"
              :value="user.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="预估工时">
          <el-input-number
            v-model="createForm.estimated_hours"
            :min="0"
            :max="9999"
            :precision="1"
            placeholder="小时"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="截止日期">
          <el-date-picker
            v-model="createForm.deadline"
            type="date"
            placeholder="选择截止日期"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreateTask">确认创建</el-button>
      </template>
    </el-dialog>

    <!-- Task Detail Drawer -->
    <el-drawer
      v-model="drawerVisible"
      :title="selectedTask?.title || '任务详情'"
      size="560px"
      direction="rtl"
    >
      <template v-if="selectedTask">
        <div class="drawer-content">
          <!-- Basic Info -->
          <div class="detail-section">
            <h4>基本信息</h4>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="状态">
                <el-tag :type="(taskStatusType(selectedTask.status) as any)" size="small">
                  {{ TaskStatusLabel[selectedTask.status as TaskStatus] || selectedTask.status }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="优先级">
                <el-tag :type="(priorityTagType(selectedTask.priority) as any)" size="small">
                  {{ TaskPriorityLabel[selectedTask.priority as TaskPriority] || selectedTask.priority }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="负责人">
                {{ selectedTask.assignee_names?.join('、') || selectedTask.assignee_name || '未指派' }}
              </el-descriptions-item>
              <el-descriptions-item label="截止日期">
                <span :class="{ overdue: isOverdue(selectedTask) }">
                  {{ formatDate(selectedTask.deadline) }}
                </span>
              </el-descriptions-item>
              <el-descriptions-item label="预估工时">
                {{ selectedTask.estimated_hours ? selectedTask.estimated_hours + 'h' : '-' }}
              </el-descriptions-item>
              <el-descriptions-item label="实际工时">
                {{ selectedTask.actual_hours ? selectedTask.actual_hours + 'h' : '-' }}
              </el-descriptions-item>
              <el-descriptions-item label="当前进度">
                <el-progress :percentage="selectedTask.progress_pct" :stroke-width="10" />
              </el-descriptions-item>
              <el-descriptions-item v-if="selectedTask.signed_off_at" label="会签时间">
                {{ formatDateTime(selectedTask.signed_off_at) }}
              </el-descriptions-item>
              <el-descriptions-item v-if="selectedTask.signed_off_by_name" label="会签人">
                {{ selectedTask.signed_off_by_name }}
              </el-descriptions-item>
              <el-descriptions-item label="创建时间">
                {{ formatDateTime(selectedTask.created_at) }}
              </el-descriptions-item>
            </el-descriptions>
            <div v-if="needsSignoff(selectedTask)" class="detail-signoff">
              <el-tag type="warning" effect="plain">进度 100%，等待会签</el-tag>
              <el-button
                v-if="canUseAiRisk"
                type="warning"
                size="small"
                :loading="signoffAssistLoading"
                @click="handleSignoffAssist"
              >
                AI 会签建议
              </el-button>
              <el-button
                v-if="canSignoff(selectedTask)"
                type="success"
                size="small"
                @click="handleSignoffTask(selectedTask)"
              >
                会签确认
              </el-button>
            </div>
            <div v-if="signoffAssistStatus || signoffAssistResult" class="signoff-assist">
              <span v-if="signoffAssistStatus" class="create-ai-status">{{ signoffAssistStatus }}</span>
              <template v-if="signoffAssistResult">
                <el-tag :type="signoffAssistResult.recommendation === 'approve' ? 'success' : 'warning'" size="small">
                  {{ signoffAssistResult.recommendation === 'approve' ? '建议会签' : '建议暂缓' }}
                </el-tag>
                <p>{{ signoffAssistResult.summary }}</p>
                <ul v-if="Array.isArray(signoffAssistResult.risks) && signoffAssistResult.risks.length">
                  <li v-for="(risk, idx) in signoffAssistResult.risks" :key="idx">{{ risk }}</li>
                </ul>
              </template>
            </div>
          </div>

          <!-- Description -->
          <div class="detail-section">
            <h4>描述</h4>
            <p class="task-description">{{ selectedTask.description || '暂无描述' }}</p>
          </div>

          <div class="detail-section">
            <h4>数据 Skill</h4>
            <TaskDataSkillPanel
              :task="selectedTask"
              :can-manage-progress="canSubmitProgress"
              @progress-adopted="handleDataSkillProgressAdopted"
            />
          </div>

          <!-- Subtasks Section (Feature 1) -->
          <div class="detail-section">
            <div class="section-header-row">
              <h4>子任务</h4>
              <div class="section-header-actions">
                <el-button v-if="canCreateTask" size="small" @click="openSubtaskForm">手动添加子任务</el-button>
                <el-button v-if="canUseAiEstimate && canCreateTask" size="small" type="primary" :loading="decomposing" @click="handleAIDecompose">AI 智能分解</el-button>
              </div>
            </div>

            <!-- Inline Subtask Form -->
            <div v-if="showSubtaskForm" class="subtask-inline-form">
              <el-form :inline="false" size="small" label-width="70px">
                <el-form-item label="标题">
                  <el-input v-model="subtaskForm.title" placeholder="子任务标题" />
                </el-form-item>
                <el-form-item label="负责人">
                  <el-select
                    v-model="subtaskForm.assignee_ids"
                    placeholder="选择负责人"
                    clearable
                    filterable
                    multiple
                    class="full-assignee-select"
                    style="width: 100%"
                  >
                    <el-option
                      v-for="user in users"
                      :key="user.id"
                      :label="user.full_name"
                      :value="user.id"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item label="预估工时">
                  <el-input-number
                    v-model="subtaskForm.estimated_hours"
                    :min="0"
                    :max="9999"
                    :precision="1"
                    style="width: 100%"
                  />
                </el-form-item>
                <el-form-item label="截止日期">
                  <el-date-picker
                    v-model="subtaskForm.deadline"
                    type="date"
                    placeholder="选择截止日期"
                    value-format="YYYY-MM-DD"
                    style="width: 100%"
                  />
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" :loading="creatingSubtask" @click="handleCreateSubtask">确认</el-button>
                  <el-button @click="cancelSubtaskForm">取消</el-button>
                </el-form-item>
              </el-form>
            </div>

            <!-- Subtask Table -->
            <div v-loading="loadingSubtasks">
              <el-table
                v-if="subtasks.length > 0"
                :data="subtasks"
                size="small"
                border
                style="width: 100%"
                :header-cell-style="{ fontSize: '12px', padding: '4px 0' }"
                :cell-style="{ fontSize: '12px', padding: '4px 8px' }"
              >
                <el-table-column label="标题" prop="title" min-width="120" show-overflow-tooltip />
                <el-table-column label="负责人" width="80" align="center">
                  <template #default="{ row }">
                    {{ row.assignee_names?.join('、') || row.assignee_name || '未分配' }}
                  </template>
                </el-table-column>
                <el-table-column label="工时" width="60" align="center">
                  <template #default="{ row }">
                    {{ row.estimated_hours != null ? row.estimated_hours + 'h' : '-' }}
                  </template>
                </el-table-column>
                <el-table-column label="截止" width="90" align="center">
                  <template #default="{ row }">
                    {{ formatDate(row.deadline) }}
                  </template>
                </el-table-column>
                <el-table-column label="状态" width="70" align="center">
                  <template #default="{ row }">
                    <el-tag :type="(subtaskStatusType(row.status) as any)" size="small">
                      {{ TaskStatusLabel[row.status as TaskStatus] || row.status }}
                    </el-tag>
                  </template>
                </el-table-column>
              </el-table>
              <el-empty v-else description="暂无子任务" :image-size="40" />
            </div>
          </div>

          <div class="detail-section">
            <el-alert
              type="info"
              :closable="false"
              show-icon
              title="这里可以手动提交真实进展；项目管理页顶部的进展更新更适合批量导入群消息。"
            />
          </div>

          <div v-if="canSubmitProgress && !selectedTask.is_deleted" class="detail-section">
            <h4>手动提交</h4>
            <el-form label-width="80px" size="small">
              <el-form-item label="进度 (%)">
                <el-slider v-model="progressForm.progress_pct" :min="0" :max="100" show-input />
              </el-form-item>
              <el-form-item label="备注">
                <el-input
                  v-model="progressForm.note"
                  type="textarea"
                  :rows="2"
                  placeholder="说明真实进展、阻塞或结果"
                />
              </el-form-item>
              <el-form-item label="工时 (h)">
                <el-input-number
                  v-model="progressForm.hours_spent"
                  :min="0"
                  :max="999"
                  :precision="1"
                />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" size="default" @click="handleLogProgress">提交进展</el-button>
              </el-form-item>
            </el-form>
          </div>

          <div v-else-if="selectedTask.is_deleted" class="detail-section">
            <el-alert
              type="warning"
              :closable="false"
              show-icon
              title="任务已删除，当前仅保留详情和历史记录，不支持继续反馈进展。"
            />
          </div>
          <div v-else class="detail-section">
            <el-alert
              type="warning"
              :closable="false"
              show-icon
              title="当前账号没有手动提交进展的权限。"
            />
          </div>

          <!-- Progress History -->
          <div class="detail-section">
            <h4>进度记录</h4>
            <div v-loading="loadingProgress">
              <el-timeline v-if="progressHistory.length > 0">
                <el-timeline-item
                  v-for="log in progressHistory"
                  :key="log.id"
                  :timestamp="formatDateTime(log.created_at)"
                  placement="top"
                >
                  <div class="progress-log-item">
                    <span class="log-user">{{ log.user_name || '系统' }}</span>
                    <span class="log-pct">进度: {{ log.progress_pct }}%</span>
                    <span v-if="log.hours_spent" class="log-hours">耗时: {{ log.hours_spent }}h</span>
                    <p v-if="log.note" class="log-note">{{ log.note }}</p>
                  </div>
                </el-timeline-item>
              </el-timeline>
              <el-empty v-else description="暂无进度记录" :image-size="60" />
            </div>
          </div>
        </div>
      </template>
    </el-drawer>

    <!-- AI Decompose Results Dialog -->
    <el-dialog
      v-model="decomposeDialogVisible"
      title="AI 智能分解结果"
      width="700px"
      :close-on-click-modal="false"
    >
      <div v-loading="decomposing" element-loading-text="AI 正在分析任务...">
        <template v-if="!decomposing && decomposeResults.length > 0">
          <div class="decompose-toolbar">
            <el-checkbox
              :model-value="allDecomposeSelected"
              @change="(val: any) => toggleSelectAllDecompose(val as boolean)"
            >
              全选
            </el-checkbox>
            <span class="decompose-count">共 {{ decomposeResults.length }} 个建议子任务</span>
          </div>
          <div class="decompose-list">
            <div
              v-for="(item, idx) in decomposeResults"
              :key="idx"
              class="decompose-item"
            >
              <div class="decompose-item-header">
                <el-checkbox v-model="item.selected" @change="onDecomposeItemChange" />
                <span class="decompose-item-title">{{ item.title }}</span>
                <el-tag v-if="item.estimated_hours != null" size="small" type="info">
                  {{ item.estimated_hours }}h
                </el-tag>
              </div>
              <div v-if="item.description" class="decompose-item-desc">{{ item.description }}</div>
              <div class="decompose-item-meta">
                <span v-if="item.recommended_assignee" class="decompose-meta-label">
                  建议负责人: <strong>{{ item.recommended_assignee }}</strong>
                </span>
              </div>
              <div v-if="item.reason" class="decompose-item-reason">
                <el-icon style="vertical-align: middle; margin-right: 4px;"><Warning /></el-icon>
                {{ item.reason }}
              </div>
            </div>
          </div>
        </template>
        <el-empty v-if="!decomposing && decomposeResults.length === 0" description="未能获取分解建议" />
      </div>
      <template #footer>
        <el-button @click="decomposeDialogVisible = false">关闭</el-button>
        <el-button
          type="primary"
          :loading="adoptingSubtasks"
          :disabled="decomposing || decomposeResults.filter(i => i.selected).length === 0"
          @click="handleAdoptAll"
        >
          全部采纳 ({{ decomposeResults.filter(i => i.selected).length }})
        </el-button>
      </template>
    </el-dialog>

    <!-- AI Project Analysis Drawer -->
    <el-drawer
      v-model="riskDrawerVisible"
      title="项目分析"
      size="520px"
      direction="rtl"
    >
      <div v-loading="loadingRisk" element-loading-text="AI 正在生成项目分析..." class="risk-drawer-content">
        <template v-if="!loadingRisk && riskAnalysis">
          <div class="risk-health-section">
            <div
              class="health-badge"
              :style="{ backgroundColor: healthColor(riskAnalysis.overall_health) }"
            >
              {{ healthLabel(riskAnalysis.overall_health) }}
            </div>
          </div>

          <div class="risk-summary-section">
            <h4>AI 综合判断</h4>
            <p class="risk-summary-text">{{ riskAnalysis.summary }}</p>
          </div>

          <div class="analysis-progress-section">
            <h4>项目进展</h4>
            <div class="analysis-metric-grid">
              <div class="analysis-metric-card">
                <span class="analysis-metric-label">任务总数</span>
                <strong class="analysis-metric-value">{{ projectOverview.total }}</strong>
              </div>
              <div class="analysis-metric-card success">
                <span class="analysis-metric-label">已完成</span>
                <strong class="analysis-metric-value">{{ projectOverview.done }}</strong>
              </div>
              <div class="analysis-metric-card warning">
                <span class="analysis-metric-label">进行中</span>
                <strong class="analysis-metric-value">{{ projectOverview.inProgress }}</strong>
              </div>
              <div class="analysis-metric-card">
                <span class="analysis-metric-label">未开始</span>
                <strong class="analysis-metric-value">{{ projectOverview.notStarted }}</strong>
              </div>
              <div class="analysis-metric-card danger">
                <span class="analysis-metric-label">已逾期</span>
                <strong class="analysis-metric-value">{{ projectOverview.overdue }}</strong>
              </div>
              <div class="analysis-metric-card primary">
                <span class="analysis-metric-label">整体进度</span>
                <strong class="analysis-metric-value">{{ projectOverview.avgProgress }}%</strong>
              </div>
            </div>
            <p class="risk-summary-text analysis-progress-text">{{ projectProgressNarrative }}</p>
            <div class="analysis-notes-grid">
              <div class="analysis-note-panel">
                <span class="analysis-note-title">进展要点</span>
                <ul class="analysis-note-list">
                  <li v-for="item in progressHighlights" :key="item">{{ item }}</li>
                </ul>
              </div>
              <div class="analysis-note-panel warning">
                <span class="analysis-note-title">当前阻塞</span>
                <ul class="analysis-note-list">
                  <li v-for="item in progressBlockers" :key="item">{{ item }}</li>
                </ul>
              </div>
            </div>
          </div>

          <div class="priority-list-section">
            <h4>优先级建议</h4>
            <div v-if="aiPriorityRecommendations.length" class="priority-cards">
              <div
                v-for="item in aiPriorityRecommendations"
                :key="`${item.title}-${item.reason}`"
                class="priority-card"
              >
                <div class="priority-card-head">
                  <el-tag :type="(severityTagType(item.urgency || 'medium') as any)" size="small" effect="dark">
                    {{ urgencyLabel(item.urgency || 'medium') }}
                  </el-tag>
                  <span class="priority-card-title">{{ item.title }}</span>
                </div>
                <div v-if="item.affected_tasks?.length || item.affected_users?.length" class="priority-card-meta">
                  <span v-if="item.affected_tasks?.length">任务：{{ item.affected_tasks.join('、') }}</span>
                  <span v-if="item.affected_users?.length">成员：{{ item.affected_users.join('、') }}</span>
                </div>
                <p class="priority-card-reason">{{ item.reason }}</p>
                <p v-if="item.suggestion" class="priority-card-suggestion">{{ item.suggestion }}</p>
              </div>
            </div>
            <div v-else-if="priorityInsights.actionItems.length" class="priority-cards">
              <div v-for="item in priorityInsights.actionItems" :key="item.id" class="priority-card">
                <div class="priority-card-head">
                  <el-tag :type="(severityTagType(item.urgency) as any)" size="small" effect="dark">
                    {{ urgencyLabel(item.urgency) }}
                  </el-tag>
                  <span class="priority-card-title">{{ item.title }}</span>
                </div>
                <div class="priority-card-meta">
                  <span>{{ item.assigneeText }}</span>
                  <span>{{ formatDate(item.deadline) }}</span>
                  <span>{{ item.progressPct }}%</span>
                </div>
                <p class="priority-card-reason">{{ item.reason }}</p>
              </div>
            </div>
            <el-empty v-else description="暂无需要优先推进的任务" :image-size="60" />
          </div>

          <div class="priority-list-section">
            <h4>关键节点</h4>
            <div v-if="priorityInsights.keyNodes.length" class="priority-cards">
              <div v-for="item in priorityInsights.keyNodes" :key="item.id" class="priority-card node-card">
                <div class="priority-card-head">
                  <el-tag :type="(severityTagType(item.urgency) as any)" size="small" effect="plain">
                    {{ urgencyLabel(item.urgency) }}
                  </el-tag>
                  <span class="priority-card-title">{{ item.title }}</span>
                </div>
                <div class="priority-card-meta">
                  <span>{{ item.assigneeText }}</span>
                  <span>{{ formatDate(item.deadline) }}</span>
                  <span>{{ item.progressPct }}%</span>
                </div>
                <p class="priority-card-reason">{{ item.reason }}</p>
              </div>
            </div>
            <el-empty v-else description="暂无需要特别关注的关键节点" :image-size="60" />
          </div>

          <div class="risk-list-section">
            <h4>风险明细 ({{ riskAnalysis.risks?.length || 0 }})</h4>
            <div v-if="riskAnalysis.risks && riskAnalysis.risks.length > 0" class="risk-cards">
              <el-card
                v-for="(risk, idx) in riskAnalysis.risks"
                :key="idx"
                class="risk-card"
                shadow="hover"
              >
                <div class="risk-card-header">
                  <el-tag :type="(severityTagType(risk.severity) as any)" size="small" effect="dark">
                    {{ severityLabel(risk.severity) }}
                  </el-tag>
                  <el-tag size="small" effect="plain">{{ risk.type }}</el-tag>
                  <span class="risk-card-title">{{ risk.title }}</span>
                </div>
                <p class="risk-card-desc">{{ risk.description }}</p>
                <div v-if="risk.affected_tasks && risk.affected_tasks.length > 0" class="risk-card-tags">
                  <span class="risk-tag-label">受影响任务</span>
                  <el-tag
                    v-for="t in risk.affected_tasks"
                    :key="t"
                    size="small"
                    type="info"
                    class="risk-tag-item"
                  >
                    {{ t }}
                  </el-tag>
                </div>
                <div v-if="risk.affected_users && risk.affected_users.length > 0" class="risk-card-tags">
                  <span class="risk-tag-label">受影响人员</span>
                  <el-tag
                    v-for="u in risk.affected_users"
                    :key="u"
                    size="small"
                    type="warning"
                    class="risk-tag-item"
                  >
                    {{ u }}
                  </el-tag>
                </div>
                <div v-if="risk.suggestion" class="risk-suggestion">
                  <strong>建议:</strong> {{ risk.suggestion }}
                </div>
              </el-card>
            </div>
            <el-empty v-else description="暂无风险项" :image-size="60" />
          </div>
        </template>
        <el-empty v-if="!loadingRisk && !riskAnalysis" description="暂无项目分析结果" :image-size="80" />
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.task-board-view {
  padding: 16px;
  height: calc(100vh - 120px);
  position: relative;
}

.board-container {
  display: flex;
  gap: 16px;
  height: 100%;
  overflow-x: auto;
  padding-bottom: 8px;
}

.board-column {
  flex: 0 0 280px;
  display: flex;
  flex-direction: column;
  background: #f5f7fa;
  border-radius: 8px;
  overflow: hidden;
}

.column-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #fff;
  border-top: 3px solid #909399;
  font-weight: 600;
  font-size: 14px;
}

.column-title {
  color: #303133;
}

.column-body {
  flex: 1;
  padding: 8px;
  overflow-y: auto;
  min-height: 100px;
}

.task-card {
  background: #fff;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 8px;
  border-left: 4px solid #909399;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  cursor: pointer;
  transition: box-shadow 0.2s;
}

.task-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.ghost-card {
  opacity: 0.4;
  background: #e6f7ff;
}

.task-title {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
  line-height: 1.4;
  display: flex;
  align-items: center;
  gap: 6px;
}

.subtask-badge {
  flex-shrink: 0;
  font-size: 10px;
  padding: 0 4px;
  height: 18px;
  line-height: 16px;
  border-radius: 3px;
}

.task-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.assignee {
  font-size: 12px;
  color: #909399;
}

.task-deadline {
  font-size: 11px;
  color: #909399;
  margin-bottom: 6px;
}

.task-deadline.overdue {
  color: #f56c6c;
  font-weight: 600;
}

.task-progress {
  margin-top: 4px;
}

.signoff-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 8px;
}

.create-ai-wrap {
  width: 100%;
}

.create-ai-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.create-ai-status {
  font-size: 12px;
  color: #e6a23c;
  animation: pulse 1.5s infinite;
}

.create-ai-box {
  margin-top: 10px;
  padding: 10px 12px;
  border: 1px solid #faecd8;
  border-radius: 6px;
  background: #fdf6ec;
}

.create-ai-head {
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #b88230;
}

.create-ai-estimate {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  font-size: 12px;
  color: #303133;
}

.create-ai-reason {
  margin-bottom: 8px;
  font-size: 12px;
  line-height: 1.5;
  color: #606266;
}

.create-ai-recs-title {
  margin-bottom: 4px;
  font-size: 12px;
  font-weight: 600;
  color: #303133;
}

.create-ai-rec {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  border-top: 1px solid #faecd8;
  flex-wrap: wrap;
}

.create-ai-rank {
  font-weight: 700;
  color: #b88230;
}

.create-ai-name {
  font-weight: 500;
  color: #303133;
}

.create-ai-rec-reason {
  width: 100%;
  font-size: 11px;
  line-height: 1.5;
  color: #909399;
}

/* Floating action buttons */
.fab-button {
  position: fixed;
  right: 40px;
  bottom: 40px;
  width: 56px;
  height: 56px;
  font-size: 24px;
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.4);
  z-index: 100;
}

.fab-button-risk {
  position: fixed;
  right: 40px;
  bottom: 110px;
  width: 56px;
  height: 56px;
  font-size: 24px;
  box-shadow: 0 4px 12px rgba(230, 162, 60, 0.4);
  z-index: 100;
}

/* Drawer content */
.drawer-content {
  padding: 0 8px;
}

.detail-section {
  margin-bottom: 24px;
}

.detail-section h4 {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 12px 0;
  color: #303133;
}

.detail-signoff {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  flex-wrap: wrap;
}

.signoff-assist {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid #faecd8;
  background: #fdf6ec;
  font-size: 12px;
  color: #606266;
}

.signoff-assist p {
  margin: 6px 0;
  line-height: 1.5;
}

.signoff-assist ul {
  margin: 4px 0 0;
  padding-left: 18px;
}

.task-description {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
  margin: 0;
  white-space: pre-wrap;
}

.overdue {
  color: #f56c6c;
  font-weight: 600;
}

.progress-log-item {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  font-size: 13px;
}

.log-user {
  font-weight: 500;
  color: #409eff;
}

.log-pct {
  color: #303133;
}

.log-hours {
  color: #909399;
}

.log-note {
  width: 100%;
  margin: 4px 0 0 0;
  font-size: 12px;
  color: #606266;
}

/* Subtask section */
.section-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}

.section-header-row h4 {
  margin: 0 !important;
}

.section-header-actions {
  display: flex;
  gap: 8px;
}

.subtask-inline-form {
  background: #f5f7fa;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 12px;
}

.full-assignee-select :deep(.el-select__wrapper) {
  min-height: 32px;
  align-items: flex-start;
  padding-top: 4px;
  padding-bottom: 4px;
}

.full-assignee-select :deep(.el-select__selection) {
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}

.full-assignee-select :deep(.el-tag) {
  height: auto;
  min-height: 24px;
  margin: 2px 0;
  white-space: normal;
}

/* AI Decompose Dialog */
.decompose-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #ebeef5;
}

.decompose-count {
  font-size: 13px;
  color: #909399;
}

.decompose-list {
  max-height: 450px;
  overflow-y: auto;
}

.decompose-item {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 10px;
  transition: border-color 0.2s;
}

.decompose-item:hover {
  border-color: #409eff;
}

.decompose-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.decompose-item-title {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
  flex: 1;
}

.decompose-item-desc {
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
  margin-bottom: 6px;
  padding-left: 24px;
}

.decompose-item-meta {
  padding-left: 24px;
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.decompose-meta-label strong {
  color: #303133;
}

.decompose-item-reason {
  padding-left: 24px;
  font-size: 12px;
  color: #e6a23c;
  background: #fdf6ec;
  border-radius: 4px;
  padding: 6px 8px 6px 24px;
  margin-top: 6px;
  line-height: 1.4;
}

/* Risk Analysis Drawer */
.risk-drawer-content {
  padding: 0 8px;
  min-height: 200px;
}

.risk-health-section {
  display: flex;
  justify-content: center;
  margin-bottom: 20px;
}

.health-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 80px;
  height: 80px;
  border-radius: 50%;
  color: #fff;
  font-size: 20px;
  font-weight: 700;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
}

.risk-summary-section {
  margin-bottom: 20px;
}

.risk-summary-section h4 {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 8px 0;
  color: #303133;
}

.risk-summary-text {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
  margin: 0;
  background: #f5f7fa;
  border-radius: 6px;
  padding: 10px 12px;
}

.analysis-progress-section {
  margin-bottom: 20px;
}

.analysis-progress-section h4 {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 12px 0;
  color: #303133;
}

.analysis-metric-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.analysis-metric-card {
  padding: 12px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fff;
}

.analysis-metric-card.primary {
  background: #ecf5ff;
}

.analysis-metric-card.success {
  background: #f0f9eb;
}

.analysis-metric-card.warning {
  background: #fdf6ec;
}

.analysis-metric-card.danger {
  background: #fef0f0;
}

.analysis-metric-label {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
  color: #909399;
}

.analysis-metric-value {
  font-size: 20px;
  font-weight: 700;
  color: #303133;
}

.analysis-progress-text {
  margin-bottom: 12px;
}

.analysis-notes-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.analysis-note-panel {
  padding: 12px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid #ebeef5;
}

.analysis-note-panel.warning {
  background: #fff7ed;
}

.analysis-note-title {
  display: block;
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 600;
  color: #909399;
}

.analysis-note-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}

.analysis-note-list li + li {
  margin-top: 4px;
}

.risk-list-section h4 {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 12px 0;
  color: #303133;
}

.risk-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.risk-card {
  border-radius: 8px;
}

.risk-card :deep(.el-card__body) {
  padding: 14px;
}

.risk-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.risk-card-title {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

.risk-card-desc {
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
  margin: 0 0 8px 0;
}

.risk-card-tags {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 6px;
}

.risk-tag-label {
  font-size: 12px;
  color: #909399;
  margin-right: 4px;
}

.risk-tag-item {
  margin: 0;
}

.risk-suggestion {
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 10px;
  font-size: 13px;
  color: #409eff;
  margin-top: 8px;
  line-height: 1.5;
}

.risk-suggestion strong {
  color: #303133;
}

.priority-list-section {
  margin: 16px 0;
}

.priority-list-section h4 {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 12px;
  color: #303133;
}

.priority-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.priority-card {
  padding: 12px 14px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fff;
}

.node-card {
  background: #f8fafc;
}

.priority-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.priority-card-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.priority-card-meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 8px;
  font-size: 12px;
  color: #909399;
}

.priority-card-reason {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: #606266;
}

.priority-card-suggestion {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: #409eff;
}

.project-summary-card {
  margin-bottom: 16px;
  padding: 18px 20px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fff;
}

.project-summary-head h2 {
  margin: 0 0 12px;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.project-summary-grid {
  display: grid;
  gap: 12px;
}

.project-summary-section {
  padding: 14px 16px;
  border-radius: 8px;
  background: #f8fafc;
}

.project-summary-label {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #909399;
}

.project-summary-section p {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: #606266;
  white-space: pre-wrap;
}
</style>
