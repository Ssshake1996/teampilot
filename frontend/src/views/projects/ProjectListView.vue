<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { projectsApi } from '@/api/projects'
import { tasksApi } from '@/api/tasks'
import { usersApi } from '@/api/users'
import { aiApi } from '@/api/ai'
import { useAuthStore } from '@/stores/auth'
import type { Project, User, TaskProgress } from '@/types/models'

const router = useRouter()
const auth = useAuthStore()

const loading = ref(false)
const projects = ref<Project[]>([])
const users = ref<User[]>([])
const showArchived = ref(false)

const taskTrees = ref<Record<string, any[]>>({})
const loadingTrees = ref<Record<string, boolean>>({})
const expandedProjects = ref<Set<string>>(new Set())

// Permission: only admin can edit tasks
const canEdit = computed(() => auth.user?.role === 'admin')

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
const aiRecommendations = ref<any[]>([])
const aiEstimateInfo = ref<any>(null)

// Progress feedback dialog
const feedbackDialogVisible = ref(false)
const feedbackTask = ref<any>(null)
const feedbackHistory = ref<TaskProgress[]>([])
const feedbackLoading = ref(false)
const feedbackForm = ref({ progress_pct: 0, note: '' })
const feedbackSubmitting = ref(false)

// Status change with progress
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

function userName(id: string | null): string {
  if (!id) return '未分配'
  return users.value.find(u => u.id === id)?.full_name || '未分配'
}

// ── Data Loading ──
async function loadProjects() {
  loading.value = true
  try {
    const projRes = await projectsApi.list(1, 100, showArchived.value)
    projects.value = projRes.data.items
  } catch { ElMessage.error('加载项目列表失败') }
  try {
    const userRes = await usersApi.list(1, 200)
    users.value = userRes.data.items
  } catch {}
  loading.value = false
}

async function loadTaskTree(pid: string, force = false) {
  if (taskTrees.value[pid] && !force) return
  loadingTrees.value[pid] = true
  try {
    const res = await projectsApi.getTaskTree(pid)
    taskTrees.value[pid] = flattenTree(res.data)
  } catch { ElMessage.error('加载任务树失败') }
  finally { loadingTrees.value[pid] = false }
}

function flattenTree(roots: any[]): any[] {
  const list: any[] = []
  for (const t of roots) {
    list.push({ ...t, _depth: 0 })
    if (t.children?.length) {
      for (const c of t.children) {
        list.push({ ...c, _depth: 1, _parentId: t.id })
        if (c.children?.length) {
          for (const gc of c.children) list.push({ ...gc, _depth: 2, _parentId: c.id })
        }
      }
    }
  }
  return list
}

function toggleProject(pid: string) {
  if (expandedProjects.value.has(pid)) { expandedProjects.value.delete(pid) }
  else { expandedProjects.value.add(pid); loadTaskTree(pid) }
}
function isExpanded(pid: string) { return expandedProjects.value.has(pid) }

// ── Inline Edit (admin only) ──
async function handleAssigneeChange(task: any, newId: string) {
  try {
    await tasksApi.assign(task.id, newId || null)
    task.assignee_id = newId || null
    task.assignee_name = userName(newId)
  } catch { ElMessage.error('更新失败') }
}

async function handleFieldUpdate(task: any, field: string, value: any) {
  try {
    await tasksApi.update(task.id, { [field]: value || null } as any)
    task[field] = value || null
  } catch { ElMessage.error('更新失败') }
}

function handleStatusClick(task: any, newStatus: string) {
  if (newStatus === task.status) return
  const opt = statusOptions.find(o => o.value === newStatus)
  progressTarget.value = { task, newStatus }
  progressForm.value = { progress_pct: opt?.pct ?? 0, note: '' }
  progressDialogVisible.value = true
}

async function confirmStatusChange() {
  if (!progressTarget.value) return
  const { task, newStatus } = progressTarget.value
  try {
    await tasksApi.updateStatus(task.id, newStatus as any)
    await tasksApi.logProgress(task.id, {
      progress_pct: progressForm.value.progress_pct,
      note: progressForm.value.note || statusOptions.find(o => o.value === newStatus)?.label || '',
    })
    task.status = newStatus
    task.progress_pct = progressForm.value.progress_pct
    task.completed_at = newStatus === 'done' ? new Date().toISOString() : null
    if (task._parentId) recalcParent(task._parentId)
    progressDialogVisible.value = false
  } catch { ElMessage.error('更新失败') }
}

