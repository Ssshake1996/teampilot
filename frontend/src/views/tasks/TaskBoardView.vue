<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus, Warning } from '@element-plus/icons-vue'
import draggable from 'vuedraggable'
import { useMediaQuery } from '@vueuse/core'
import { projectsApi } from '@/api/projects'
import { tasksApi } from '@/api/tasks'

import { usersApi } from '@/api/users'
import { fetchAllPages } from '@/utils/pagination'
import { taskViewKey, safeTaskReturnPath } from '@/utils/taskViewState'
import { useProjectUpdates } from '@/composables/useProjectUpdates'
import TaskDataSkillPanel from '@/components/tasks/TaskDataSkillPanel.vue'
import TaskAuditTrail from '@/components/tasks/TaskAuditTrail.vue'
import { useTaskStore } from '@/stores/task'
import { useAuthStore } from '@/stores/auth'
import { TaskStatus, TaskPriority, TaskStatusLabel, TaskPriorityLabel, PriorityColor } from '@/types/enums'
import type { Project, Task, TaskProgress, User } from '@/types/models'
import type { FormInstance } from 'element-plus'

const route = useRoute()
const router = useRouter()
const projectId = route.params.id as string
const taskStore = useTaskStore()
const auth = useAuthStore()

const loading = ref(false)
const boardError = ref('')
const routeTaskError = ref('')
const boardUpdatedAt = ref('')
const boardElement = ref<HTMLElement>()
const boardStateKey = taskViewKey(auth.user?.id || 'anonymous', projectId, 'board')
let savedBoard: { activeColumn?: TaskStatus; scrollTop?: number } = {}
try { savedBoard = JSON.parse(sessionStorage.getItem(boardStateKey) || '{}') || {} } catch { /* Ignore damaged local state. */ }
function saveBoardView() {
  try { sessionStorage.setItem(boardStateKey, JSON.stringify({ activeColumn: activeColumn.value,
    scrollTop: boardElement.value?.closest('.app-content')?.scrollTop || 0 })) } catch { /* Optional continuity. */ }
}
onBeforeUnmount(saveBoardView)
const sourcePath = computed(() => safeTaskReturnPath(route.query.from))
function returnToSource() { router.push(sourcePath.value || `/projects/${projectId}/tasks`) }
function goToList() { router.push(`/projects/${projectId}/tasks`) }
const project = ref<Project | null>(null)
const users = ref<User[]>([])
const mobileBoard = useMediaQuery('(max-width: 760px)')
const activeColumn = ref(Object.values(TaskStatus).includes(savedBoard.activeColumn as TaskStatus) ? savedBoard.activeColumn! : TaskStatus.IN_PROGRESS)
const columnLimit = ref<Record<string, number>>({ not_started: 100, in_progress: 100, done: 100 })
const canCreateTask = computed(() => auth.can('task.create'))
const canSignoffTask = computed(() => auth.can('task.signoff'))
const canSubmitProgress = computed(() => auth.can('progress.submit'))

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
    columnTasks.value[col.status] = taskStore.tasksByStatus(col.status).slice(0, columnLimit.value[col.status])
  }
}

function columnCount(status: TaskStatus): number {
  return taskStore.tasksByStatus(status).length
}
function showMore(status: TaskStatus) { columnLimit.value[status] = (columnLimit.value[status] || 100) + 100; syncColumnsFromStore() }

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

  createDialogVisible.value = true
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
const progressError = ref('')
const progressUpdatedAt = ref('')
const submittingProgress = ref(false)
let progressRequest = 0
let progressTaskId = ''

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

