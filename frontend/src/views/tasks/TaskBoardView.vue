<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus, Warning } from '@element-plus/icons-vue'
import draggable from 'vuedraggable'
import { tasksApi } from '@/api/tasks'
import { aiApi } from '@/api/ai'
import { usersApi } from '@/api/users'
import { useTaskStore } from '@/stores/task'
import { TaskStatus, TaskPriority, TaskStatusLabel, TaskPriorityLabel, PriorityColor } from '@/types/enums'
import type { Task, TaskProgress, User } from '@/types/models'
import type { FormInstance } from 'element-plus'

const route = useRoute()
const projectId = route.params.id as string
const taskStore = useTaskStore()

const loading = ref(false)
const users = ref<User[]>([])

// Kanban columns config
const columns = [
  { status: TaskStatus.BACKLOG, label: TaskStatusLabel[TaskStatus.BACKLOG] },
  { status: TaskStatus.TODO, label: TaskStatusLabel[TaskStatus.TODO] },
  { status: TaskStatus.IN_PROGRESS, label: TaskStatusLabel[TaskStatus.IN_PROGRESS] },
  { status: TaskStatus.IN_REVIEW, label: TaskStatusLabel[TaskStatus.IN_REVIEW] },
  { status: TaskStatus.DONE, label: TaskStatusLabel[TaskStatus.DONE] },
]

const columnHeaderColors: Record<string, string> = {
  [TaskStatus.BACKLOG]: '#909399',
  [TaskStatus.TODO]: '#409EFF',
  [TaskStatus.IN_PROGRESS]: '#E6A23C',
  [TaskStatus.IN_REVIEW]: '#9B59B6',
  [TaskStatus.DONE]: '#67C23A',
}