function recalcParent(parentId: string) {
  for (const tree of Object.values(taskTrees.value)) {
    const parent = (tree as any[]).find(t => t.id === parentId)
    if (!parent) continue
    const children = (tree as any[]).filter(t => t._parentId === parentId && !t.is_deleted)
    if (children.length) {
      parent.subtask_done = children.filter(c => c.status === 'done').length
      parent.subtask_total = children.length
      parent.progress_pct = Math.round(parent.subtask_done / children.length * 100)
    }
    return
  }
}

// ── Task delete (admin only, soft) ──
async function handleDelete(task: any) {
  try {
    await tasksApi.delete(task.id)
    task.is_deleted = true
    ElMessage.success('已标记删除')
    const projRes = await projectsApi.list(1, 100, showArchived.value)
    projects.value = projRes.data.items
  } catch { ElMessage.error('删除失败') }
}

// ── Progress Feedback (everyone) ──
async function openFeedback(task: any) {
  feedbackTask.value = task
  feedbackForm.value = { progress_pct: task.progress_pct || 0, note: '' }
  feedbackDialogVisible.value = true
  feedbackLoading.value = true
  try {
    const res = await tasksApi.getProgress(task.id)
    feedbackHistory.value = res.data
  } catch { feedbackHistory.value = [] }
  finally { feedbackLoading.value = false }
}

async function submitFeedback() {
  if (!feedbackTask.value) return
  if (!feedbackForm.value.note.trim()) { ElMessage.warning('请填写进展说明'); return }
  feedbackSubmitting.value = true
  try {
    await tasksApi.logProgress(feedbackTask.value.id, {
      progress_pct: feedbackForm.value.progress_pct,
      note: feedbackForm.value.note,
    })
    feedbackTask.value.progress_pct = feedbackForm.value.progress_pct
    feedbackTask.value.latest_note = feedbackForm.value.note
    ElMessage.success('进展已提交')
    feedbackForm.value.note = ''
    // Reload history
    const res = await tasksApi.getProgress(feedbackTask.value.id)
    feedbackHistory.value = res.data
  } catch { ElMessage.error('提交失败') }
  finally { feedbackSubmitting.value = false }
}

// ── Add Subtask (admin only) ──
function openSubtaskDialog(task: any, projectId: string) {
  subtaskParent.value = { id: task.id, title: task.title, projectId }
  subtaskForm.value = { title: '', description: '', assignee_id: '', estimated_hours: null, deadline: '' }
  aiRecommendations.value = []; aiEstimateInfo.value = null
  subtaskDialogVisible.value = true
}

async function handleCreateSubtask() {
  if (!subtaskForm.value.title.trim() || !subtaskParent.value) { ElMessage.warning('请输入子任务标题'); return }
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
  } catch { ElMessage.error('创建失败') }
  finally { creatingSubtask.value = false }
}

async function handleAiEstimate() {
  if (!subtaskForm.value.title.trim() || !subtaskParent.value) return
  aiEstimating.value = true; aiStatusMsg.value = '正在启动 AI...'
  try {
    const data = await aiApi.estimateTask(subtaskParent.value.projectId, subtaskForm.value.title, subtaskForm.value.description, (msg: string) => { aiStatusMsg.value = msg })
    aiEstimateInfo.value = data
    aiRecommendations.value = data.recommended_assignees || []
    if (data.estimated_hours && !subtaskForm.value.estimated_hours) subtaskForm.value.estimated_hours = data.estimated_hours
    aiStatusMsg.value = ''
  } catch { aiStatusMsg.value = ''; ElMessage.error('AI 分析失败') }
  finally { aiEstimating.value = false }
}

function applyRecommendation(rec: any) { subtaskForm.value.assignee_id = rec.user_id; ElMessage.success('已采纳') }

// ── Archive / Create ──
async function archiveProject(pid: string) {
  try { await projectsApi.delete(pid); ElMessage.success('已归档'); await loadProjects() }
  catch { ElMessage.error('归档失败') }
}
function onArchivedChange() { taskTrees.value = {}; expandedProjects.value.clear(); loadProjects() }