function projectContactText(): string {
  return project.value?.contact_names?.join('、') || project.value?.owner_name || '-'
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

async function openTaskDrawer(task: Task, updateRoute = true) {
  selectedTask.value = task
  showSubtaskForm.value = false
  activeColumn.value = task.status
  routeTaskError.value = ''
  if (updateRoute && route.query.taskId !== task.id) void router.replace({ query: { ...route.query, taskId: task.id } })

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
  const request = ++progressRequest
  if (progressTaskId !== taskId) { progressHistory.value = []; progressUpdatedAt.value = '' }
  progressTaskId = taskId
  progressError.value = ''
  if (!auth.can('progress.view')) { loadingProgress.value = false; progressError.value = '当前账号没有查看进展记录的权限。'; return }
  loadingProgress.value = true
  try {
    const res = await tasksApi.getProgress(taskId)
    if (request !== progressRequest || selectedTask.value?.id !== taskId) return
    progressHistory.value = res.data
    progressUpdatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } catch {
    if (request === progressRequest && selectedTask.value?.id === taskId) progressError.value = '进展记录加载失败，请重试。'
  } finally {
    if (request === progressRequest) loadingProgress.value = false
  }
}

async function handleLogProgress() {
  if (submittingProgress.value || !selectedTask.value) return
  if (selectedTask.value.is_deleted) {
    ElMessage.warning('已删除任务不支持反馈进展')
    return
  }
  if (!progressForm.value.note.trim()) {
    ElMessage.warning('请填写进展说明')
    return
  }
  const taskId = selectedTask.value.id
  submittingProgress.value = true
  try {
    const data: { progress_pct: number; note?: string; hours_spent?: number } = {
      progress_pct: progressForm.value.progress_pct,
    }
    if (progressForm.value.note) data.note = progressForm.value.note
    if (progressForm.value.hours_spent !== null) data.hours_spent = progressForm.value.hours_spent
    await tasksApi.logProgress(taskId, data)
    ElMessage.success('进度已更新')
    await loadTasks()
    if (selectedTask.value?.id === taskId) {
      progressForm.value.note = ''
      progressForm.value.hours_spent = null
      progressForm.value.progress_pct = selectedTask.value.progress_pct
      await loadProgressHistory(taskId)
    }
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '更新进度失败')
  } finally { submittingProgress.value = false }
}

