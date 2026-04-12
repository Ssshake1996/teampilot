<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { projectsApi } from '@/api/projects'
import { tasksApi } from '@/api/tasks'
import { usersApi } from '@/api/users'
import { aiApi } from '@/api/ai'
import type { Project, User } from '@/types/models'

const router = useRouter()

const loading = ref(false)
const projects = ref<Project[]>([])
const users = ref<User[]>([])
const showArchived = ref(false)

const taskTrees = ref<Record<string, any[]>>({})
const loadingTrees = ref<Record<string, boolean>>({})
const expandedProjects = ref<Set<string>>(new Set())

// Create project
const createDialogVisible = ref(false)
const createForm = ref({ name: '', description: '', start_date: '', end_date: '' })
const creating = ref(false)

// Add subtask
const subtaskDialogVisible = ref(false)
const subtaskParent = ref<{ id: string; title: string; projectId: string } | null>(null)
const subtaskForm = ref({ title: '', description: '', assignee_id: '', estimated_hours: null as number | null, deadline: '' })
const creatingSubtask = ref(false)
const aiEstimating = ref(false)
const aiStatusMsg = ref('')
const aiRecommendations = ref<{ user_id: string; name: string; score: number; reason: string }[]>([])
const aiEstimateInfo = ref<{ estimated_hours: number; reasoning: string; confidence: string } | null>(null)

// Progress dialog (when changing status)
const progressDialogVisible = ref(false)
const progressTarget = ref<{ task: any; newStatus: string } | null>(null)
const progressForm = ref({ progress_pct: 0, note: '' })

const statusOptions = [
  { value: 'backlog', label: '待办池', pct: 0 },
  { value: 'todo', label: '待处理', pct: 0 },
  { value: 'in_progress', label: '进行中', pct: 30 },
  { value: 'in_review', label: '审核中', pct: 80 },
  { value: 'done', label: '已完成', pct: 100 },
]

// ── User name lookup ──
function userName(assigneeId: string | null): string {
  if (!assigneeId) return '未分配'
  const u = users.value.find(u => u.id === assigneeId)
  return u ? u.full_name : '未分配'
}

// ── Data Loading ──
async function loadProjects() {
  loading.value = true
  try {
    const projRes = await projectsApi.list(1, 100, showArchived.value)
    projects.value = projRes.data.items
  } catch {
    ElMessage.error('加载项目列表失败')
  }
  try {
    const userRes = await usersApi.list(1, 200)
    users.value = userRes.data.items
  } catch { /* not critical */ }
  loading.value = false
}

async function loadTaskTree(projectId: string, force = false) {
  if (taskTrees.value[projectId] && !force) return
  loadingTrees.value[projectId] = true
  try {
    const res = await projectsApi.getTaskTree(projectId)
    taskTrees.value[projectId] = flattenTree(res.data)
  } catch {
    ElMessage.error('加载任务树失败')
  } finally {
    loadingTrees.value[projectId] = false
  }
}

// Flatten nested tree into a display list with depth info
function flattenTree(roots: any[]): any[] {
  const list: any[] = []
  for (const t of roots) {
    list.push({ ...t, _depth: 0 })
    if (t.children?.length) {
      for (const c of t.children) {
        list.push({ ...c, _depth: 1, _parentId: t.id })
        if (c.children?.length) {
          for (const gc of c.children) {
            list.push({ ...gc, _depth: 2, _parentId: c.id })
          }
        }
      }
    }
  }
  return list
}

function toggleProject(projectId: string) {
  if (expandedProjects.value.has(projectId)) {
    expandedProjects.value.delete(projectId)
  } else {
    expandedProjects.value.add(projectId)
    loadTaskTree(projectId)
  }
}

function isExpanded(pid: string) { return expandedProjects.value.has(pid) }

// ── Inline Edit ──
async function handleAssigneeChange(task: any, newId: string) {
  try {
    await tasksApi.assign(task.id, newId || null)
    task.assignee_id = newId || null
    task.assignee_name = userName(newId)
    ElMessage.success('负责人已更新')
  } catch {
    ElMessage.error('更新失败')
  }
}