async function handleCreate() {
  if (!createForm.value.name.trim()) { ElMessage.warning('请输入项目名称'); return }
  creating.value = true
  try {
    await projectsApi.create({ name: createForm.value.name, description: createForm.value.description || undefined, start_date: createForm.value.start_date || undefined, end_date: createForm.value.end_date || undefined })
    ElMessage.success('项目已创建'); createDialogVisible.value = false
    createForm.value = { name: '', description: '', start_date: '', end_date: '' }
    await loadProjects()
  } catch { ElMessage.error('创建失败') } finally { creating.value = false }
}

// ── Helpers ──
function taskProgressColor(task: any): string {
  const pct = task.progress_pct ?? 0
  if (task.status === 'done' || pct >= 100) return '#67C23A'
  if (!task.deadline || !task.created_at) return pct > 0 ? '#409EFF' : '#C0C4CC'
  if (task.status === 'backlog') return '#C0C4CC'
  const now = Date.now(), start = new Date(task.created_at).getTime(), end = new Date(task.deadline).getTime()
  const span = end - start; if (span <= 0) return pct > 0 ? '#67C23A' : '#F56C6C'
  const deviation = pct - (Math.min(now - start, span) / span * 100)
  if (deviation >= 0) return '#67C23A'
  if (deviation >= -20) return '#E6A23C'
  return '#F56C6C'
}
function projectProgress(p: Project) { return p.task_count ? Math.round(p.completed_count / p.task_count * 100) : 0 }
function projectProgressColor(p: Project): string {
  const pct = projectProgress(p)
  if (pct >= 100 || p.status === 'completed') return '#67C23A'
  if (!p.start_date || !p.end_date) return pct > 0 ? '#409EFF' : '#C0C4CC'
  const span = new Date(p.end_date).getTime() - new Date(p.start_date).getTime()
  if (span <= 0) return '#409EFF'
  const deviation = pct - (Math.min(Date.now() - new Date(p.start_date).getTime(), span) / span * 100)
  return deviation >= 0 ? '#67C23A' : deviation >= -20 ? '#E6A23C' : '#F56C6C'
}
function statusType(s: string) { return ({ planning: 'info', active: '', paused: 'warning', completed: 'success', archived: 'danger' } as any)[s] || 'info' }
function statusLabel(s: string) { return ({ planning: '规划中', active: '进行中', paused: '已暂停', completed: '已完成', archived: '已归档' } as any)[s] || s }
function taskStatusType(s: string) { return ({ backlog: 'info', todo: '', in_progress: 'warning', in_review: '', done: 'success' } as any)[s] || 'info' }
function taskStatusLabel(s: string) { return ({ backlog: '待办池', todo: '待处理', in_progress: '进行中', in_review: '审核中', done: '已完成' } as any)[s] || s }
function formatDate(d: string | null) { return d ? d.slice(0, 10) : '-' }
function formatDateTime(d: string | null) { return d ? d.replace('T', ' ').slice(0, 16) : '' }
function goToBoard(pid: string) { router.push(`/projects/${pid}/board`) }

const summaryStats = computed(() => {
  const total = projects.value.length, active = projects.value.filter(p => p.status === 'active').length
  const totalTasks = projects.value.reduce((s, p) => s + (p.task_count || 0), 0)
  const doneTasks = projects.value.reduce((s, p) => s + (p.completed_count || 0), 0)
  return { total, active, totalTasks, doneTasks, overallRate: totalTasks > 0 ? Math.round(doneTasks / totalTasks * 100) : 0 }
})

onMounted(loadProjects)
</script>

