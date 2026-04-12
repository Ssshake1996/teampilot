<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import draggable from 'vuedraggable'
import { tasksApi } from '@/api/tasks'
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
  await loadProgressHistory(task.id)
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
  // Find tasks that changed columns (their status doesn't match the column)
  for (let i = 0; i < tasksInColumn.length; i++) {
    const task = tasksInColumn[i]
    if (task.status !== status) {
      try {
        await tasksApi.updateStatus(task.id, status)
        taskStore.updateTaskLocally(task.id, { status, sort_order: i })
        // Update the local copy
        tasksInColumn[i] = { ...task, status, sort_order: i }
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
              <div class="task-title">{{ task.title }}</div>
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

/* Floating action button */
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
</style>