async function handleFieldUpdate(task: any, field: string, value: any) {
  try {
    await tasksApi.update(task.id, { [field]: value || null } as any)
    task[field] = value || null
  } catch {
    ElMessage.error('更新失败')
  }
}

// Task commands (edit/delete)
async function handleTaskCommand(cmd: string, task: any, projectId: string) {
  if (cmd === 'edit') {
    openEditDialog(task)
  } else if (cmd === 'delete') {
    try {
      await tasksApi.delete(task.id)
      task.is_deleted = true
      ElMessage.success('任务已标记删除（数据保留，不计入统计）')
      // Refresh project stats
      const projRes = await projectsApi.list(1, 100, showArchived.value)
      projects.value = projRes.data.items
    } catch {
      ElMessage.error('删除失败')
    }
  }
}

// Edit task dialog
const editDialogVisible = ref(false)
const editingTask = ref<any>(null)
const editForm = ref({ title: '', description: '', priority: 'medium', estimated_hours: null as number | null, deadline: '' })

function openEditDialog(task: any) {
  editingTask.value = task
  editForm.value = {
    title: task.title || '',
    description: task.description || '',
    priority: task.priority || 'medium',
    estimated_hours: task.estimated_hours,
    deadline: task.deadline ? task.deadline.slice(0, 10) : '',
  }
  editDialogVisible.value = true
}

async function handleEditSave() {
  if (!editingTask.value) return
  const updates: any = {}
  if (editForm.value.title !== editingTask.value.title) updates.title = editForm.value.title
  if (editForm.value.priority !== editingTask.value.priority) updates.priority = editForm.value.priority
  if (editForm.value.estimated_hours !== editingTask.value.estimated_hours) updates.estimated_hours = editForm.value.estimated_hours
  const newDeadline = editForm.value.deadline || null
  const oldDeadline = editingTask.value.deadline ? editingTask.value.deadline.slice(0, 10) : null
  if (newDeadline !== oldDeadline) updates.deadline = newDeadline
  if (editForm.value.description !== (editingTask.value.description || '')) updates.description = editForm.value.description

  if (Object.keys(updates).length === 0) {
    editDialogVisible.value = false
    return
  }
  try {
    await tasksApi.update(editingTask.value.id, updates)
    Object.assign(editingTask.value, updates)
    if (updates.deadline) editingTask.value.deadline = updates.deadline
    ElMessage.success('任务已更新')
    editDialogVisible.value = false
  } catch {
    ElMessage.error('更新失败')
  }
}

// ── Inline Edit: Status with Progress ──
function handleStatusClick(task: any, newStatus: string) {
  if (newStatus === task.status) return
  const opt = statusOptions.find(o => o.value === newStatus)
  progressTarget.value = { task, newStatus }
  progressForm.value = {
    progress_pct: opt?.pct ?? 0,
    note: '',
  }
  progressDialogVisible.value = true
}

async function confirmStatusChange() {
  if (!progressTarget.value) return
  const { task, newStatus } = progressTarget.value
  try {
    await tasksApi.updateStatus(task.id, newStatus as any)
    // Log progress
    await tasksApi.logProgress(task.id, {
      progress_pct: progressForm.value.progress_pct,
      note: progressForm.value.note || `状态变更为${statusOptions.find(o => o.value === newStatus)?.label}`,
    })
    task.status = newStatus
    task.progress_pct = progressForm.value.progress_pct
    if (newStatus === 'done') task.completed_at = new Date().toISOString()
    else task.completed_at = null
    // Recalc parent
    if (task._parentId) recalcParent(task._parentId)
    ElMessage.success('状态和进度已更新')
    progressDialogVisible.value = false
  } catch {
    ElMessage.error('更新失败')
  }
}