async function handleDataSkillProgressAdopted(entry: TaskProgress) {
  if (!selectedTask.value) return
  await loadTasks()
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

async function loadTasks() {
  loading.value = true
  boardError.value = ''
  try {
    await taskStore.fetchTasks(projectId, { page_size: 500 }, true)
    syncColumnsFromStore()
    boardUpdatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    if (selectedTask.value) selectedTask.value = taskStore.tasks.find(task => task.id === selectedTask.value?.id) || null
  } catch {
    boardError.value = '任务加载失败，请重试。'
  } finally {
    loading.value = false
  }
}

async function fetchUsers() {
  try {
    users.value = await fetchAllPages(page => usersApi.list(page, 500))
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
  weight: number
  progress_pct: number
  is_deleted: boolean
}

const subtasks = ref<SubtaskItem[]>([])
const loadingSubtasks = ref(false)
const subtasksError = ref('')
let subtasksRequest = 0
let subtasksTaskId = ''
const showSubtaskForm = ref(false)
const creatingSubtask = ref(false)

const subtaskForm = ref({
  title: '',
  assignee_ids: [] as string[],
  estimated_hours: null as number | null,
  deadline: '',
})

async function loadSubtasks(taskId: string) {
  const request = ++subtasksRequest
  if (subtasksTaskId !== taskId) subtasks.value = []
  subtasksTaskId = taskId
  loadingSubtasks.value = true
  subtasksError.value = ''
  try {
    const res = await tasksApi.getSubtasks(taskId)
    if (request === subtasksRequest && selectedTask.value?.id === taskId) subtasks.value = res.data
  } catch {
    if (request === subtasksRequest && selectedTask.value?.id === taskId) subtasksError.value = '子任务加载失败，请重试。'
  } finally {
    if (request === subtasksRequest) loadingSubtasks.value = false
  }
}

const selectedChildren = computed(() => taskStore.tasks.filter(task => task.parent_task_id === selectedTask.value?.id && !task.is_deleted))
const selectedTaskHasChildren = computed(() => selectedChildren.value.length > 0)
const weightedProgressExplanation = computed(() => selectedChildren.value.map(task => `${task.title} ${task.progress_pct}% × 权重 ${Number(task.weight).toLocaleString('zh-CN', { maximumFractionDigits: 6 })}`).join(' + '))

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









function subtaskStatusType(status: TaskStatus): string {
  const map: Record<string, string> = {
    [TaskStatus.NOT_STARTED]: 'info',
    [TaskStatus.IN_PROGRESS]: 'warning',
    [TaskStatus.DONE]: 'success',
  }
  return map[status] || 'info'
}



















// ========== Feature 3: Subtask count on task cards ==========

function hasSubtasks(task: Task): boolean {
  return taskStore.tasks.some(child => child.parent_task_id === task.id && !child.is_deleted)
}

async function openTaskFromRoute() {
  const taskId = typeof route.query.taskId === 'string' ? route.query.taskId : ''
  if (!taskId || (drawerVisible.value && selectedTask.value?.id === taskId)) return
  routeTaskError.value = ''
  try {
    const task = taskStore.tasks.find(item => item.id === taskId) || (await tasksApi.get(taskId)).data
    if (route.query.taskId !== taskId) return
    if (task.project_id !== projectId) { routeTaskError.value = '此任务不属于当前项目。'; return }
    await openTaskDrawer(task, false)
  } catch { if (route.query.taskId === taskId) routeTaskError.value = '无法打开此任务，可能已不存在或无访问权限。' }
}
function closeTaskRoute() {
  ++progressRequest; ++subtasksRequest
  loadingProgress.value = false; loadingSubtasks.value = false
  selectedTask.value = null
  if (route.query.taskId) {
    const { taskId: _taskId, ...query } = route.query
    void router.replace({ query })
  }
}
watch(() => route.query.taskId, value => { if (!value) drawerVisible.value = false; else void openTaskFromRoute() })
// ========== Init ==========

useProjectUpdates(async pid => { if (!pid || pid === projectId) await Promise.all([loadTasks(), fetchProject()]) })
onMounted(async () => {
  await Promise.all([loadTasks(), fetchUsers(), fetchProject()])
  await nextTick()
  const content = boardElement.value?.closest('.app-content')
  if (content && typeof savedBoard.scrollTop === 'number') content.scrollTop = savedBoard.scrollTop
  await openTaskFromRoute()
})
</script>

<template>
  <div ref="boardElement" v-loading="loading" class="task-board-view">
    <div v-if="project" class="project-summary-card">
      <div class="project-summary-head">
        <h2>{{ project.name }}</h2>
        <div class="project-people"><span>接口人 <strong>{{ projectContactText() }}</strong></span><span>创建人 <strong>{{ project.owner_name || '-' }}</strong></span></div>
      </div>
      <div class="project-summary-tools">
      <details class="project-description"><summary>项目目标与描述</summary><div class="project-summary-grid">
        <div class="project-summary-section">
          <span class="project-summary-label">项目目标</span>
          <p>{{ project.goal || '暂无项目目标' }}</p>
        </div>
        <div class="project-summary-section">
          <span class="project-summary-label">项目描述</span>
          <p>{{ project.description || '暂无项目描述' }}</p>
        </div>
      </div></details>
      <div class="board-actions">
        <el-button v-if="sourcePath" @click="returnToSource">返回来源</el-button>
        <el-button @click="goToList">任务列表</el-button>

        <el-tooltip v-if="canCreateTask" content="新建任务" placement="top">
          <el-button type="primary" :icon="Plus" circle aria-label="新建任务" @click="openCreateDialog" />
        </el-tooltip>
      </div>
      </div>
    </div>
    <el-alert v-if="boardError || routeTaskError" type="error" show-icon :closable="false" class="board-error">
      <template #title>{{ boardError || routeTaskError }}<span v-if="boardError && boardUpdatedAt"> 已保留上次读取的数据（{{ boardUpdatedAt }}）。</span></template>
      <el-button link type="primary" @click="boardError ? loadTasks() : openTaskFromRoute()">重试</el-button>
    </el-alert>
    <p class="board-help">状态按开始时间自动判断；进度达到 100% 后由有权限的人员会签完成。</p>
    <el-radio-group v-if="mobileBoard" v-model="activeColumn" class="board-status-tabs" aria-label="任务状态">
      <el-radio-button v-for="col in columns" :key="col.status" :value="col.status">{{ col.label }} {{ columnCount(col.status) }}</el-radio-button>
    </el-radio-group>
    <div class="board-container">
      <div v-for="col in columns" v-show="!mobileBoard || activeColumn === col.status" :key="col.status" class="board-column">
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
                <button type="button" class="task-open" :aria-label="`查看任务：${task.title}`" @click.stop="openTaskDrawer(task)">{{ task.title }}</button>
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
        <el-button v-if="columnCount(col.status) > (columnTasks[col.status]?.length || 0)" class="load-more" text @click="showMore(col.status)">加载更多 ({{ columnCount(col.status) - (columnTasks[col.status]?.length || 0) }})</el-button>
      </div>
    </div>

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
      @closed="closeTaskRoute"
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
                <details v-if="selectedTaskHasChildren" class="progress-basis"><summary>由子任务加权计算</summary><p>{{ weightedProgressExplanation }}，按权重总和归一后四舍五入。</p><p>直接提交的历史百分比仅为原始记录，不覆盖父任务汇总进度。</p></details>
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
                v-if="canSignoff(selectedTask)"
                type="success"
                size="small"
                @click="handleSignoffTask(selectedTask)"
              >
                会签确认
              </el-button>
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
          <TaskAuditTrail v-if="auth.can('progress.view')" :task-id="selectedTask.id" :revision="selectedTask.updated_at" />

          <!-- Subtasks Section (Feature 1) -->
          <div class="detail-section">
            <div class="section-header-row">
              <h4>子任务</h4>
              <div class="section-header-actions">
                <el-button v-if="canCreateTask" size="small" @click="openSubtaskForm">手动添加子任务</el-button>

              </div>
            </div>

            <el-alert v-if="subtasksError" type="error" show-icon :closable="false" :title="subtasksError"><el-button link @click="loadSubtasks(selectedTask.id)">重试</el-button></el-alert>
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
              <el-empty v-else-if="!loadingSubtasks && !subtasksError" description="暂无子任务" :image-size="40" />
            </div>
          </div>

          <div class="detail-section">
            <el-alert
              type="info"
              :closable="false"
              show-icon
              title="在此填写真实进展说明和本次投入工时。提交后保留历史记录，进度达到 100% 后仍需会签完成。"
            />
          </div>

          <div v-if="canSubmitProgress && !selectedTask.is_deleted" class="detail-section">
            <h4>手动提交</h4>
            <el-form label-width="80px" size="small" :disabled="submittingProgress">
              <el-form-item label="进度 (%)">
                <el-slider v-model="progressForm.progress_pct" :min="0" :max="100" show-input :disabled="selectedTaskHasChildren" /><span v-if="selectedTaskHasChildren" class="field-hint">父任务进度自动计算；此处记录说明与工时。</span>
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
                <el-button type="primary" size="default" :loading="submittingProgress" :disabled="submittingProgress" @click="handleLogProgress">提交进展</el-button>
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
            <el-alert v-if="progressError" type="error" :closable="false" show-icon :title="progressError"><el-button v-if="auth.can('progress.view')" link @click="loadProgressHistory(selectedTask.id)">重试</el-button></el-alert>
            <p v-if="progressUpdatedAt" class="field-hint">{{ progressError ? '上次成功读取' : '读取时间' }} {{ progressUpdatedAt }}</p>
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
              <el-empty v-else-if="!progressError && !loadingProgress" description="暂无进度记录" :image-size="60" />
            </div>
          </div>
        </div>
      </template>
    </el-drawer>


  </div>
</template>

<style scoped>
.board-error { margin: 12px 0; }
.board-help, .field-hint { color: var(--muted); font-size: 12px; line-height: 1.6; margin: 8px 0; }
.progress-basis { color: var(--muted); font-size: 12px; line-height: 1.6; }
.progress-basis summary { cursor: pointer; color: var(--brand); }
.task-open { padding: 0; border: 0; background: transparent; color: inherit; text-align: left; font: inherit; font-weight: inherit; cursor: pointer; }
.task-card:focus-within { outline: 2px solid var(--brand); outline-offset: 2px; }

.task-board-view {
  padding: 16px;
  height: calc(100vh - 120px);
  position: relative;
}

.board-container {
  display: flex;
  gap: 16px;
  height: min(68vh, 800px);
  overflow-x: auto;
  padding-bottom: 8px;
}

.board-column {
  flex: 1 0 280px;
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
  border-top: 1px solid #e5ebed;
  border-right: 1px solid #e5ebed;
  border-bottom: 1px solid #e5ebed;
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

/* Risk Analysis Drawer */

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

.analysis-note-panel.warning {
  background: #fff7ed;
}

.project-summary-card {
  margin-bottom: 16px;
  padding: 0 0 16px;
  border-bottom: 1px solid var(--border);
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
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.project-summary-section {
  padding: 12px 0;
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
.project-summary-head { display: flex; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
.project-summary-head h2 { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.project-people { display: flex; gap: 16px; flex-wrap: wrap; color: var(--muted); font-size: 12px; line-height: 28px; }
.project-people strong { color: var(--ink); font-weight: 500; margin-left: 6px; }
.project-description summary { color: var(--muted); cursor: pointer; font-size: 13px; }
.project-summary-tools { display: flex; align-items: flex-start; gap: 16px; }
.project-description { flex: 1; min-width: 0; }
.board-actions { display: flex; flex-shrink: 0; gap: 8px; }
.board-actions .el-button + .el-button { margin-left: 0; }
.load-more { width: 100%; flex-shrink: 0; }
@media (max-width: 760px) {
  .project-summary-head { display: block; }
  .project-summary-grid { grid-template-columns: 1fr; }
  .board-column { flex: 1 0 100%; min-width: 0; }
  .task-meta { flex-wrap: wrap; gap: 6px; }
}
.board-status-tabs { display: flex; margin-bottom: 12px; }
.board-status-tabs :deep(.el-radio-button) { flex: 1; }
.board-status-tabs :deep(.el-radio-button__inner) { width: 100%; padding: 9px 8px; }
</style>
