<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { projectsApi } from '@/api/projects'
import type { Project } from '@/types/models'

const router = useRouter()

// ── State ──
const loading = ref(false)
const projects = ref<Project[]>([])

// Expanded project task trees: projectId -> task[]
const taskTrees = ref<Record<string, any[]>>({})
const loadingTrees = ref<Record<string, boolean>>({})
const expandedProjects = ref<Set<string>>(new Set())

// Create dialog
const createDialogVisible = ref(false)
const createForm = ref({ name: '', description: '', start_date: '', end_date: '' })
const creating = ref(false)

// ── Data Loading ──
async function loadProjects() {
  loading.value = true
  try {
    const res = await projectsApi.list(1, 100)
    projects.value = res.data.items
  } finally {
    loading.value = false
  }
}

async function loadTaskTree(projectId: string) {
  if (taskTrees.value[projectId]) return
  loadingTrees.value[projectId] = true
  try {
    const res = await projectsApi.getTaskTree(projectId)
    taskTrees.value[projectId] = res.data
  } catch {
    ElMessage.error('加载任务树失败')
  } finally {
    loadingTrees.value[projectId] = false
  }
}

function toggleProject(projectId: string) {
  if (expandedProjects.value.has(projectId)) {
    expandedProjects.value.delete(projectId)
  } else {
    expandedProjects.value.add(projectId)
    loadTaskTree(projectId)
  }
}

function isProjectExpanded(projectId: string): boolean {
  return expandedProjects.value.has(projectId)
}

// ── Computed ──
function projectProgress(p: Project): number {
  if (!p.task_count || p.task_count === 0) return 0
  return Math.round((p.completed_count / p.task_count) * 100)
}

function statusType(status: string): string {
  const map: Record<string, string> = {
    planning: 'info', active: '', paused: 'warning', completed: 'success', archived: 'danger',
  }
  return map[status] || 'info'
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    planning: '规划中', active: '进行中', paused: '已暂停', completed: '已完成', archived: '已归档',
  }
  return map[status] || status
}

function taskStatusType(s: string): string {
  const map: Record<string, string> = {
    backlog: 'info', todo: '', in_progress: 'warning', in_review: '', done: 'success',
  }
  return map[s] || 'info'
}

function taskStatusLabel(s: string): string {
  const map: Record<string, string> = {
    backlog: '待办池', todo: '待处理', in_progress: '进行中', in_review: '审核中', done: '已完成',
  }
  return map[s] || s
}

function formatDate(d: string | null): string {
  if (!d) return '-'
  return d.slice(0, 10)
}

function goToBoard(projectId: string) {
  router.push(`/projects/${projectId}/board`)
}

// ── Create Project ──
async function handleCreate() {
  if (!createForm.value.name.trim()) {
    ElMessage.warning('请输入项目名称')
    return
  }
  creating.value = true
  try {
    await projectsApi.create({
      name: createForm.value.name,
      description: createForm.value.description || undefined,
      start_date: createForm.value.start_date || undefined,
      end_date: createForm.value.end_date || undefined,
    })
    ElMessage.success('项目已创建')
    createDialogVisible.value = false
    createForm.value = { name: '', description: '', start_date: '', end_date: '' }
    await loadProjects()
  } catch {
    ElMessage.error('创建失败')
  } finally {
    creating.value = false
  }
}

// ── Summary Stats ──
const summaryStats = computed(() => {
  const total = projects.value.length
  const active = projects.value.filter(p => p.status === 'active').length
  const totalTasks = projects.value.reduce((s, p) => s + (p.task_count || 0), 0)
  const doneTasks = projects.value.reduce((s, p) => s + (p.completed_count || 0), 0)
  const overallRate = totalTasks > 0 ? Math.round(doneTasks / totalTasks * 100) : 0
  return { total, active, totalTasks, doneTasks, overallRate }
})

onMounted(loadProjects)
</script>