function recalcParent(parentId: string) {
  for (const tree of Object.values(taskTrees.value)) {
    const parent = (tree as any[]).find((t: any) => t.id === parentId && t._depth !== undefined)
    if (!parent) continue
    const children = (tree as any[]).filter((t: any) => t._parentId === parentId)
    if (children.length) {
      const done = children.filter((c: any) => c.status === 'done').length
      parent.subtask_done = done
      parent.subtask_total = children.length
      parent.progress_pct = Math.round(done / children.length * 100)
    }
    return
  }
}

// ── Add Subtask ──
function openSubtaskDialog(task: any, projectId: string) {
  subtaskParent.value = { id: task.id, title: task.title, projectId }
  subtaskForm.value = { title: '', description: '', assignee_id: '', estimated_hours: null, deadline: '' }
  aiRecommendations.value = []
  aiEstimateInfo.value = null
  subtaskDialogVisible.value = true
}

async function handleAiEstimate() {
  if (!subtaskForm.value.title.trim()) { ElMessage.warning('请先输入任务标题'); return }
  if (!subtaskParent.value) return
  aiEstimating.value = true
  aiStatusMsg.value = '正在启动 AI 分析...'
  try {
    const data = await aiApi.estimateTask(
      subtaskParent.value.projectId,
      subtaskForm.value.title,
      subtaskForm.value.description,
      (msg: string) => { aiStatusMsg.value = msg },
    )
    aiEstimateInfo.value = { estimated_hours: data.estimated_hours, reasoning: data.reasoning, confidence: data.confidence }
    aiRecommendations.value = data.recommended_assignees || []
    if (data.estimated_hours && !subtaskForm.value.estimated_hours) {
      subtaskForm.value.estimated_hours = data.estimated_hours
    }
    aiStatusMsg.value = ''
    ElMessage.success('AI 分析完成')
  } catch {
    aiStatusMsg.value = ''
    ElMessage.error('AI 分析失败，请检查 AI 配置')
  } finally {
    aiEstimating.value = false
  }
}

function applyRecommendation(rec: { user_id: string }) {
  subtaskForm.value.assignee_id = rec.user_id
  ElMessage.success('已采纳推荐人选')
}

async function handleCreateSubtask() {
  if (!subtaskForm.value.title.trim() || !subtaskParent.value) {
    ElMessage.warning('请输入子任务标题')
    return
  }
  creatingSubtask.value = true
  try {
    const payload: any = { title: subtaskForm.value.title }
    if (subtaskForm.value.description) payload.description = subtaskForm.value.description
    if (subtaskForm.value.assignee_id) payload.assignee_id = subtaskForm.value.assignee_id
    if (subtaskForm.value.estimated_hours) payload.estimated_hours = subtaskForm.value.estimated_hours
    if (subtaskForm.value.deadline) payload.deadline = subtaskForm.value.deadline
    await tasksApi.createSubtask(subtaskParent.value.id, payload)
    ElMessage.success('子任务已创建')
    subtaskDialogVisible.value = false
    await loadTaskTree(subtaskParent.value.projectId, true)
    const projRes = await projectsApi.list(1, 100, showArchived.value)
    projects.value = projRes.data.items
  } catch {
    ElMessage.error('创建子任务失败')
  } finally {
    creatingSubtask.value = false
  }
}

// ── Archive ──
async function archiveProject(pid: string) {
  try {
    await projectsApi.delete(pid)
    ElMessage.success('项目已归档')
    await loadProjects()
  } catch {
    ElMessage.error('归档失败')
  }
}

function onArchivedChange() {
  taskTrees.value = {}
  expandedProjects.value.clear()
  loadProjects()
}

// ── Create Project ──
async function handleCreate() {
  if (!createForm.value.name.trim()) { ElMessage.warning('请输入项目名称'); return }
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
  } catch { ElMessage.error('创建失败') } finally { creating.value = false }
}

// ── Helpers ──

