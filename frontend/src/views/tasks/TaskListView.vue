<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { View, Edit, Delete } from '@element-plus/icons-vue'
import { projectsApi } from '@/api/projects'
import { tasksApi } from '@/api/tasks'
import { usersApi } from '@/api/users'
import { fetchAllPages } from '@/utils/pagination'
import { useAuthStore } from '@/stores/auth'
import { parseTaskListState, taskViewKey } from '@/utils/taskViewState'
import { useProjectUpdates } from '@/composables/useProjectUpdates'
import { TaskStatus, TaskPriority, TaskStatusLabel, TaskPriorityLabel } from '@/types/enums'
import type { Project, Task, User } from '@/types/models'

const route = useRoute()
const router = useRouter()
const projectId = route.params.id as string
const auth = useAuthStore()
const stateKey = taskViewKey(auth.user?.id || 'anonymous', projectId)
let savedState = parseTaskListState(null)
try { savedState = parseTaskListState(sessionStorage.getItem(stateKey)) } catch { /* Storage may be unavailable. */ }
const viewElement = ref<HTMLElement>()
const listError = ref('')
const updatedAt = ref('')
let listRequest = 0
const sortBy = ref(savedState.sortBy)
const sortOrder = ref<'asc' | 'desc'>(savedState.sortOrder)
function saveView() {
  try {
    sessionStorage.setItem(stateKey, JSON.stringify({ page: currentPage.value, pageSize: pageSize.value,
      status: filterStatus.value, assignee: filterAssignee.value, priority: filterPriority.value,
      sortBy: sortBy.value, sortOrder: sortOrder.value,
      scrollTop: viewElement.value?.closest('.app-content')?.scrollTop || 0 }))
  } catch { /* Navigation still works when storage is disabled. */ }
}
onBeforeUnmount(saveView)

const project = ref<Project | null>(null)
const tasks = ref<Task[]>([])
const total = ref(0)
const loading = ref(false)
const users = ref<User[]>([])
const currentPage = ref(savedState.page)
const pageSize = ref(savedState.pageSize)

// Filters
const filterStatus = ref(savedState.status)
const filterAssignee = ref(savedState.assignee)
const filterPriority = ref(savedState.priority)

const statusOptions = [
  { label: '全部状态', value: '' },
  { label: TaskStatusLabel[TaskStatus.NOT_STARTED], value: TaskStatus.NOT_STARTED },
  { label: TaskStatusLabel[TaskStatus.IN_PROGRESS], value: TaskStatus.IN_PROGRESS },
  { label: TaskStatusLabel[TaskStatus.DONE], value: TaskStatus.DONE },
]

const priorityOptions = [
  { label: '全部优先级', value: '' },
  { label: TaskPriorityLabel[TaskPriority.LOW], value: TaskPriority.LOW },
  { label: TaskPriorityLabel[TaskPriority.MEDIUM], value: TaskPriority.MEDIUM },
  { label: TaskPriorityLabel[TaskPriority.HIGH], value: TaskPriority.HIGH },
  { label: TaskPriorityLabel[TaskPriority.URGENT], value: TaskPriority.URGENT },
]

function statusTagType(status: TaskStatus): string {
  const map: Record<string, string> = {
    [TaskStatus.NOT_STARTED]: 'info',
    [TaskStatus.IN_PROGRESS]: 'warning',
    [TaskStatus.DONE]: 'success',
  }
  return map[status] || 'info'
}

function displayStatusType(task: Task): string {
  return task.is_deleted ? 'info' : statusTagType(task.status)
}