<template>
  <div v-loading="loading" class="plv">
    <!-- Summary -->
    <div class="summary-bar">
      <div class="si"><span class="sv">{{ summaryStats.total }}</span><span class="sl">项目总数</span></div>
      <div class="si"><span class="sv active">{{ summaryStats.active }}</span><span class="sl">进行中</span></div>
      <div class="si"><span class="sv">{{ summaryStats.totalTasks }}</span><span class="sl">总任务数</span></div>
      <div class="si"><span class="sv done">{{ summaryStats.doneTasks }}</span><span class="sl">已完成</span></div>
      <div class="si"><span class="sv" :class="{ warn: summaryStats.overallRate < 50 }">{{ summaryStats.overallRate }}%</span><span class="sl">完成率</span></div>
      <el-switch v-model="showArchived" active-text="含归档" style="margin-left:auto" @change="onArchivedChange" />
      <el-button type="primary" @click="createDialogVisible = true">新建项目</el-button>
    </div>

    <!-- Project List -->
    <div class="ptree">
      <div v-for="project in projects" :key="project.id" class="pblock">
        <!-- Project Row -->
        <div class="prow" @click="toggleProject(project.id)">
          <div class="col-exp">
            <svg viewBox="0 0 1024 1024" width="14" height="14" :class="{ rot: isExpanded(project.id) }" class="ei"><path d="M384 256l320 256-320 256z" fill="currentColor"/></svg>
          </div>
          <div class="col-name pn"><strong>{{ project.name }}</strong>
            <el-tag :type="(statusType(project.status) as any)" size="small" style="margin-left:8px">{{ statusLabel(project.status) }}</el-tag>
          </div>
          <div class="col-fb"></div>
          <div class="col-who">{{ project.member_count }} 人</div>
          <div class="col-hrs center">{{ project.task_count }} 任务</div>
          <div class="col-prog">
            <el-progress :percentage="projectProgress(project)" :stroke-width="8" :color="projectProgressColor(project)" style="width:100px" />
            <span class="ptxt">{{ project.completed_count }}/{{ project.task_count }}</span>
          </div>
          <div class="col-dl">{{ formatDate(project.start_date) }} ~ {{ formatDate(project.end_date) }}</div>
          <div class="col-act center" @click.stop>
            <el-button type="primary" link size="small" @click="goToBoard(project.id)">看板</el-button>
            <el-popconfirm v-if="project.status !== 'archived' && canEdit" title="归档后不计入统计，确认？" @confirm="archiveProject(project.id)">
              <template #reference><el-button type="info" link size="small">归档</el-button></template>
            </el-popconfirm>
            <el-tag v-if="project.status === 'archived'" type="info" size="small" effect="plain">已归档</el-tag>
          </div>
        </div>

        <!-- Task Tree -->
        <div v-if="isExpanded(project.id)" class="ttree">
          <div v-if="loadingTrees[project.id]" class="tloading">加载中...</div>
          <template v-else-if="taskTrees[project.id]?.length">
            <div class="thead">
              <div class="col-exp"></div>
              <div class="col-name">任务名称</div>
              <div class="col-fb">最新进展</div>
              <div class="col-who">负责人</div>
              <div class="col-hrs center">工时(h)</div>
              <div class="col-prog">进度</div>
              <div class="col-dl">截止日期</div>
              <div class="col-act center">状态</div>
            </div>

            <div v-for="task in taskTrees[project.id]" :key="task.id" class="trow" :class="['d' + task._depth, { tdel: task.is_deleted }]">
              <div class="col-exp">
                <span v-if="task._depth === 0 && task.subtask_total > 0" class="sbadge">{{ task.subtask_done }}/{{ task.subtask_total }}</span>
              </div>
              <div class="col-name" :style="{ paddingLeft: (4 + task._depth * 18) + 'px' }">
                <span v-if="task._depth > 0" class="si2">└</span>
                <span class="tname">{{ task.title }}</span>
                <el-tag v-if="task.priority === 'urgent'" type="danger" size="small" style="margin-left:4px">紧急</el-tag>
                <el-tag v-else-if="task.priority === 'high'" type="danger" size="small" effect="plain" style="margin-left:4px">高</el-tag>
              </div>
              <!-- Progress Feedback Column -->
              <div class="col-fb" @click.stop>
                <span class="fb-text" @click="openFeedback(task)" :title="task.latest_note || '点击反馈进展'">
                  {{ task.latest_note || '反馈进展' }}
                </span>
              </div>
              <!-- Assignee -->
              <div class="col-who" @click.stop>
                <template v-if="canEdit && !task.is_deleted">
                  <el-select :model-value="task.assignee_id || ''" size="small" placeholder="未分配" clearable filterable class="isel" @change="(v: string) => handleAssigneeChange(task, v)">
                    <el-option v-for="u in users" :key="u.id" :label="u.full_name" :value="u.id" />
                  </el-select>
                </template>
                <span v-else class="who-text">{{ task.assignee_name || '未分配' }}</span>
              </div>
              <!-- Hours -->
              <div class="col-hrs center" @click.stop>
                <template v-if="canEdit && !task.is_deleted">
                  <el-input-number :model-value="task.estimated_hours" size="small" :min="0" :max="999" :precision="1" :controls="false" class="ihrs" placeholder="-" @change="(v: number) => handleFieldUpdate(task, 'estimated_hours', v)" />
                </template>
                <span v-else>{{ task.estimated_hours ? task.estimated_hours + 'h' : '-' }}</span>
              </div>
              <!-- Progress bar -->
              <div class="col-prog">
                <el-progress :percentage="task.progress_pct ?? (task.status === 'done' ? 100 : 0)" :stroke-width="6" :color="taskProgressColor(task)" style="width:90px" />
              </div>
              <!-- Deadline -->
              <div class="col-dl" @click.stop>
                <template v-if="canEdit && !task.is_deleted">
                  <el-date-picker :model-value="task.deadline ? task.deadline.slice(0, 10) : ''" type="date" size="small" value-format="YYYY-MM-DD" placeholder="-" class="idl" :class="{ ovd: task.is_overdue }" @update:model-value="(v: string) => handleFieldUpdate(task, 'deadline', v)" />
                </template>
                <span v-else :class="{ ovd: task.is_overdue }">{{ formatDate(task.deadline) }}</span>
              </div>
              <!-- Status + Actions -->
              <div class="col-act center" @click.stop>
                <el-select v-if="canEdit && !task.is_deleted" :model-value="task.status" size="small" class="isel ist" @change="(v: string) => handleStatusClick(task, v)">
                  <el-option v-for="opt in statusOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                </el-select>
                <el-tag v-else :type="(taskStatusType(task.status) as any)" size="small">{{ taskStatusLabel(task.status) }}</el-tag>
                <el-button v-if="canEdit && !task.is_deleted" type="primary" link size="small" title="添加子任务" @click="openSubtaskDialog(task, project.id)">+</el-button>
                <el-popconfirm v-if="canEdit && !task.is_deleted" title="标记删除？不计入统计" @confirm="handleDelete(task)">
                  <template #reference><el-button type="danger" link size="small" title="删除">x</el-button></template>
                </el-popconfirm>
              </div>
            </div>
          </template>
          <div v-else class="tloading">暂无任务</div>
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
        <el-form-item label="任务标题"><el-input v-model="subtaskForm.title" /></el-form-item>
        <el-form-item label="任务描述"><el-input v-model="subtaskForm.description" type="textarea" :rows="2" placeholder="可选，有助 AI 更准推荐" /></el-form-item>
        <el-form-item>
          <div class="ai-row">
            <el-button type="warning" :loading="aiEstimating" @click="handleAiEstimate" :disabled="!subtaskForm.title.trim()">AI 推荐人选 + 预估工时</el-button>
            <span v-if="aiStatusMsg" class="ai-st">{{ aiStatusMsg }}</span>
          </div>
        </el-form-item>
        <div v-if="aiEstimateInfo" class="ai-box">
          <div class="ai-hd">AI 分析结果</div>
          <div class="ai-est">预估工时: <strong>{{ aiEstimateInfo.estimated_hours }}h</strong>
            <el-tag :type="aiEstimateInfo.confidence === 'high' ? 'success' : aiEstimateInfo.confidence === 'medium' ? 'warning' : 'info'" size="small">{{ aiEstimateInfo.confidence === 'high' ? '高置信' : aiEstimateInfo.confidence === 'medium' ? '中置信' : '低置信' }}</el-tag>
          </div>
          <div class="ai-reason">{{ aiEstimateInfo.reasoning }}</div>
          <div v-if="aiRecommendations.length" class="ai-recs">
            <div class="ai-rt">推荐人选:</div>
            <div v-for="(rec, i) in aiRecommendations" :key="i" class="ai-ri">
              <span class="ri-rank">#{{ i + 1 }}</span> <span class="ri-name">{{ rec.name }}</span>
              <el-tag size="small" type="warning">{{ rec.score }}分</el-tag>
              <div class="ri-reason">{{ rec.reason }}</div>
              <el-button type="primary" size="small" @click="applyRecommendation(rec)">采纳</el-button>
            </div>
          </div>
        </div>
        <el-form-item label="负责人"><el-select v-model="subtaskForm.assignee_id" placeholder="选择负责人" clearable filterable style="width:100%"><el-option v-for="u in users" :key="u.id" :label="u.full_name" :value="u.id" /></el-select></el-form-item>
        <el-form-item label="预估工时"><el-input-number v-model="subtaskForm.estimated_hours" :min="0" :max="999" :precision="1" style="width:100%" /></el-form-item>
        <el-form-item label="截止日期"><el-date-picker v-model="subtaskForm.deadline" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="subtaskDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creatingSubtask" @click="handleCreateSubtask">创建</el-button>
      </template>
    </el-dialog>

    <!-- Status Change Dialog -->
    <el-dialog v-model="progressDialogVisible" title="更新状态和进度" width="440px">
      <div v-if="progressTarget" style="margin-bottom:16px;color:#606266;font-size:13px">
        <strong>{{ progressTarget.task.title }}</strong> →
        <el-tag :type="(taskStatusType(progressTarget.newStatus) as any)" size="small">{{ taskStatusLabel(progressTarget.newStatus) }}</el-tag>
      </div>
      <el-form label-width="80px">
        <el-form-item label="进度 (%)"><el-slider v-model="progressForm.progress_pct" :min="0" :max="100" :step="5" show-stops style="padding:0 8px" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="progressForm.note" type="textarea" :rows="2" placeholder="说明本次进展" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="progressDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmStatusChange">确认</el-button>
      </template>
    </el-dialog>

    <!-- Progress Feedback Drawer -->
    <el-drawer v-model="feedbackDialogVisible" :title="'任务进展 — ' + (feedbackTask?.title || '')" size="420px" direction="rtl">
      <div v-if="feedbackTask" class="fb-drawer">
        <!-- Submit feedback -->
        <div class="fb-form">
          <h4>反馈进展</h4>
          <el-form label-width="70px" size="small">
            <el-form-item label="进度 (%)">
              <el-slider v-model="feedbackForm.progress_pct" :min="0" :max="100" :step="5" show-input />
            </el-form-item>
            <el-form-item label="进展说明">
              <el-input v-model="feedbackForm.note" type="textarea" :rows="3" placeholder="描述当前进展、遇到的问题..." />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="feedbackSubmitting" @click="submitFeedback">提交</el-button>
            </el-form-item>
          </el-form>
        </div>
        <!-- History -->
        <div class="fb-history">
          <h4>历史记录</h4>
          <div v-loading="feedbackLoading">
            <el-timeline v-if="feedbackHistory.length">
              <el-timeline-item v-for="log in feedbackHistory" :key="log.id" :timestamp="formatDateTime(log.created_at)" placement="top" :color="log.progress_pct >= 100 ? '#67C23A' : '#409EFF'">
                <div class="fb-log">
                  <span class="fb-user">{{ log.user_name }}</span>
                  <el-tag size="small">{{ log.progress_pct }}%</el-tag>
                  <span v-if="log.hours_spent" class="fb-hrs">{{ log.hours_spent }}h</span>
                </div>
                <p v-if="log.note" class="fb-note">{{ log.note }}</p>
              </el-timeline-item>
            </el-timeline>
            <el-empty v-else description="暂无进展记录" :image-size="60" />
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.plv { padding: 0; }
.summary-bar { display: flex; align-items: center; gap: 24px; padding: 14px 20px; background: #fff; border-radius: 8px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.si { display: flex; flex-direction: column; align-items: center; }
.sv { font-size: 22px; font-weight: 700; color: #303133; }
.sv.active { color: #409EFF; } .sv.done { color: #67C23A; } .sv.warn { color: #E6A23C; }
.sl { font-size: 11px; color: #909399; margin-top: 2px; }

.ptree { display: flex; flex-direction: column; gap: 2px; }
.pblock { background: #fff; border-radius: 6px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }

/* Grid: 8 columns */
.prow, .trow, .thead {
  display: grid;
  grid-template-columns: 32px minmax(120px,1fr) minmax(60px,0.6fr) 80px 42px 90px 96px 156px;
  align-items: center; padding: 0 8px; min-height: 40px; gap: 2px;
}
.prow { background: #fafbfc; border-left: 4px solid #409EFF; cursor: pointer; min-height: 48px; }
.prow:hover { background: #f0f5ff; }
.pn strong { font-size: 13px; }
.thead { background: #f5f7fa; font-size: 11px; color: #909399; font-weight: 600; min-height: 30px; border-bottom: 1px solid #ebeef5; }
.trow { border-bottom: 1px solid #f2f3f5; font-size: 12px; min-height: 36px; }
.trow:last-child { border-bottom: none; }
.d0 { background: #fff; } .d1 { background: #fafbfc; } .d2 { background: #f5f7fa; }

.col-exp { display: flex; justify-content: center; align-items: center; color: #909399; }
.ei { transition: transform 0.2s; } .ei.rot { transform: rotate(90deg); }
.sbadge { font-size: 10px; color: #409EFF; background: #ecf5ff; padding: 1px 5px; border-radius: 8px; white-space: nowrap; }

.col-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.si2 { color: #c0c4cc; margin-right: 3px; }
.tname { }

.col-fb { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fb-text { font-size: 11px; color: #909399; cursor: pointer; padding: 2px 4px; border-radius: 3px; }
.fb-text:hover { background: #ecf5ff; color: #409EFF; }

.col-who { font-size: 11px; color: #606266; }
.who-text { }

.col-hrs { font-size: 11px; color: #606266; }
.col-hrs.center { text-align: center; }
.col-prog { display: flex; align-items: center; }
.ptxt { font-size: 10px; color: #909399; white-space: nowrap; margin-left: 4px; }
.col-dl { font-size: 11px; color: #909399; }
.col-act { font-size: 11px; }
.col-act.center { text-align: center; display: flex; align-items: center; justify-content: center; gap: 2px; }
.ovd { color: #F56C6C !important; font-weight: 600; }

/* Inline controls */
.isel { width: 100%; }
.isel :deep(.el-input__wrapper) { box-shadow: none !important; background: transparent; padding: 0 2px; }
.isel :deep(.el-input__wrapper:hover) { box-shadow: 0 0 0 1px #dcdfe6 inset !important; }
.isel :deep(.el-input__inner) { font-size: 11px; }
.ist { width: 72px; }
.ihrs { width: 46px; }
.ihrs :deep(.el-input__wrapper) { box-shadow: none !important; background: transparent; padding: 0; }
.ihrs :deep(.el-input__wrapper:hover) { box-shadow: 0 0 0 1px #dcdfe6 inset !important; }
.ihrs :deep(.el-input__inner) { font-size: 11px; text-align: center; }
.idl { width: 92px; }
.idl :deep(.el-input__wrapper) { box-shadow: none !important; background: transparent; padding: 0 2px; }
.idl :deep(.el-input__wrapper:hover) { box-shadow: 0 0 0 1px #dcdfe6 inset !important; }
.idl :deep(.el-input__inner) { font-size: 11px; }
.idl.ovd :deep(.el-input__inner) { color: #F56C6C; font-weight: 600; }

/* Deleted */
.tdel { opacity: 0.4; }
.tdel .tname { text-decoration: line-through; color: #c0c4cc; }
.tdel .isel :deep(.el-input__wrapper), .tdel .ihrs :deep(.el-input__wrapper), .tdel .idl :deep(.el-input__wrapper) { pointer-events: none; }

.ttree { border-top: 1px solid #ebeef5; }
.tloading { padding: 12px 20px; text-align: center; color: #909399; font-size: 12px; }

/* AI */
.ai-row { display: flex; align-items: center; gap: 12px; }
.ai-st { font-size: 12px; color: #e6a23c; animation: pulse 1.5s infinite; }
@keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.5; } }
.ai-box { background: #fdf6ec; border: 1px solid #faecd8; border-radius: 6px; padding: 10px 14px; margin-bottom: 14px; }
.ai-hd { font-weight: 600; font-size: 13px; color: #e6a23c; margin-bottom: 6px; }
.ai-est { display: flex; align-items: center; gap: 10px; font-size: 12px; margin-bottom: 4px; }
.ai-reason { font-size: 11px; color: #909399; margin-bottom: 8px; }
.ai-rt { font-size: 12px; font-weight: 600; margin-bottom: 4px; }
.ai-ri { display: flex; align-items: center; gap: 6px; padding: 4px 0; border-bottom: 1px solid #faecd8; flex-wrap: wrap; }
.ai-ri:last-child { border-bottom: none; }
.ri-rank { font-weight: 700; color: #e6a23c; } .ri-name { font-weight: 500; }
.ri-reason { font-size: 11px; color: #909399; width: 100%; }

/* Feedback drawer */
.fb-drawer { padding: 0 4px; }
.fb-form { margin-bottom: 20px; }
.fb-form h4, .fb-history h4 { font-size: 14px; font-weight: 600; margin: 0 0 10px 0; color: #303133; }
.fb-log { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.fb-user { font-weight: 500; color: #409EFF; }
.fb-hrs { color: #909399; }
.fb-note { margin: 4px 0 0; font-size: 12px; color: #606266; line-height: 1.5; }
</style>