/**
 * Progress bar color based on efficiency vs expected pace.
 * Green: on track or ahead (deviation >= 0)
 * Yellow: slightly behind (deviation -20% ~ 0)
 * Red: significantly behind (deviation < -20%)
 *
 * Expected progress = elapsed time ratio * 100
 * Deviation = actual progress - expected progress
 */
function taskProgressColor(task: any): string {
  const GREEN = '#67C23A'
  const YELLOW = '#E6A23C'
  const RED = '#F56C6C'

  const pct = task.progress_pct ?? 0
  // Done = always green
  if (task.status === 'done' || pct >= 100) return GREEN
  // Not started statuses without deadline = neutral blue
  if (!task.deadline || !task.created_at) return pct > 0 ? '#409EFF' : '#C0C4CC'
  if (task.status === 'backlog') return '#C0C4CC'

  const now = Date.now()
  const start = new Date(task.created_at).getTime()
  const end = new Date(task.deadline).getTime()
  const totalSpan = end - start
  if (totalSpan <= 0) return pct > 0 ? GREEN : RED

  const elapsed = Math.min(now - start, totalSpan)
  const timeRatio = elapsed / totalSpan  // 0~1
  const expectedPct = timeRatio * 100
  const deviation = pct - expectedPct

  if (deviation >= 0) return GREEN        // on track or ahead
  if (deviation >= -20) return YELLOW     // slightly behind (within 20%)
  return RED                              // significantly behind (>20%)
}