<template>
  <div v-loading="loading" class="project-list-view">
    <!-- Summary Bar -->
    <div class="summary-bar">
      <div class="summary-item">
        <span class="summary-value">{{ summaryStats.total }}</span>
        <span class="summary-label">项目总数</span>
      </div>
      <div class="summary-item">
        <span class="summary-value active">{{ summaryStats.active }}</span>
        <span class="summary-label">进行中</span>
      </div>
      <div class="summary-item">
        <span class="summary-value">{{ summaryStats.totalTasks }}</span>
        <span class="summary-label">总任务数</span>
      </div>
      <div class="summary-item">
        <span class="summary-value done">{{ summaryStats.doneTasks }}</span>
        <span class="summary-label">已完成</span>
      </div>
      <div class="summary-item">
        <span class="summary-value" :class="{ warning: summaryStats.overallRate < 50 }">
          {{ summaryStats.overallRate }}%
        </span>
        <span class="summary-label">整体完成率</span>
      </div>
      <el-button type="primary" class="create-btn" @click="createDialogVisible = true">
        新建项目
      </el-button>
    </div>

    <!-- Project Tree Table -->
    <div class="project-tree">
      <div v-for="project in projects" :key="project.id" class="project-block">
        <!-- Project Row -->
        <div class="project-row" @click="toggleProject(project.id)">
          <div class="row-expand">
            <svg
              viewBox="0 0 1024 1024" width="14" height="14"
              :class="{ rotated: isProjectExpanded(project.id) }"
              class="expand-icon"
            >
              <path d="M384 256l320 256-320 256z" fill="currentColor"/>
            </svg>
          </div>
          <div class="row-name project-name">
            <strong>{{ project.name }}</strong>
            <el-tag :type="(statusType(project.status) as any)" size="small" style="margin-left:8px">
              {{ statusLabel(project.status) }}
            </el-tag>
          </div>
          <div class="row-assignee">{{ project.member_count }} 人</div>
          <div class="row-hours">{{ project.task_count }} 任务</div>
          <div class="row-progress">
            <el-progress
              :percentage="projectProgress(project)"
              :stroke-width="8"
              :color="projectProgress(project) >= 80 ? '#67C23A' : projectProgress(project) >= 40 ? '#E6A23C' : '#409EFF'"
              style="width:120px"
            />
            <span class="progress-text">{{ project.completed_count }}/{{ project.task_count }}</span>
          </div>
          <div class="row-deadline">{{ formatDate(project.start_date) }} ~ {{ formatDate(project.end_date) }}</div>
          <div class="row-actions" @click.stop>
            <el-button type="primary" link size="small" @click="goToBoard(project.id)">看板</el-button>
          </div>
        </div>

        <!-- Expanded Task Tree -->
        <div v-if="isProjectExpanded(project.id)" class="task-tree-container">
          <div v-if="loadingTrees[project.id]" class="tree-loading">
            加载中...
          </div>
          <template v-else-if="taskTrees[project.id]?.length">
            <!-- Column Headers -->
            <div class="task-header-row">
              <div class="row-expand"></div>
              <div class="row-name">任务名称</div>
              <div class="row-assignee">负责人</div>
              <div class="row-hours">工时</div>
              <div class="row-progress">进度</div>
              <div class="row-deadline">截止日期</div>
              <div class="row-actions">状态</div>
            </div>
            <!-- Parent Tasks -->
            <div v-for="task in taskTrees[project.id]" :key="task.id">
              <div class="task-row parent-task">
                <div class="row-expand">
                  <span v-if="task.children?.length" class="subtask-badge">{{ task.subtask_done }}/{{ task.subtask_total }}</span>
                </div>
                <div class="row-name task-name">
                  {{ task.title }}
                  <el-tag v-if="task.priority === 'urgent'" type="danger" size="small" style="margin-left:4px">紧急</el-tag>
                  <el-tag v-else-if="task.priority === 'high'" type="danger" size="small" effect="plain" style="margin-left:4px">高</el-tag>
                </div>
                <div class="row-assignee">
                  <span :class="{ 'no-assignee': !task.assignee_name }">
                    {{ task.assignee_name || '未分配' }}
                  </span>
                </div>
                <div class="row-hours">{{ task.estimated_hours ? task.estimated_hours + 'h' : '-' }}</div>
                <div class="row-progress">
                  <el-progress
                    :percentage="task.progress_pct"
                    :stroke-width="6"
                    :color="task.progress_pct === 100 ? '#67C23A' : '#409EFF'"
                    style="width:100px"
                  />
                </div>
                <div class="row-deadline" :class="{ overdue: task.is_overdue }">
                  {{ formatDate(task.deadline) }}
                </div>
                <div class="row-actions">
                  <el-tag :type="(taskStatusType(task.status) as any)" size="small">
                    {{ taskStatusLabel(task.status) }}
                  </el-tag>
                </div>
              </div>
              <!-- Subtasks -->
              <div v-for="sub in task.children" :key="sub.id" class="task-row subtask-row">
                <div class="row-expand"></div>
                <div class="row-name subtask-name">
                  <span class="subtask-indent">└</span> {{ sub.title }}
                </div>
                <div class="row-assignee">
                  <span :class="{ 'no-assignee': !sub.assignee_name }">
                    {{ sub.assignee_name || '未分配' }}
                  </span>
                </div>
                <div class="row-hours">{{ sub.estimated_hours ? sub.estimated_hours + 'h' : '-' }}</div>
                <div class="row-progress">
                  <el-progress
                    :percentage="sub.status === 'done' ? 100 : 0"
                    :stroke-width="6"
                    :color="sub.status === 'done' ? '#67C23A' : '#C0C4CC'"
                    style="width:100px"
                  />
                </div>
                <div class="row-deadline" :class="{ overdue: sub.is_overdue }">
                  {{ formatDate(sub.deadline) }}
                </div>
                <div class="row-actions">
                  <el-tag :type="(taskStatusType(sub.status) as any)" size="small">
                    {{ taskStatusLabel(sub.status) }}
                  </el-tag>
                </div>
              </div>
            </div>
          </template>
          <div v-else class="tree-empty">暂无任务，前往看板创建</div>
        </div>
      </div>
    </div>

    <!-- Create Dialog -->
    <el-dialog v-model="createDialogVisible" title="新建项目" width="500px">
      <el-form label-width="80px">
        <el-form-item label="项目名称">
          <el-input v-model="createForm.name" placeholder="请输入项目名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="3" placeholder="项目描述" />
        </el-form-item>
        <el-form-item label="开始日期">
          <el-date-picker v-model="createForm.start_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="截止日期">
          <el-date-picker v-model="createForm.end_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.project-list-view { padding: 0; }