// Reactive column data: each column is an array of tasks
const columnTasks = ref<Record<string, Task[]>>({
  [TaskStatus.BACKLOG]: [],
  [TaskStatus.TODO]: [],
  [TaskStatus.IN_PROGRESS]: [],
  [TaskStatus.IN_REVIEW]: [],
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
  assignee_id: '',
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
    assignee_id: '',
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
    if (createForm.value.assignee_id) payload.assignee_id = createForm.value.assignee_id
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

async function openTaskDrawer(task: Task) {
  selectedTask.value = task
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
  } catch {
    ElMessage.error('更新进度失败')
  }
}

// Drag & drop
async function onDragEnd(status: TaskStatus) {
  const tasksInColumn = columnTasks.value[status]
  if (!tasksInColumn) return
  // Find tasks that changed columns (their status doesn't match the column)
  for (let i = 0; i < tasksInColumn.length; i++) {
    const task = tasksInColumn[i]
    if (!task) continue
    if (task.status !== status) {
      try {
        await tasksApi.updateStatus(task.id, status)
        taskStore.updateTaskLocally(task.id, { status, sort_order: i })
        // Update the local copy
        tasksInColumn[i] = { ...task, status, sort_order: i } as Task
      } catch {
        ElMessage.error('更新任务状态失败')
        await loadTasks()
        return
      }
    }
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

// ========== Feature 1: Subtask Decomposition ==========

interface SubtaskItem {
  id?: string
  title: string
  assignee_id: string | null
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
  assignee_id: '',
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
  subtaskForm.value = { title: '', assignee_id: '', estimated_hours: null, deadline: '' }
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
    if (subtaskForm.value.assignee_id) payload.assignee_id = subtaskForm.value.assignee_id
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
    const items = (res.data as any)?.subtasks || (res.data as any) || []
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
    [TaskStatus.BACKLOG]: 'info',
    [TaskStatus.TODO]: '',
    [TaskStatus.IN_PROGRESS]: 'warning',
    [TaskStatus.IN_REVIEW]: '',
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
}

const riskDrawerVisible = ref(false)
const loadingRisk = ref(false)
const riskAnalysis = ref<RiskAnalysis | null>(null)

async function openRiskAnalysis() {
  riskDrawerVisible.value = true
  loadingRisk.value = true
  riskAnalysis.value = null
  try {
    const res = await aiApi.analyzeRisk(projectId)
    riskAnalysis.value = res.data as any
  } catch {
    ElMessage.error('AI 风险分析失败，请稍后重试')
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
  await Promise.all([loadTasks(), fetchUsers()])
})
</script>

<template>
  <div v-loading="loading" class="task-board-view">
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
          @end="onDragEnd(col.status)"
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
                <span v-if="task.assignee_name" class="assignee">
                  {{ task.assignee_name }}
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
            </div>
          </template>
        </draggable>
      </div>
    </div>

    <!-- Floating Create Button -->
    <el-button
      class="fab-button"
      type="primary"
      :icon="Plus"
      circle
      size="large"
      @click="openCreateDialog"
    />

    <!-- AI Risk Analysis Floating Button -->
    <el-button
      class="fab-button-risk"
      type="warning"
      :icon="Warning"
      circle
      size="large"
      @click="openRiskAnalysis"
    />

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
            v-model="createForm.assignee_id"
            placeholder="选择负责人"
            clearable
            filterable
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
      size="480px"
      direction="rtl"
    >
      <template v-if="selectedTask">
        <div class="drawer-content">
          <!-- Basic Info -->
          <div class="detail-section">
            <h4>基本信息</h4>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="状态">
                <el-tag size="small">
                  {{ TaskStatusLabel[selectedTask.status as TaskStatus] || selectedTask.status }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="优先级">
                <el-tag :type="(priorityTagType(selectedTask.priority) as any)" size="small">
                  {{ TaskPriorityLabel[selectedTask.priority as TaskPriority] || selectedTask.priority }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="负责人">
                {{ selectedTask.assignee_name || '未指派' }}
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
              <el-descriptions-item label="创建时间">
                {{ formatDateTime(selectedTask.created_at) }}
              </el-descriptions-item>
            </el-descriptions>
          </div>

          <!-- Description -->
          <div class="detail-section">
            <h4>描述</h4>
            <p class="task-description">{{ selectedTask.description || '暂无描述' }}</p>
          </div>

          <!-- Subtasks Section (Feature 1) -->
          <div class="detail-section">
            <div class="section-header-row">
              <h4>子任务</h4>
              <div class="section-header-actions">
                <el-button size="small" @click="openSubtaskForm">手动添加子任务</el-button>
                <el-button size="small" type="primary" :loading="decomposing" @click="handleAIDecompose">AI 智能分解</el-button>
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
                    v-model="subtaskForm.assignee_id"
                    placeholder="选择负责人"
                    clearable
                    filterable
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
                    {{ row.assignee_name || '未分配' }}
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

          <!-- Progress Log Form -->
          <div class="detail-section">
            <h4>更新进度</h4>
            <el-form label-width="80px" size="small">
              <el-form-item label="进度 (%)">
                <el-slider v-model="progressForm.progress_pct" :min="0" :max="100" show-input />
              </el-form-item>
              <el-form-item label="备注">
                <el-input
                  v-model="progressForm.note"
                  type="textarea"
                  :rows="2"
                  placeholder="说明进展情况"
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
                <el-button type="primary" size="default" @click="handleLogProgress">提交进度</el-button>
              </el-form-item>
            </el-form>
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

    <!-- AI Risk Analysis Drawer (Feature 2) -->
    <el-drawer
      v-model="riskDrawerVisible"
      title="AI 风险分析"
      size="520px"
      direction="rtl"
    >
      <div v-loading="loadingRisk" element-loading-text="AI 正在分析项目风险..." class="risk-drawer-content">
        <template v-if="!loadingRisk && riskAnalysis">
          <!-- Overall Health Badge -->
          <div class="risk-health-section">
            <div
              class="health-badge"
              :style="{ backgroundColor: healthColor(riskAnalysis.overall_health) }"
            >
              {{ healthLabel(riskAnalysis.overall_health) }}
            </div>
          </div>

          <!-- Summary -->
          <div class="risk-summary-section">
            <h4>概况</h4>
            <p class="risk-summary-text">{{ riskAnalysis.summary }}</p>
          </div>

          <!-- Risk Items -->
          <div class="risk-list-section">
            <h4>风险列表 ({{ riskAnalysis.risks?.length || 0 }})</h4>
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
                  <span class="risk-tag-label">受影响任务:</span>
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
                  <span class="risk-tag-label">受影响人员:</span>
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
        <el-empty v-if="!loadingRisk && !riskAnalysis" description="暂无分析结果" :image-size="80" />
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
</style>