function projectProgress(p: Project) {
  return p.task_count ? Math.round(p.completed_count / p.task_count * 100) : 0
}
function projectProgressColor(p: Project): string {
  const pct = projectProgress(p)
  if (pct >= 100 || p.status === 'completed') return '#67C23A'
  if (!p.start_date || !p.end_date) return pct > 0 ? '#409EFF' : '#C0C4CC'
  const now = Date.now()
  const start = new Date(p.start_date).getTime()
  const end = new Date(p.end_date).getTime()
  const span = end - start
  if (span <= 0) return '#409EFF'
  const elapsed = Math.min(now - start, span)
  const expectedPct = (elapsed / span) * 100
  const deviation = pct - expectedPct
  if (deviation >= 0) return '#67C23A'
  if (deviation >= -20) return '#E6A23C'
  return '#F56C6C'
}
function statusType(s: string) { return ({ planning: 'info', active: '', paused: 'warning', completed: 'success', archived: 'danger' } as any)[s] || 'info' }
function statusLabel(s: string) { return ({ planning: '规划中', active: '进行中', paused: '已暂停', completed: '已完成', archived: '已归档' } as any)[s] || s }
function taskStatusType(s: string) { return ({ backlog: 'info', todo: '', in_progress: 'warning', in_review: '', done: 'success' } as any)[s] || 'info' }
function taskStatusLabel(s: string) { return ({ backlog: '待办池', todo: '待处理', in_progress: '进行中', in_review: '审核中', done: '已完成' } as any)[s] || s }
function formatDate(d: string | null) { return d ? d.slice(0, 10) : '-' }
function goToBoard(pid: string) { router.push(`/projects/${pid}/board`) }
function depthIndent(depth: number) { return depth === 1 ? '└ ' : depth === 2 ? '└ ' : '' }

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
      <div class="summary-item"><span class="summary-value">{{ summaryStats.total }}</span><span class="summary-label">项目总数</span></div>
      <div class="summary-item"><span class="summary-value active">{{ summaryStats.active }}</span><span class="summary-label">进行中</span></div>
      <div class="summary-item"><span class="summary-value">{{ summaryStats.totalTasks }}</span><span class="summary-label">总任务数</span></div>
      <div class="summary-item"><span class="summary-value done">{{ summaryStats.doneTasks }}</span><span class="summary-label">已完成</span></div>
      <div class="summary-item"><span class="summary-value" :class="{ warning: summaryStats.overallRate < 50 }">{{ summaryStats.overallRate }}%</span><span class="summary-label">整体完成率</span></div>
      <el-switch v-model="showArchived" active-text="含归档" inactive-text="" style="margin-left:auto" @change="onArchivedChange" />
      <el-button type="primary" @click="createDialogVisible = true">新建项目</el-button>
    </div>

    <!-- Project Tree -->
    <div class="project-tree">
      <div v-for="project in projects" :key="project.id" class="project-block">
        <div class="project-row" @click="toggleProject(project.id)">
          <div class="row-expand">
            <svg viewBox="0 0 1024 1024" width="14" height="14" :class="{ rotated: isExpanded(project.id) }" class="expand-icon">
              <path d="M384 256l320 256-320 256z" fill="currentColor"/>
            </svg>
          </div>
          <div class="row-name project-name">
            <strong>{{ project.name }}</strong>
            <el-tag :type="(statusType(project.status) as any)" size="small" style="margin-left:8px">{{ statusLabel(project.status) }}</el-tag>
          </div>
          <div class="row-cell">{{ project.member_count }} 人</div>
          <div class="row-cell center">{{ project.task_count }} 任务</div>
          <div class="row-progress">
            <el-progress :percentage="projectProgress(project)" :stroke-width="8" :color="projectProgressColor(project)" style="width:120px" />
            <span class="progress-text">{{ project.completed_count }}/{{ project.task_count }}</span>
          </div>
          <div class="row-cell">{{ formatDate(project.start_date) }} ~ {{ formatDate(project.end_date) }}</div>
          <div class="row-cell center" @click.stop>
            <el-button type="primary" link size="small" @click="goToBoard(project.id)">看板</el-button>
            <el-popconfirm v-if="project.status !== 'archived'" title="归档后不计入仪表盘统计，确认？" @confirm="archiveProject(project.id)">
              <template #reference><el-button type="info" link size="small">归档</el-button></template>
            </el-popconfirm>
            <el-tag v-else type="info" size="small" effect="plain">已归档</el-tag>
          </div>
        </div>

        <!-- Task Tree -->
        <div v-if="isExpanded(project.id)" class="task-tree-container">
          <div v-if="loadingTrees[project.id]" class="tree-loading">加载中...</div>
          <template v-else-if="taskTrees[project.id]?.length">
            <div class="task-header-row">
              <div class="row-expand"></div>
              <div class="row-name">任务名称</div>
              <div class="row-cell">负责人</div>
              <div class="row-cell center">工时</div>
              <div class="row-progress">进度</div>
              <div class="row-cell">截止日期</div>
              <div class="row-cell center">状态 / 操作</div>
            </div>

            <div v-for="task in taskTrees[project.id]" :key="task.id" class="task-row" :class="{ 'depth-0': task._depth === 0, 'depth-1': task._depth === 1, 'depth-2': task._depth === 2, 'task-deleted': task.is_deleted }">
              <div class="row-expand">
                <span v-if="task._depth === 0 && task.subtask_total > 0" class="subtask-badge">{{ task.subtask_done }}/{{ task.subtask_total }}</span>
              </div>
              <div class="row-name" :style="{ paddingLeft: (8 + task._depth * 20) + 'px' }">
                <span v-if="task._depth > 0" class="subtask-indent">└</span>
                <span class="task-title-text" @dblclick.stop="openEditDialog(task)" title="双击编辑">{{ task.title }}</span>
                <el-tag v-if="task.priority === 'urgent'" type="danger" size="small" style="margin-left:4px">紧急</el-tag>
                <el-tag v-else-if="task.priority === 'high'" type="danger" size="small" effect="plain" style="margin-left:4px">高</el-tag>
              </div>
              <div class="row-cell" @click.stop>
                <el-select
                  :model-value="task.assignee_id || ''"
                  size="small" placeholder="未分配" clearable filterable
                  class="inline-select"
                  @change="(v: string) => handleAssigneeChange(task, v)"
                >
                  <el-option v-for="u in users" :key="u.id" :label="u.full_name" :value="u.id" />
                </el-select>
              </div>
              <div class="row-cell center" @click.stop>
                <el-input-number
                  :model-value="task.estimated_hours"
                  size="small" :min="0" :max="999" :precision="1" :controls="false"
                  class="inline-hours"
                  placeholder="-"
                  @change="(v: number) => handleFieldUpdate(task, 'estimated_hours', v)"
                />
              </div>
              <div class="row-progress">
                <el-progress
                  :percentage="task.progress_pct ?? (task.status === 'done' ? 100 : 0)"
                  :stroke-width="6"
                  :color="taskProgressColor(task)"
                  style="width:100px"
                />
                <span class="progress-num">{{ task.progress_pct ?? (task.status === 'done' ? 100 : 0) }}%</span>
              </div>
              <div class="row-cell" @click.stop>
                <el-date-picker
                  :model-value="task.deadline ? task.deadline.slice(0, 10) : ''"
                  type="date" size="small" value-format="YYYY-MM-DD"
                  placeholder="-" class="inline-date"
                  :class="{ overdue: task.is_overdue }"
                  @update:model-value="(v: string) => handleFieldUpdate(task, 'deadline', v)"
                />
              </div>
              <div class="row-cell center" @click.stop>
                <el-select
                  :model-value="task.status" size="small"
                  class="inline-select status-select"
                  @change="(v: string) => handleStatusClick(task, v)"
                >
                  <el-option v-for="opt in statusOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                </el-select>
                <el-button type="primary" link size="small" class="add-sub-btn" title="添加子任务" @click="openSubtaskDialog(task, project.id)">+</el-button>
                <el-dropdown trigger="click" size="small" @command="(cmd: string) => handleTaskCommand(cmd, task, project.id)">
                  <el-button type="info" link size="small" class="more-btn" title="更多">...</el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="edit">编辑任务</el-dropdown-item>
                      <el-dropdown-item command="delete" divided style="color:#F56C6C">删除任务</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </div>
          </template>
          <div v-else class="tree-empty">暂无任务，前往看板创建</div>
        </div>
      </div>
    </div>

    <!-- Create Project Dialog -->
    <el-dialog v-model="createDialogVisible" title="新建项目" width="500px">
      <el-form label-width="80px">
        <el-form-item label="项目名称"><el-input v-model="createForm.name" placeholder="请输入项目名称" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="createForm.description" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="开始日期"><el-date-picker v-model="createForm.start_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
        <el-form-item label="截止日期"><el-date-picker v-model="createForm.end_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- Add Subtask Dialog -->
    <el-dialog v-model="subtaskDialogVisible" :title="'添加子任务 — ' + (subtaskParent?.title || '')" width="640px">
      <el-form label-width="80px">
        <el-form-item label="任务标题">
          <el-input v-model="subtaskForm.title" placeholder="请输入子任务标题" />
        </el-form-item>
        <el-form-item label="任务描述">
          <el-input v-model="subtaskForm.description" type="textarea" :rows="2" placeholder="简要描述任务内容(可选,有助于 AI 更准确推荐)" />
        </el-form-item>
        <el-form-item>
          <div class="ai-action-row">
            <el-button type="warning" :loading="aiEstimating" @click="handleAiEstimate" :disabled="!subtaskForm.title.trim()">
              AI 推荐人选 + 预估工时
            </el-button>
            <span v-if="aiStatusMsg" class="ai-status-text">{{ aiStatusMsg }}</span>
          </div>
        </el-form-item>

        <!-- AI Recommendations -->
        <div v-if="aiEstimateInfo" class="ai-result-box">
          <div class="ai-result-header">AI 分析结果</div>
          <div class="ai-estimate-row">
            <span>预估工时: <strong>{{ aiEstimateInfo.estimated_hours }}h</strong></span>
            <el-tag :type="aiEstimateInfo.confidence === 'high' ? 'success' : aiEstimateInfo.confidence === 'medium' ? 'warning' : 'info'" size="small">
              {{ aiEstimateInfo.confidence === 'high' ? '高置信' : aiEstimateInfo.confidence === 'medium' ? '中置信' : '低置信' }}
            </el-tag>
          </div>
          <div class="ai-reasoning">{{ aiEstimateInfo.reasoning }}</div>
          <div v-if="aiRecommendations.length" class="ai-recommend-list">
            <div class="ai-recommend-title">推荐人选:</div>
            <div v-for="(rec, idx) in aiRecommendations" :key="idx" class="ai-recommend-item">
              <div class="rec-info">
                <span class="rec-rank">#{{ idx + 1 }}</span>
                <span class="rec-name">{{ rec.name }}</span>
                <el-tag size="small" type="warning">{{ rec.score }}分</el-tag>
              </div>
              <div class="rec-reason">{{ rec.reason }}</div>
              <el-button type="primary" size="small" @click="applyRecommendation(rec)">采纳</el-button>
            </div>
          </div>
        </div>

        <el-form-item label="负责人">
          <el-select v-model="subtaskForm.assignee_id" placeholder="选择负责人" clearable filterable style="width:100%">
            <el-option v-for="u in users" :key="u.id" :label="u.full_name" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="预估工时">
          <el-input-number v-model="subtaskForm.estimated_hours" :min="0" :max="999" :precision="1" style="width:100%" />
        </el-form-item>
        <el-form-item label="截止日期">
          <el-date-picker v-model="subtaskForm.deadline" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="subtaskDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creatingSubtask" @click="handleCreateSubtask">创建</el-button>
      </template>
    </el-dialog>

    <!-- Progress + Status Change Dialog -->
    <el-dialog v-model="progressDialogVisible" title="更新状态和进度" width="440px">
      <div v-if="progressTarget" style="margin-bottom:16px;color:#606266;font-size:13px">
        <strong>{{ progressTarget.task.title }}</strong> →
        <el-tag :type="(taskStatusType(progressTarget.newStatus) as any)" size="small">{{ taskStatusLabel(progressTarget.newStatus) }}</el-tag>
      </div>
      <el-form label-width="80px">
        <el-form-item label="进度 (%)">
          <el-slider v-model="progressForm.progress_pct" :min="0" :max="100" :step="5" show-stops style="padding:0 8px" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="progressForm.note" type="textarea" :rows="2" placeholder="说明本次进展" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="progressDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmStatusChange">确认</el-button>
      </template>
    </el-dialog>

    <!-- Edit Task Dialog -->
    <el-dialog v-model="editDialogVisible" title="编辑任务" width="520px">
      <el-form v-if="editingTask" label-width="80px">
        <el-form-item label="任务标题">
          <el-input v-model="editForm.title" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="editForm.priority" style="width:100%">
            <el-option label="低" value="low" />
            <el-option label="中" value="medium" />
            <el-option label="高" value="high" />
            <el-option label="紧急" value="urgent" />
          </el-select>
        </el-form-item>
        <el-form-item label="预估工时">
          <el-input-number v-model="editForm.estimated_hours" :min="0" :max="999" :precision="1" style="width:100%" />
        </el-form-item>
        <el-form-item label="截止日期">
          <el-date-picker v-model="editForm.deadline" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleEditSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.project-list-view { padding: 0; }

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