/* Summary Bar */
.summary-bar {
  display: flex; align-items: center; gap: 32px;
  padding: 16px 20px; background: #fff; border-radius: 8px;
  margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.summary-item { display: flex; flex-direction: column; align-items: center; }
.summary-value { font-size: 24px; font-weight: 700; color: #303133; }
.summary-value.active { color: #409EFF; }
.summary-value.done { color: #67C23A; }
.summary-value.warning { color: #E6A23C; }
.summary-label { font-size: 12px; color: #909399; margin-top: 2px; }
.create-btn { margin-left: auto; }

/* Project Tree */
.project-tree { display: flex; flex-direction: column; gap: 2px; }
.project-block {
  background: #fff; border-radius: 6px; overflow: hidden;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

/* Row Layout */
.project-row, .task-row, .task-header-row {
  display: grid;
  grid-template-columns: 48px 1fr 80px 60px 150px 130px 72px;
  align-items: center; padding: 0 12px; min-height: 44px; gap: 4px;
}
.project-row {
  background: #fafbfc; border-left: 4px solid #409EFF;
  cursor: pointer; min-height: 52px; transition: background 0.15s;
}
.project-row:hover { background: #f0f5ff; }
.project-name strong { font-size: 14px; }
.task-header-row {
  background: #f5f7fa; font-size: 12px; color: #909399;
  font-weight: 600; min-height: 32px; border-bottom: 1px solid #ebeef5;
}
.task-row { border-bottom: 1px solid #f2f3f5; font-size: 13px; min-height: 40px; }
.task-row:last-child { border-bottom: none; }
.parent-task { background: #fff; }
.subtask-row { background: #fafbfc; }

.row-expand { display: flex; justify-content: center; align-items: center; color: #909399; }
.expand-icon { transition: transform 0.2s; }
.expand-icon.rotated { transform: rotate(90deg); }

.subtask-badge {
  font-size: 11px; color: #409EFF; background: #ecf5ff;
  padding: 1px 6px; border-radius: 8px; white-space: nowrap;
}
.row-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.task-name { padding-left: 8px; }
.subtask-name { padding-left: 24px; color: #606266; }
.subtask-indent { color: #c0c4cc; margin-right: 4px; }
.row-assignee { font-size: 12px; color: #606266; }
.no-assignee { color: #c0c4cc; }
.row-hours { font-size: 12px; color: #606266; text-align: center; }
.row-progress { display: flex; align-items: center; gap: 6px; }
.progress-text { font-size: 11px; color: #909399; white-space: nowrap; }
.row-deadline { font-size: 12px; color: #909399; }
.row-deadline.overdue { color: #F56C6C; font-weight: 600; }
.row-actions { text-align: center; }

.task-tree-container { border-top: 1px solid #ebeef5; }
.tree-loading, .tree-empty {
  padding: 16px 24px; text-align: center; color: #909399; font-size: 13px;
}
</style>
