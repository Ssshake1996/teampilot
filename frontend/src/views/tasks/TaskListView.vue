<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { View, Edit, Delete } from '@element-plus/icons-vue'
import { projectsApi } from '@/api/projects'
import { tasksApi } from '@/api/tasks'
import { usersApi } from '@/api/users'
import { TaskStatus, TaskPriority, TaskStatusLabel, TaskPriorityLabel } from '@/types/enums'
import type { Project, Task, User } from '@/types/models'

const route = useRoute()
const router = useRouter()
const projectId = route.params.id as string

const project = ref<Project | null>(null)
const tasks = ref<Task[]>([])
const total = ref(0)
const loading = ref(false)
const users = ref<User[]>([])
const currentPage = ref(1)
const pageSize = ref(20)

// Filters
const filterStatus = ref<string>('')
const filterAssignee = ref<string>('')
const filterPriority = ref<string>('')

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
  loading.value = true
  try {
    const params: Record<string, any> = {
      page: currentPage.value,
      page_size: pageSize.value,
    }
    if (filterStatus.value) params.status = filterStatus.value
    if (filterAssignee.value) params.user_id = filterAssignee.value
    // Priority filter is applied client-side since the API may not support it
    const res = await tasksApi.list(projectId, params)
    let items = res.data.items
    if (filterPriority.value) {
      items = items.filter((t) => t.priority === filterPriority.value)
    }
    tasks.value = items
    total.value = res.data.total
  } catch {
    ElMessage.error('加载任务列表失败')
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

function goToBoard() {
  router.push(`/projects/${projectId}/board`)
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

onMounted(async () => {
  await Promise.all([fetchTasks(), fetchUsers(), fetchProject()])
})
</script>

<template>
  <div class="task-list-view">
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
      <el-button @click="goToBoard">看板视图</el-button>
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

    <!-- Task Table -->
    <el-table
      v-loading="loading"
      :data="tasks"
      stripe
      style="width: 100%"
      :default-sort="{ prop: 'created_at', order: 'descending' }"
    >
      <el-table-column prop="title" label="任务标题" min-width="200" sortable>
        <template #default="{ row }">
          <div class="task-main-cell">
            <span class="task-title-cell" :class="{ deleted: row.is_deleted }">{{ row.title }}</span>
            <span v-if="row.description" class="task-desc-cell">{{ row.description }}</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column prop="status" label="状态" width="110" sortable>
        <template #default="{ row }">
          <el-tag :type="(displayStatusType(row) as any)" size="small">
            {{ displayStatusLabel(row) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column prop="priority" label="优先级" width="100" sortable>
        <template #default="{ row }">
          <el-tag :type="(priorityTagType(row.priority) as any)" size="small" effect="light">
            {{ TaskPriorityLabel[row.priority as TaskPriority] || row.priority }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column prop="assignee_name" label="负责人" width="120" sortable>
        <template #default="{ row }">
          {{ row.assignee_names?.join('、') || row.assignee_name || '未指派' }}
        </template>
      </el-table-column>

      <el-table-column prop="deadline" label="截止日期" width="120" sortable>
        <template #default="{ row }">
          <span :class="{ overdue: isOverdue(row) }">
            {{ formatDate(row.deadline) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column prop="progress_pct" label="进度" width="150" sortable>
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
            @click="router.push(`/projects/${projectId}/board`)"
          >
            查看
          </el-button>
          <el-popconfirm
            title="确定要删除此任务吗？"
            v-if="!row.is_deleted"
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
            v-else
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
.task-list-view {
  padding: 20px;
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