function displayStatusLabel(task: Task): string {
  return task.is_deleted ? '已删除' : (TaskStatusLabel[task.status as TaskStatus] || task.status)
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

function isOverdue(task: Task): boolean {
  if (!task.deadline || task.status === TaskStatus.DONE) return false
  return new Date(task.deadline) < new Date()
}

async function fetchTasks() {
  const request = ++listRequest
  loading.value = true
  listError.value = ''
  try {
    const params: Record<string, any> = {
      page: currentPage.value,
      page_size: pageSize.value,
      sort_by: sortBy.value, sort_order: sortOrder.value,
    }
    if (filterStatus.value) params.status = filterStatus.value
    if (filterAssignee.value) params.user_id = filterAssignee.value
    if (filterPriority.value) params.priority = filterPriority.value
    const res = await tasksApi.list(projectId, params)
    if (request !== listRequest) return
    tasks.value = res.data.items
    total.value = res.data.total
    updatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    if (currentPage.value > Math.max(1, Math.ceil(total.value / pageSize.value))) {
      currentPage.value = Math.max(1, Math.ceil(total.value / pageSize.value))
      await fetchTasks()
    }
  } catch {
    if (request === listRequest) listError.value = '加载任务列表失败，请重试。'
  } finally {
    if (request === listRequest) loading.value = false
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

function handleFilter() {
  currentPage.value = 1
  fetchTasks()
}

function handlePageChange(page: number) {
  currentPage.value = page
  fetchTasks()
}

function handleSizeChange(size: number) {
  pageSize.value = size
  currentPage.value = 1
  fetchTasks()
}

function goToBoard(task?: Task) {
  saveView()
  router.push({ path: `/projects/${projectId}/board`, query: { from: route.fullPath, ...(task ? { taskId: task.id } : {}) } })
}
function handleSort({ prop, order }: { prop?: string; order?: string | null }) {
  sortBy.value = order && prop ? prop : 'created_at'
  sortOrder.value = order === 'ascending' ? 'asc' : 'desc'
  currentPage.value = 1
  void fetchTasks()
}

async function handleDeleteTask(task: Task) {
  try {
    await tasksApi.delete(task.id)
    ElMessage.success('任务已标记删除')
    await fetchTasks()
  } catch {
    ElMessage.error('删除任务失败')
  }
}

async function handleRestoreTask(task: Task) {
  try {
    await tasksApi.restore(task.id)
    ElMessage.success('任务已恢复')
    await fetchTasks()
  } catch {
    ElMessage.error('恢复任务失败')
  }
}

useProjectUpdates(async pid => { if (!pid || pid === projectId) await Promise.all([fetchTasks(), fetchProject()]) })
onMounted(async () => {
  await Promise.all([fetchTasks(), fetchUsers(), fetchProject()])
  await nextTick()
  const content = viewElement.value?.closest('.app-content')
  if (content) content.scrollTop = savedState.scrollTop
})
</script>

<template>
  <div ref="viewElement" class="task-list-view">
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
    <div class="page-header">
      <h2>任务列表</h2>
      <el-button @click="goToBoard()">看板视图</el-button>
    </div>

    <!-- Filter Bar -->
    <div class="filter-bar">
      <el-select
        v-model="filterStatus"
        placeholder="状态筛选"
        clearable
        style="width: 150px"
        @change="handleFilter"
      >
        <el-option
          v-for="opt in statusOptions"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>

      <el-select
        v-model="filterPriority"
        placeholder="优先级筛选"
        clearable
        style="width: 150px"
        @change="handleFilter"
      >
        <el-option
          v-for="opt in priorityOptions"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>

      <el-select
        v-model="filterAssignee"
        placeholder="负责人筛选"
        clearable
        filterable
        style="width: 180px"
        @change="handleFilter"
      >
        <el-option label="全部负责人" value="" />
        <el-option
          v-for="user in users"
          :key="user.id"
          :label="user.full_name"
          :value="user.id"
        />
      </el-select>
    </div>

    <el-alert v-if="listError" type="error" :closable="false" show-icon class="list-error">
      <template #title>{{ listError }}<span v-if="tasks.length"> 当前保留上次读取的数据。</span></template>
      <el-button link type="primary" @click="fetchTasks">重试</el-button>
    </el-alert>
    <p class="data-note">排序覆盖全部匹配任务。<span v-if="updatedAt">上次读取 {{ updatedAt }}</span></p>
    <!-- Task Table -->
    <el-table
      v-loading="loading"
      :data="tasks"
      stripe
      style="width: 100%"
      :default-sort="{ prop: sortBy, order: sortOrder === 'asc' ? 'ascending' : 'descending' }"
      @sort-change="handleSort"
    >
      <el-table-column prop="title" label="任务标题" min-width="200" sortable="custom">
        <template #default="{ row }">
          <div class="task-main-cell">
            <button type="button" class="task-title-cell task-link" :class="{ deleted: row.is_deleted }" @click="goToBoard(row)">{{ row.title }}</button>
            <span v-if="row.description" class="task-desc-cell">{{ row.description }}</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column prop="status" label="状态" width="110" sortable="custom">
        <template #default="{ row }">
          <el-tag :type="(displayStatusType(row) as any)" size="small">
            {{ displayStatusLabel(row) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column prop="priority" label="优先级" width="100" sortable="custom">
        <template #default="{ row }">
          <el-tag :type="(priorityTagType(row.priority) as any)" size="small" effect="light">
            {{ TaskPriorityLabel[row.priority as TaskPriority] || row.priority }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column prop="assignee_name" label="负责人" width="120" sortable="custom">
        <template #default="{ row }">
          {{ row.assignee_names?.join('、') || row.assignee_name || '未指派' }}
        </template>
      </el-table-column>

      <el-table-column prop="deadline" label="截止日期" width="120" sortable="custom">
        <template #default="{ row }">
          <span :class="{ overdue: isOverdue(row) }">
            {{ formatDate(row.deadline) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column prop="progress_pct" label="进度" width="150" sortable="custom">
        <template #default="{ row }">
          <el-progress
            :percentage="row.progress_pct || 0"
            :stroke-width="8"
            :text-inside="true"
          />
        </template>
      </el-table-column>

      <el-table-column label="操作" width="120" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            type="primary"
            :icon="View"
            size="small"
            link
            @click="goToBoard(row)"
          >
            查看
          </el-button>
          <el-popconfirm
            title="确定要删除此任务吗？"
            v-if="!row.is_deleted && auth.can('task.delete')"
            @confirm="handleDeleteTask(row)"
          >
            <template #reference>
              <el-button
                type="danger"
                :icon="Delete"
                size="small"
                link
              >
                删除
              </el-button>
            </template>
          </el-popconfirm>
          <el-button
            v-else-if="row.is_deleted && auth.can('task.delete')"
            type="success"
            :icon="Edit"
            size="small"
            link
            @click="handleRestoreTask(row)"
          >
            恢复
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Pagination -->
    <div class="pagination-container">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        background
        @current-change="handlePageChange"
        @size-change="handleSizeChange"
      />
    </div>
  </div>
</template>

<style scoped>
.task-link { border: 0; background: transparent; color: var(--brand); text-align: left; cursor: pointer; padding: 2px 0; font: inherit; }
.list-error { margin-bottom: 12px; }
.data-note { margin: 0 0 10px; font-size: 12px; color: var(--muted); }
.data-note span { margin-left: 12px; }

.task-list-view {
  padding: 0;
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

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
}

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.task-title-cell {
  font-weight: 500;
}

.task-main-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.task-title-cell.deleted {
  color: #909399;
  text-decoration: line-through;
}

.task-desc-cell {
  font-size: 12px;
  line-height: 1.5;
  color: #909399;
  white-space: pre-wrap;
}

.overdue {
  color: #f56c6c;
  font-weight: 600;
}

.pagination-container {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
}
</style>