.project-tree { display: flex; flex-direction: column; gap: 2px; }
.project-block { background: #fff; border-radius: 6px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }

.project-row, .task-row, .task-header-row {
  display: grid;
  grid-template-columns: 40px minmax(180px, 1fr) 100px 56px 140px 120px 160px;
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
.depth-0 { background: #fff; }
.depth-1 { background: #fafbfc; }
.depth-2 { background: #f5f7fa; }

.row-expand { display: flex; justify-content: center; align-items: center; color: #909399; }
.expand-icon { transition: transform 0.2s; }
.expand-icon.rotated { transform: rotate(90deg); }

.subtask-badge {
  font-size: 11px; color: #409EFF; background: #ecf5ff;
  padding: 1px 6px; border-radius: 8px; white-space: nowrap;
}

.row-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.subtask-indent { color: #c0c4cc; margin-right: 4px; }
.row-cell { font-size: 12px; color: #606266; }
.row-cell.center { text-align: center; }
.row-progress { display: flex; align-items: center; gap: 4px; }
.progress-text { font-size: 11px; color: #909399; white-space: nowrap; }
.progress-num { font-size: 11px; color: #909399; min-width: 32px; }
.overdue { color: #F56C6C; font-weight: 600; }

.inline-select { width: 100%; }
.inline-select :deep(.el-input__wrapper) { box-shadow: none !important; background: transparent; padding: 0 4px; }
.inline-select :deep(.el-input__wrapper:hover) { box-shadow: 0 0 0 1px #dcdfe6 inset !important; }
.inline-select :deep(.el-input__inner) { font-size: 12px; }
.status-select { width: 80px; }
.add-sub-btn { font-size: 16px; font-weight: 700; padding: 2px 6px; margin-left: 2px; }

.task-tree-container { border-top: 1px solid #ebeef5; }
.tree-loading, .tree-empty { padding: 16px 24px; text-align: center; color: #909399; font-size: 13px; }

.ai-result-box {
  background: #fdf6ec; border: 1px solid #faecd8; border-radius: 6px;
  padding: 12px 16px; margin-bottom: 16px;
}
.ai-result-header { font-weight: 600; font-size: 14px; color: #e6a23c; margin-bottom: 8px; }
.ai-estimate-row { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; font-size: 13px; }
.ai-reasoning { font-size: 12px; color: #909399; margin-bottom: 10px; }
.ai-recommend-title { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 6px; }
.ai-recommend-item {
  display: flex; align-items: center; gap: 8px; padding: 6px 0;
  border-bottom: 1px solid #faecd8; flex-wrap: wrap;
}
.ai-recommend-item:last-child { border-bottom: none; }
.rec-info { display: flex; align-items: center; gap: 6px; flex: 1; }
.rec-rank { font-weight: 700; color: #e6a23c; font-size: 13px; }
.rec-name { font-weight: 500; font-size: 13px; }
.rec-reason { font-size: 12px; color: #909399; width: 100%; margin: 2px 0; }

.ai-action-row { display: flex; align-items: center; gap: 12px; }
.ai-status-text { font-size: 13px; color: #e6a23c; animation: pulse 1.5s infinite; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.5; } }

/* Task deleted strikethrough */
.task-deleted { opacity: 0.5; }
.task-deleted .task-title-text { text-decoration: line-through; color: #c0c4cc; }
.task-deleted .inline-select :deep(.el-input__wrapper),
.task-deleted .inline-hours :deep(.el-input__wrapper),
.task-deleted .inline-date :deep(.el-input__wrapper) { pointer-events: none; }

/* Inline hours input */
.inline-hours { width: 56px; }
.inline-hours :deep(.el-input__wrapper) { box-shadow: none !important; background: transparent; padding: 0 2px; }
.inline-hours :deep(.el-input__wrapper:hover) { box-shadow: 0 0 0 1px #dcdfe6 inset !important; }
.inline-hours :deep(.el-input__inner) { font-size: 12px; text-align: center; }

/* Inline date picker */
.inline-date { width: 110px; }
.inline-date :deep(.el-input__wrapper) { box-shadow: none !important; background: transparent; padding: 0 2px; }
.inline-date :deep(.el-input__wrapper:hover) { box-shadow: 0 0 0 1px #dcdfe6 inset !important; }
.inline-date :deep(.el-input__inner) { font-size: 12px; }
.inline-date.overdue :deep(.el-input__inner) { color: #F56C6C; font-weight: 600; }

/* Title clickable */
.task-title-text { cursor: default; }
.task-title-text:hover { color: #409EFF; cursor: pointer; }

/* More button */
.more-btn { font-size: 14px; font-weight: 700; padding: 2px 4px; margin-left: 0; }
</style>
