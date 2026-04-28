<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import draggable from 'vuedraggable'
import { projectsApi } from '@/api/projects'
import { tasksApi } from '@/api/tasks'
import { usersApi } from '@/api/users'
import { aiApi } from '@/api/ai'
import { reportsApi, type ReportType } from '@/api/reports'
import { useAuthStore } from '@/stores/auth'
import TaskDataSkillPanel from '@/components/tasks/TaskDataSkillPanel.vue'
import type { Project, User, TaskProgress } from '@/types/models'
import {
  flattenTaskTree,
  getVisibleTaskRows,
  hasTaskChildren,
  moveVisibleRow,
  normalizeTaskTreeForScope,
  orderedSiblingsForTask,
  scopePeerForRow,
} from '@/utils/taskTree'

const router = useRouter()
const auth = useAuthStore()

const loading = ref(false)
const projects = ref<Project[]>([])
const users = ref<User[]>([])
const showArchived = ref(false)

const taskTrees = ref<Record<string, any[]>>({})
const loadingTrees = ref<Record<string, boolean>>({})
const expandedProjects = ref<Set<string>>(new Set())
const draggingTaskId = ref<string | null>(null)
const collapsedTaskIds = ref<Record<string, string[]>>({})

const canCreateProject = computed(() => auth.can('project.create'))
const canArchiveProject = computed(() => auth.can('project.archive'))
const canEditProject = computed(() => auth.can('project.edit'))
const canCreateTask = computed(() => auth.can('task.create'))
const canEditTask = computed(() => auth.can('task.edit'))
const canAssignTask = computed(() => auth.can('task.assign'))
const canSetTaskHours = computed(() => auth.can('task.set_hours'))
const canSetTaskDeadline = computed(() => auth.can('task.set_deadline'))
const canSignoffTask = computed(() => auth.can('task.signoff'))
const canDeleteTask = computed(() => auth.can('task.delete'))
const canUseAiEstimate = computed(() => auth.can('ai.estimate'))
const canUseAiRisk = computed(() => auth.can('ai.risk'))
const canManageProgress = computed(() => auth.can('progress.submit'))
const canViewInspectionReport = computed(() => auth.isAuthenticated)

// Create project
const createDialogVisible = ref(false)
const createForm = ref({ name: '', goal: '', description: '', start_date: '', end_date: '' })
const creating = ref(false)

// Add subtask
const subtaskDialogVisible = ref(false)
const subtaskParent = ref<{ id: string | null; title: string; projectId: string } | null>(null)
const subtaskForm = ref({ title: '', goal: '', description: '', assignee_ids: [] as string[], estimated_hours: null as number | null, deadline: '' })
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
const feedbackForm = ref({ progress_pct: 0, note: '', hours_spent: null as number | null })
const feedbackSubmitting = ref(false)
const projectDetailVisible = ref(false)
const projectDetailLoading = ref(false)
const projectDetailSaving = ref(false)
const projectDetail = ref<Project | null>(null)
const projectDetailForm = ref({ goal: '', description: '' })
const taskDetailVisible = ref(false)
const taskDetail = ref<any>(null)
const taskDetailSaving = ref(false)
const taskDetailForm = ref({ title: '', goal: '', description: '' })

// Group progress import
const progressImportDialogVisible = ref(false)
const progressImportText = ref('')
const progressImportStatus = ref('')
const progressImportPreview = ref<any[]>([])
const progressImportUnmatched = ref<any[]>([])
const progressImportLoading = ref(false)
const progressImportSubmitting = ref(false)

// AI project setup
const projectPlanPrompt = ref('')
const projectPlanStatus = ref('')
const projectPlanPreview = ref<any>(null)
const projectPlanLoading = ref(false)
const projectPlanSubmitting = ref(false)

// AI daily brief
const dailyBriefDialogVisible = ref(false)
const dailyBriefStatus = ref('')
const dailyBriefResult = ref<any>(null)
const dailyBriefLoading = ref(false)
const reportGeneratedAt = ref<string | null>(null)
const reportType = ref<ReportType>('daily')
const reportRecipients = ref('')
const reportSending = ref(false)

// AI retrospective
const retrospectiveDialogVisible = ref(false)
const retrospectiveProject = ref<Project | null>(null)
const retrospectiveStatus = ref('')
const retrospectiveResult = ref<any>(null)
const retrospectiveLoading = ref(false)

function userNames(ids: string[] | null | undefined): string {
  if (!ids?.length) return '未分配'
  return ids
    .map((id) => users.value.find(u => u.id === id)?.full_name)
    .filter(Boolean)
    .join('、') || '未分配'
}

function formatApiError(err: any, fallback: string) {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const message = detail
      .map((item) => item?.msg || item?.message || item?.detail || JSON.stringify(item))
      .filter(Boolean)
      .join('；')
    return message || fallback
  }
  if (detail && typeof detail === 'object') {
    return detail.message || detail.msg || detail.detail || JSON.stringify(detail)
  }
  return err?.message || fallback
}

// ── Data Loading ──
async function loadProjects() {
  loading.value = true
  try {
    const projRes = await projectsApi.list(1, 100, showArchived.value)
    projects.value = projRes.data.items
  } catch {
    projects.value = []
    ElMessage.error('加载项目列表失败')
  }
  try {
    const userRes = await usersApi.list(1, 200)
    users.value = userRes.data.items
  } catch {
    users.value = []
  } finally {
    loading.value = false
  }
}

async function loadTaskTree(pid: string, force = false) {
  if (taskTrees.value[pid] && !force) return
  loadingTrees.value[pid] = true
  try {
    const res = await projectsApi.getTaskTree(pid)
    taskTrees.value[pid] = flattenTaskTree(res.data)
    pruneCollapsedTaskIds(pid)
  } catch { ElMessage.error('加载任务树失败') }
  finally { loadingTrees.value[pid] = false }
}

async function refreshProjectSummary(projectId: string) {
  if (!projectId) return
  try {
    const res = await projectsApi.get(projectId)
    projects.value = projects.value.map((item) => item.id === projectId ? { ...item, ...res.data } : item)
  } catch {
    // Summary refresh is non-blocking; the task operation already succeeded.
  }
}

function toggleProject(pid: string) {
  if (expandedProjects.value.has(pid)) { expandedProjects.value.delete(pid) }
  else { expandedProjects.value.add(pid); loadTaskTree(pid) }
}
function isExpanded(pid: string) { return expandedProjects.value.has(pid) }

function collapsedTaskSet(projectId: string) {
  return new Set(collapsedTaskIds.value[projectId] || [])
}

function visibleTaskRows(projectId: string) {
  return getVisibleTaskRows(taskTrees.value[projectId] || [], collapsedTaskSet(projectId))
}

function pruneCollapsedTaskIds(projectId: string) {
  const ids = new Set((taskTrees.value[projectId] || []).map((task: any) => task.id))
  const next = (collapsedTaskIds.value[projectId] || []).filter((id) => ids.has(id))
  collapsedTaskIds.value = { ...collapsedTaskIds.value, [projectId]: next }
}

function isTaskCollapsed(projectId: string, task: any) {
  return collapsedTaskSet(projectId).has(task.id)
}

function setTaskCollapsed(projectId: string, taskId: string, collapsed: boolean) {
  const ids = new Set(collapsedTaskIds.value[projectId] || [])
  if (collapsed) ids.add(taskId)
  else ids.delete(taskId)
  collapsedTaskIds.value = { ...collapsedTaskIds.value, [projectId]: Array.from(ids) }
}

function toggleTaskCollapse(projectId: string, task: any) {
  setTaskCollapsed(projectId, task.id, !isTaskCollapsed(projectId, task))
}

function taskHasChildren(projectId: string, task: any) {
  return hasTaskChildren(taskTrees.value[projectId] || [], task.id)
}

function taskNameIndentStyle(task: any) {
  return { '--task-depth': `${task._depth || 0}` } as Record<string, string>
}

// ── Inline Edit (admin only) ──
async function handleAssigneeChange(task: any, newIds: string[]) {
  try {
    const res = await tasksApi.assign(task.id, newIds || [])
    Object.assign(task, res.data)
  } catch { ElMessage.error('更新失败') }
}

async function handleFieldUpdate(task: any, field: string, value: any) {
  try {
    const res = await tasksApi.update(task.id, { [field]: value || null } as any)
    Object.assign(task, res.data)
    const projectId = resolveProjectIdForTask(task)
    if (field === 'start_date' && projectId) await refreshProjectSummary(projectId)
  } catch { ElMessage.error('更新失败') }
}

function canMoveTaskRow(evt: any) {
  const dragged = evt?.draggedContext?.element
  const related = evt?.relatedContext?.element
  if (!canEditTask.value || !dragged || dragged.is_deleted || !related) return false
  const tree = Object.values(taskTrees.value).find((items: any[]) => items.some((task: any) => task.id === dragged.id)) as any[] | undefined
  const peer = tree ? scopePeerForRow(tree, related, dragged) : null
  return !!peer && peer.id !== dragged.id
}

function handleTaskRowDragStart(projectId: string, evt: any) {
  const rows = visibleTaskRows(projectId)
  draggingTaskId.value = rows[evt?.oldIndex]?.id || null
}

async function handleTaskRowDragEnd(projectId: string, evt: any) {
  if (evt?.oldIndex === evt?.newIndex) {
    draggingTaskId.value = null
    return
  }
  const tree = taskTrees.value[projectId] || []
  const visibleRows = visibleTaskRows(projectId)
  const oldIndex = Number(evt?.oldIndex)
  const newIndex = Number(evt?.newIndex)
  const moved = visibleRows.find((task: any) => task.id === draggingTaskId.value) || visibleRows[oldIndex]
  draggingTaskId.value = null
  if (!moved) {
    await loadTaskTree(projectId, true)
    return
  }

  const reorderedVisibleRows = moveVisibleRow(visibleRows, oldIndex, newIndex)
  const movedInReorderedRows = reorderedVisibleRows.find((task: any) => task.id === moved.id) || moved
  const siblings = orderedSiblingsForTask(reorderedVisibleRows, movedInReorderedRows)
  if (siblings.length < 2) {
    await loadTaskTree(projectId, true)
    return
  }
  taskTrees.value[projectId] = normalizeTaskTreeForScope(tree, movedInReorderedRows, siblings)
  try {
    await tasksApi.reorder(siblings.map((task: any, index: number) => ({
      task_id: task.id,
      status: task.status,
      sort_order: index + 1,
    })))
    siblings.forEach((task: any, index: number) => { task.sort_order = index + 1 })
    ElMessage.success('排序已更新')
  } catch (err: any) {
    ElMessage({
      type: 'error',
      message: formatApiError(err, '排序更新失败'),
      showClose: true,
      duration: 6000,
    })
    await loadTaskTree(projectId, true)
  }
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
function resolveProjectIdForTask(task: any, projectId?: string) {
  if (projectId) return projectId
  if (taskDetail.value?.projectId && taskDetail.value?.id === task?.id) return taskDetail.value.projectId
  return Object.keys(taskTrees.value).find((pid) => (taskTrees.value[pid] || []).some((item: any) => item.id === task?.id)) || ''
}

async function handleDelete(task: any, projectId?: string) {
  const pid = resolveProjectIdForTask(task, projectId)
  try {
    await tasksApi.delete(task.id)
    if (feedbackTask.value?.id === task.id) feedbackTask.value = { ...feedbackTask.value, is_deleted: true }
    if (taskDetail.value?.id === task.id) taskDetail.value = { ...taskDetail.value, is_deleted: true }
    ElMessage.success('任务已标记删除')
    if (pid) await loadTaskTree(pid, true)
    if (pid) await refreshProjectSummary(pid)
  } catch {
    ElMessage.error('删除失败')
  }
}

// ── Progress Feedback (everyone) ──
async function handleRestore(task: any, projectId?: string) {
  const pid = resolveProjectIdForTask(task, projectId)
  try {
    const res = await tasksApi.restore(task.id)
    Object.assign(task, res.data)
    if (feedbackTask.value?.id === task.id) feedbackTask.value = { ...feedbackTask.value, ...res.data }
    if (taskDetail.value?.id === task.id) taskDetail.value = { ...taskDetail.value, ...res.data }
    ElMessage.success('任务已恢复')
    if (pid) await loadTaskTree(pid, true)
    if (pid) await refreshProjectSummary(pid)
  } catch (err: any) {
    ElMessage.error(formatApiError(err, '恢复失败'))
  }
}

function syncProjectDetailForm(project: Project | null) {
  projectDetailForm.value = {
    goal: project?.goal || '',
    description: project?.description || '',
  }
}

async function openProjectDetail(project: Project) {
  projectDetailVisible.value = true
  projectDetailLoading.value = true
  projectDetail.value = { ...project }
  syncProjectDetailForm(projectDetail.value)
  try {
    const res = await projectsApi.get(project.id)
    projectDetail.value = res.data
    syncProjectDetailForm(projectDetail.value)
  } catch {
    ElMessage.error('加载项目详情失败')
  } finally {
    projectDetailLoading.value = false
  }
}

async function saveProjectDetail() {
  if (!projectDetail.value) return
  projectDetailSaving.value = true
  try {
    const res = await projectsApi.update(projectDetail.value.id, {
      goal: projectDetailForm.value.goal.trim() || null,
      description: projectDetailForm.value.description.trim() || null,
    })
    projectDetail.value = res.data
    syncProjectDetailForm(projectDetail.value)
    projects.value = projects.value.map((item) => item.id === res.data.id ? { ...item, ...res.data } : item)
    ElMessage.success('项目信息已更新')
  } catch (err: any) {
    ElMessage.error(formatApiError(err, '保存失败'))
  } finally {
    projectDetailSaving.value = false
  }
}

function openTaskDetail(task: any, projectId: string) {
  taskDetail.value = { ...task, projectId }
  syncTaskDetailForm(taskDetail.value)
  taskDetailVisible.value = true
}

function syncTaskDetailForm(task: any | null) {
  taskDetailForm.value = {
    title: task?.title || '',
    goal: task?.goal || '',
    description: task?.description || '',
  }
}

function mergeTaskIntoTrees(updated: any) {
  for (const tree of Object.values(taskTrees.value)) {
    const item = (tree as any[]).find((task) => task.id === updated.id)
    if (item) Object.assign(item, updated)
  }
}

async function saveTaskDetail() {
  if (!taskDetail.value) return
  const title = taskDetailForm.value.title.trim()
  if (!title) {
    ElMessage.warning('请输入任务名称')
    return
  }

  taskDetailSaving.value = true
  try {
    const projectId = taskDetail.value.projectId || resolveProjectIdForTask(taskDetail.value)
    const res = await tasksApi.update(taskDetail.value.id, {
      title,
      goal: taskDetailForm.value.goal.trim() || null,
      description: taskDetailForm.value.description.trim() || null,
    } as any)
    taskDetail.value = { ...taskDetail.value, ...res.data, projectId }
    syncTaskDetailForm(taskDetail.value)
    mergeTaskIntoTrees(res.data)
    ElMessage.success('任务信息已更新')
  } catch (err: any) {
    ElMessage.error(formatApiError(err, '保存失败'))
  } finally {
    taskDetailSaving.value = false
  }
}

async function handleTaskDetailDataSkillAdopted(entry: TaskProgress) {
  if (!taskDetail.value) return
  taskDetail.value = { ...taskDetail.value, progress_pct: entry.progress_pct }
  const projectId = taskDetail.value.projectId || resolveProjectIdForTask(taskDetail.value)
  if (projectId) await loadTaskTree(projectId, true)
}

async function openFeedback(task: any, projectId?: string) {
  feedbackTask.value = { ...task, projectId: projectId || resolveProjectIdForTask(task) }
  feedbackForm.value = {
    progress_pct: task.progress_pct || 0,
    note: '',
    hours_spent: null,
  }
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
  if (feedbackTask.value.is_deleted) {
    ElMessage.warning('已删除任务不支持反馈进展')
    return
  }
  if (!feedbackForm.value.note.trim()) {
    ElMessage.warning('请填写进展说明')
    return
  }
  feedbackSubmitting.value = true
  try {
    await tasksApi.logProgress(feedbackTask.value.id, {
      progress_pct: feedbackForm.value.progress_pct,
      note: feedbackForm.value.note,
      hours_spent: feedbackForm.value.hours_spent ?? undefined,
    })
    feedbackTask.value.progress_pct = feedbackForm.value.progress_pct
    feedbackTask.value.latest_note = feedbackForm.value.note
    mergeTaskIntoTrees({
      id: feedbackTask.value.id,
      progress_pct: feedbackForm.value.progress_pct,
      latest_note: feedbackForm.value.note,
    })
    if (taskDetail.value?.id === feedbackTask.value.id) {
      taskDetail.value = {
        ...taskDetail.value,
        progress_pct: feedbackForm.value.progress_pct,
        latest_note: feedbackForm.value.note,
      }
    }
    ElMessage.success('进展已提交')
    feedbackForm.value.note = ''
    feedbackForm.value.hours_spent = null
    const res = await tasksApi.getProgress(feedbackTask.value.id)
    feedbackHistory.value = res.data
  } catch (err: any) {
    ElMessage.error(formatApiError(err, '提交失败'))
  } finally {
    feedbackSubmitting.value = false
  }
}

function openProgressImport() {
  progressImportText.value = ''
  progressImportStatus.value = ''
  progressImportPreview.value = []
  progressImportUnmatched.value = []
  progressImportDialogVisible.value = true
}

async function previewProgressImport() {
  if (!progressImportText.value.trim()) {
    ElMessage.warning('请粘贴群进展内容')
    return
  }
  progressImportLoading.value = true
  progressImportStatus.value = '正在识别...'
  progressImportPreview.value = []
  progressImportUnmatched.value = []
  try {
    const data = await aiApi.previewProgressImport(
      progressImportText.value,
      (msg: string) => { progressImportStatus.value = msg },
    )
    progressImportPreview.value = (data.updates || []).map((item: any) => ({
      ...item,
      selected: Boolean(item.task_id),
    }))
    progressImportUnmatched.value = data.unmatched || []
    progressImportStatus.value = ''
  } catch {
    progressImportStatus.value = ''
    ElMessage.error('AI 识别进展失败')
  } finally {
    progressImportLoading.value = false
  }
}

async function commitProgressImport() {
  const updates = progressImportPreview.value
    .filter((item: any) => item.selected && item.task_id)
    .map((item: any) => ({
      task_id: item.task_id,
      progress_pct: item.progress_pct,
      note: item.note || item.raw_text || '',
      person_name: item.person_name || '',
      reported_at: item.reported_at || '',
    }))
  if (!updates.length) {
    ElMessage.warning('请选择需要同步的进展')
    return
  }
  progressImportSubmitting.value = true
  try {
    await aiApi.commitProgressImport(updates)
    ElMessage.success(`已同步 ${updates.length} 条进展`)
    await Promise.all(Array.from(expandedProjects.value).map(pid => loadTaskTree(pid, true)))
    await loadProjects()
    progressImportDialogVisible.value = false
    dailyBriefDialogVisible.value = true
    await refreshInspectionReport('daily', true)
  } catch {
    ElMessage.error('同步进展失败')
  } finally {
    progressImportSubmitting.value = false
  }
}

function resetProjectPlan() {
  projectPlanPrompt.value = ''
  projectPlanStatus.value = ''
  projectPlanPreview.value = null
}

function openCreateProjectDialog() {
  createForm.value = { name: '', goal: '', description: '', start_date: '', end_date: '' }
  resetProjectPlan()
  createDialogVisible.value = true
}

async function previewProjectPlan() {
  if (!projectPlanPrompt.value.trim()) {
    ElMessage.warning('请描述项目目标')
    return
  }
  projectPlanLoading.value = true
  projectPlanStatus.value = '正在生成项目计划...'
  projectPlanPreview.value = null
  try {
    projectPlanPreview.value = await aiApi.previewProjectPlan(
      projectPlanPrompt.value,
      (msg: string) => { projectPlanStatus.value = msg },
    )
    projectPlanStatus.value = ''
  } catch {
    projectPlanStatus.value = ''
    ElMessage.error('AI 生成项目计划失败')
  } finally {
    projectPlanLoading.value = false
  }
}

async function commitProjectPlan() {
  if (!projectPlanPreview.value) return
  projectPlanSubmitting.value = true
  try {
    const res = await aiApi.commitProjectPlan(projectPlanPreview.value)
    const project = (res.data as any).project
    ElMessage.success('项目和任务树已创建')
    createDialogVisible.value = false
    resetProjectPlan()
    await loadProjects()
    if (project?.id) {
      expandedProjects.value.add(project.id)
      await loadTaskTree(project.id, true)
    }
  } catch {
    ElMessage.error('创建项目计划失败')
  } finally {
    projectPlanSubmitting.value = false
  }
}

async function loadInspectionReport(type: ReportType, silent = false) {
  reportType.value = type
  dailyBriefResult.value = null
  reportGeneratedAt.value = null
  dailyBriefStatus.value = '正在读取巡检报告...'
  dailyBriefLoading.value = true
  try {
    const res = await reportsApi.snapshot(type)
    dailyBriefResult.value = res.data.report || null
    reportGeneratedAt.value = res.data.generated_at || null
    dailyBriefStatus.value = ''
  } catch (err: any) {
    dailyBriefStatus.value = ''
    if (!silent) {
      ElMessage.error(formatApiError(err, '巡检报告读取失败'))
    } else {
      ElMessage.warning(formatApiError(err, '进展已同步，但巡检报告读取失败'))
    }
  } finally {
    dailyBriefLoading.value = false
  }
}

async function openDailyBrief(silent = false) {
  dailyBriefDialogVisible.value = true
  await loadInspectionReport('daily', silent)
}

async function changeReportType(value: string | number | boolean | undefined) {
  const type: ReportType = value === 'weekly' ? 'weekly' : 'daily'
  if (dailyBriefLoading.value || type === reportType.value) return
  await loadInspectionReport(type)
}

async function refreshInspectionReport(type: ReportType = reportType.value, silent = false) {
  if (dailyBriefLoading.value) return
  reportType.value = type
  dailyBriefResult.value = null
  reportGeneratedAt.value = null
  dailyBriefStatus.value = type === 'weekly' ? '正在刷新周报...' : '正在刷新巡检报告...'
  dailyBriefLoading.value = true
  try {
    const res = await reportsApi.refresh(type)
    dailyBriefResult.value = res.data.report || null
    reportGeneratedAt.value = res.data.generated_at || null
    dailyBriefStatus.value = ''
    if (!silent) {
      ElMessage.success('巡检报告已刷新')
    }
  } catch (err: any) {
    dailyBriefStatus.value = ''
    if (silent) {
      ElMessage.warning(formatApiError(err, '进展已同步，但巡检报告刷新失败'))
    } else {
      ElMessage.error(formatApiError(err, '巡检报告刷新失败'))
    }
  } finally {
    dailyBriefLoading.value = false
  }
}

function parseReportRecipients(): string[] {
  return reportRecipients.value
    .split(/[,;\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

async function sendInspectionReport() {
  const recipients = parseReportRecipients()
  if (!dailyBriefResult.value) {
    await loadInspectionReport(reportType.value)
  }
  if (!dailyBriefResult.value) {
    ElMessage.warning('暂无巡检报告，请先刷新生成')
    return
  }
  reportSending.value = true
  try {
    await reportsApi.sendReport({
      report_type: reportType.value,
      recipients,
      report: dailyBriefResult.value,
    })
    ElMessage.success('报告邮件已发送')
  } catch (err: any) {
    ElMessage.error(formatApiError(err, '报告邮件发送失败'))
  } finally {
    reportSending.value = false
  }
}

async function openRetrospective(project: Project) {
  retrospectiveProject.value = project
  retrospectiveDialogVisible.value = true
  retrospectiveResult.value = null
  retrospectiveStatus.value = '正在生成项目复盘...'
  retrospectiveLoading.value = true
  try {
    retrospectiveResult.value = await aiApi.projectRetrospective(project.id, (msg: string) => { retrospectiveStatus.value = msg })
    retrospectiveStatus.value = ''
  } catch {
    retrospectiveStatus.value = ''
    ElMessage.error('项目复盘生成失败')
  } finally {
    retrospectiveLoading.value = false
  }
}

// ── Add Subtask (admin only) ──
function openSubtaskDialog(task: any, projectId: string) {
  subtaskParent.value = { id: task.id, title: task.title, projectId }
  subtaskForm.value = { title: '', goal: '', description: '', assignee_ids: [], estimated_hours: null, deadline: '' }
  aiRecommendations.value = []; aiEstimateInfo.value = null
  subtaskDialogVisible.value = true
}

function openRootTaskDialog(project: Project) {
  subtaskParent.value = { id: null, title: project.name, projectId: project.id }
  subtaskForm.value = { title: '', goal: '', description: '', assignee_ids: [], estimated_hours: null, deadline: '' }
  aiRecommendations.value = []; aiEstimateInfo.value = null
  subtaskDialogVisible.value = true
}

async function handleCreateSubtask() {
  if (!subtaskForm.value.title.trim() || !subtaskParent.value) { ElMessage.warning('请输入子任务标题'); return }
  creatingSubtask.value = true
  try {
    const payload: any = { title: subtaskForm.value.title }
    if (subtaskForm.value.goal) payload.goal = subtaskForm.value.goal
    if (subtaskForm.value.description) payload.description = subtaskForm.value.description
    if (subtaskForm.value.assignee_ids.length) payload.assignee_ids = subtaskForm.value.assignee_ids
    if (subtaskForm.value.estimated_hours) payload.estimated_hours = subtaskForm.value.estimated_hours
    if (subtaskForm.value.deadline) payload.deadline = subtaskForm.value.deadline
    if (subtaskParent.value.id) {
      await tasksApi.createSubtask(subtaskParent.value.id, payload)
      ElMessage.success('子任务已创建')
    } else {
      await tasksApi.create(subtaskParent.value.projectId, payload)
      ElMessage.success('任务已创建')
    }
    subtaskDialogVisible.value = false
    if (subtaskParent.value.id) {
      setTaskCollapsed(subtaskParent.value.projectId, subtaskParent.value.id, false)
    }
    await loadTaskTree(subtaskParent.value.projectId, true)
    await refreshProjectSummary(subtaskParent.value.projectId)
  } catch { ElMessage.error('创建失败') }
  finally { creatingSubtask.value = false }
}

async function handleAiEstimate() {
  if (!subtaskForm.value.title.trim() || !subtaskParent.value) return
  aiEstimating.value = true; aiStatusMsg.value = '正在启动 AI...'
  try {
    const data = await aiApi.estimateTask(subtaskParent.value.projectId, subtaskForm.value.title, subtaskForm.value.goal, subtaskForm.value.description, (msg: string) => { aiStatusMsg.value = msg })
    aiEstimateInfo.value = data
    aiRecommendations.value = data.recommended_assignees || []
    if (data.estimated_hours && !subtaskForm.value.estimated_hours) subtaskForm.value.estimated_hours = data.estimated_hours
    aiStatusMsg.value = ''
  } catch { aiStatusMsg.value = ''; ElMessage.error('AI 分析失败') }
  finally { aiEstimating.value = false }
}

function applyRecommendation(rec: any) { subtaskForm.value.assignee_ids = rec.user_id ? [rec.user_id] : []; ElMessage.success('已采纳') }

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
    await projectsApi.create({
      name: createForm.value.name,
      goal: createForm.value.goal || undefined,
      description: createForm.value.description || undefined,
      start_date: createForm.value.start_date || undefined,
      end_date: createForm.value.end_date || undefined,
    })
    ElMessage.success('项目已创建'); createDialogVisible.value = false
    createForm.value = { name: '', goal: '', description: '', start_date: '', end_date: '' }
    resetProjectPlan()
    await loadProjects()
  } catch { ElMessage.error('创建失败') } finally { creating.value = false }
}

// ── Helpers ──
function taskProgressColor(task: any): string {
  const pct = task.progress_pct ?? 0
  if (task.status === 'done') return '#67C23A'
  if (pct >= 100) return '#E6A23C'
  const sd = task.start_date || task.created_at
  if (!task.deadline || !sd) return pct > 0 ? '#409EFF' : '#C0C4CC'
  const now = Date.now(), start = new Date(sd).getTime(), end = new Date(task.deadline).getTime()
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
function statusType(s: string) { return ({ planning: 'info', active: '', completed: 'success', archived: 'danger' } as any)[s] || 'info' }
function statusLabel(s: string) { return ({ planning: '规划中', active: '进行中', completed: '已完成', archived: '已归档' } as any)[s] || s }
function taskStatusType(s: string) { return ({ not_started: 'info', in_progress: 'warning', done: 'success' } as any)[s] || 'info' }
function taskStatusLabel(s: string) { return ({ not_started: '待开始', in_progress: '进行中', done: '已完成' } as any)[s] || s }
function taskNeedsSignoff(task: any) { return task.status !== 'done' && (task.progress_pct ?? 0) >= 100 }
function taskDisplayStatusType(task: any) { return task.is_deleted ? 'info' : taskStatusType(task.status) }
function taskDisplayStatusLabel(task: any) { return task.is_deleted ? '已删除' : taskStatusLabel(task.status) }
function findProjectTask(projectId: string, taskId: string | null | undefined) {
  if (!projectId || !taskId) return null
  return (taskTrees.value[projectId] || []).find((item: any) => item.id === taskId) || null
}
function canRestoreTask(task: any, projectId: string) {
  if (!task?.is_deleted) return false
  if (!task._parentId) return true
  const parent = findProjectTask(projectId, task._parentId)
  return !parent?.is_deleted
}
function formatDate(d: string | null) { return d ? d.slice(0, 10) : '-' }
function formatDateTime(d: string | null) { return d ? d.replace('T', ' ').slice(0, 16) : '' }
function goToBoard(pid: string) { router.push(`/projects/${pid}/board`) }
function asList(value: any): any[] { return Array.isArray(value) ? value : [] }
const reportSectionKeys = computed(() => {
  const base = ['risky_projects', 'overdue_blocked_tasks', 'progress_fast_top3', 'progress_slow_top3', 'priority_tasks', 'signoff_pending']
  if (dailyBriefResult.value?.completed_tasks) base.push('completed_tasks')
  if (dailyBriefResult.value?.progress_updates) base.push('progress_updates')
  return base
})
function dailySectionLabel(section: string): string {
  return ({
    risky_projects: '风险项目',
    overdue_blocked_tasks: '逾期 / 阻塞任务',
    progress_fast_top3: '进展快 TOP3',
    progress_slow_top3: '进展慢 TOP3',
    priority_tasks: '优先推进任务',
    signoff_pending: '待会签任务',
    completed_tasks: '已会签完成',
    progress_updates: '进展记录',
  } as any)[section] || section
}
function retrospectiveSectionLabel(section: string): string {
  return ({ wins: '做得好的地方', issues: '主要问题', estimation_lessons: '估时经验', process_improvements: '流程改进', reusable_template: '可复用模板' } as any)[section] || section
}

async function handleSignoff(task: any, projectId: string) {
  try {
    const res = await tasksApi.signoff(task.id)
    Object.assign(task, res.data)
    if (task._parentId) recalcParent(task._parentId)
    if (taskDetail.value?.id === task.id) taskDetail.value = { ...taskDetail.value, ...res.data }
    await refreshProjectSummary(projectId)
    ElMessage.success('任务已会签完成')
  } catch {
    ElMessage.error('会签失败，请确认进度已达到 100%')
  }
}

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
      <div class="summary-stats">
        <div class="si"><span class="sv">{{ summaryStats.total }}</span><span class="sl">项目总数</span></div>
        <div class="si"><span class="sv active">{{ summaryStats.active }}</span><span class="sl">进行中</span></div>
        <div class="si"><span class="sv">{{ summaryStats.totalTasks }}</span><span class="sl">总任务数</span></div>
        <div class="si"><span class="sv done">{{ summaryStats.doneTasks }}</span><span class="sl">已完成</span></div>
        <div class="si"><span class="sv" :class="{ warn: summaryStats.overallRate < 50 }">{{ summaryStats.overallRate }}%</span><span class="sl">完成率</span></div>
      </div>
      <div v-if="canManageProgress" class="summary-progress-action">
        <el-button type="primary" @click="openProgressImport">进展更新</el-button>
      </div>
      <div class="summary-actions">
        <el-switch v-model="showArchived" active-text="含归档" @change="onArchivedChange" />
        <el-button v-if="canViewInspectionReport" type="info" plain @click="openDailyBrief()">巡检报告</el-button>
        <el-button v-if="canCreateProject" type="primary" @click="openCreateProjectDialog">新建项目</el-button>
      </div>
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
            <el-progress :percentage="projectProgress(project)" :stroke-width="8" :color="projectProgressColor(project)" style="width:100%" />
            <span class="ptxt">{{ project.completed_count }}/{{ project.task_count }}</span>
          </div>
          <div class="col-sd">{{ formatDate(project.start_date) }}</div>
          <div class="col-ed">{{ formatDate(project.end_date) }}</div>
          <div class="col-act center" @click.stop>
            <el-button type="info" link size="small" @click="openProjectDetail(project)">详情</el-button>
            <el-button type="primary" link size="small" @click="goToBoard(project.id)">看板</el-button>
            <el-button v-if="canUseAiRisk" type="warning" link size="small" @click="openRetrospective(project)">复盘</el-button>
            <el-button v-if="canCreateTask && project.status !== 'archived'" type="primary" link size="small" @click="openRootTaskDialog(project)">添加任务</el-button>
            <el-popconfirm v-if="project.status !== 'archived' && canArchiveProject" title="归档后不计入统计，确认？" @confirm="archiveProject(project.id)">
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
              <div class="col-fb">进展记录</div>
              <div class="col-who">负责人</div>
              <div class="col-hrs center">工时(h)</div>
              <div class="col-prog">进度</div>
              <div class="col-sd">开始日期</div>
              <div class="col-ed">截止日期</div>
              <div class="col-act center">状态 / 操作</div>
            </div>

            <draggable
              :model-value="visibleTaskRows(project.id)"
              item-key="id"
              tag="div"
              class="task-drag-list"
              ghost-class="ghost-row"
              handle=".task-drag-handle"
              :animation="160"
              :disabled="!canEditTask"
              :move="canMoveTaskRow"
              @start="(evt: any) => handleTaskRowDragStart(project.id, evt)"
              @end="(evt: any) => handleTaskRowDragEnd(project.id, evt)"
            >
              <template #item="{ element: task }">
            <div class="trow" :class="['d' + task._depth, { tdel: task.is_deleted }]">
              <div class="col-exp task-tools">
                <button
                  v-if="canEditTask && !task.is_deleted"
                  type="button"
                  class="task-drag-handle"
                  title="拖拽排序"
                  aria-label="拖拽排序"
                  @click.stop
                >
                  <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
                    <path d="M5 3h2v2H5V3Zm4 0h2v2H9V3ZM5 7h2v2H5V7Zm4 0h2v2H9V7Zm-4 4h2v2H5v-2Zm4 0h2v2H9v-2Z" fill="currentColor"/>
                  </svg>
                </button>
                <span v-else class="task-drag-spacer"></span>
                <button
                  v-if="taskHasChildren(project.id, task)"
                  type="button"
                  class="task-collapse-toggle"
                  :class="{ collapsed: isTaskCollapsed(project.id, task) }"
                  :title="isTaskCollapsed(project.id, task) ? '展开子任务' : '折叠子任务'"
                  :aria-label="isTaskCollapsed(project.id, task) ? '展开子任务' : '折叠子任务'"
                  @click.stop="toggleTaskCollapse(project.id, task)"
                >
                  <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
                    <path d="M4 6l4 4 4-4H4z" fill="currentColor"/>
                  </svg>
                </button>
                <span v-else class="task-collapse-spacer"></span>
              </div>
              <div class="col-name task-name-cell" :style="taskNameIndentStyle(task)">
                <span v-if="task._depth > 0" class="task-branch" aria-hidden="true"></span>
                <button type="button" class="task-link" @click.stop="openTaskDetail(task, project.id)">
                  <span class="tname">{{ task.title }}</span>
                </button>
                <el-tag v-if="task.priority === 'urgent'" type="danger" size="small" style="margin-left:4px">紧急</el-tag>
                <el-tag v-else-if="task.priority === 'high'" type="danger" size="small" effect="plain" style="margin-left:4px">高</el-tag>
                <span v-if="task._depth === 0 && task.subtask_total > 0" class="sbadge">{{ task.subtask_done }}/{{ task.subtask_total }}</span>
              </div>
              <!-- Progress History Column -->
              <div class="col-fb" @click.stop>
                <span class="fb-text" @click="openFeedback(task, project.id)" :title="task.latest_note || '查看进展记录'">
                  {{ task.latest_note || '查看记录' }}
                </span>
              </div>
              <!-- Assignee -->
              <div class="col-who" @click.stop>
                <template v-if="canAssignTask && !task.is_deleted">
                  <el-select :model-value="task.assignee_ids || []" size="small" placeholder="未分配" clearable filterable multiple class="isel" @change="(v: string[]) => handleAssigneeChange(task, v)">
                    <el-option v-for="u in users" :key="u.id" :label="u.full_name" :value="u.id" />
                  </el-select>
                </template>
                <span v-else class="who-text">{{ task.assignee_name || '未分配' }}</span>
              </div>
              <!-- Hours -->
              <div class="col-hrs center" @click.stop>
                <el-popover v-if="canSetTaskHours && !task.is_deleted" trigger="click" :width="160" placement="bottom">
                  <template #reference><span class="dt-click">{{ task.estimated_hours ?? '-' }}</span></template>
                  <el-input-number :model-value="task.estimated_hours" size="small" :min="0" :max="999" :precision="1" style="width:100%" @change="(v: number) => handleFieldUpdate(task, 'estimated_hours', v)" />
                </el-popover>
                <span v-else>{{ task.estimated_hours ?? '-' }}</span>
              </div>
              <!-- Progress bar -->
              <div class="col-prog">
                <el-progress :percentage="task.progress_pct ?? (task.status === 'done' ? 100 : 0)" :stroke-width="6" :color="taskProgressColor(task)" style="width:100%" />
              </div>
              <!-- Start Date -->
              <div class="col-sd" @click.stop>
                <el-popover v-if="canSetTaskDeadline && !task.is_deleted" trigger="click" :width="240" placement="bottom" :hide-after="0">
                  <template #reference><span class="dt-click">{{ formatDate(task.start_date || task.created_at) }}</span></template>
                  <div class="date-popover-body" @click.stop>
                    <el-date-picker :model-value="(task.start_date || task.created_at || '').slice(0, 10)" type="date" size="small" value-format="YYYY-MM-DD" style="width:100%" :teleported="false" @update:model-value="(v: string) => handleFieldUpdate(task, 'start_date', v)" />
                  </div>
                </el-popover>
                <span v-else>{{ formatDate(task.start_date || task.created_at) }}</span>
              </div>
              <!-- End Date -->
              <div class="col-ed" @click.stop>
                <el-popover v-if="canSetTaskDeadline && !task.is_deleted" trigger="click" :width="240" placement="bottom" :hide-after="0">
                  <template #reference><span class="dt-click" :class="{ ovd: task.is_overdue }">{{ formatDate(task.deadline) || '-' }}</span></template>
                  <div class="date-popover-body" @click.stop>
                    <el-date-picker :model-value="task.deadline ? task.deadline.slice(0, 10) : ''" type="date" size="small" value-format="YYYY-MM-DD" style="width:100%" :teleported="false" @update:model-value="(v: string) => handleFieldUpdate(task, 'deadline', v)" />
                  </div>
                </el-popover>
                <span v-else :class="{ ovd: task.is_overdue }">{{ formatDate(task.deadline) }}</span>
              </div>
              <!-- Status + Actions -->
              <div class="col-act center" @click.stop>
                <el-tag :type="(taskDisplayStatusType(task) as any)" size="small">{{ taskDisplayStatusLabel(task) }}</el-tag>
                <el-button
                  v-if="canSignoffTask && taskNeedsSignoff(task) && !task.is_deleted"
                  type="success"
                  link
                  size="small"
                  @click="handleSignoff(task, project.id)"
                >
                  会签确认
                </el-button>
                <el-button v-if="canCreateTask && !task.is_deleted" type="primary" link size="small" @click="openSubtaskDialog(task, project.id)">添加</el-button>
                <el-popconfirm v-if="canDeleteTask && !task.is_deleted" title="标记删除？不计入统计" @confirm="handleDelete(task)">
                  <template #reference><el-button type="danger" link size="small">删除</el-button></template>
                </el-popconfirm>
                <el-button
                  v-if="canDeleteTask && canRestoreTask(task, project.id)"
                  type="success"
                  link
                  size="small"
                  @click="handleRestore(task, project.id)"
                >
                  恢复
                </el-button>
              </div>
            </div>
              </template>
            </draggable>
          </template>
          <div v-else class="tloading">
            暂无任务
            <el-button v-if="canCreateTask && project.status !== 'archived'" type="primary" link size="small" @click="openRootTaskDialog(project)">添加任务</el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- Create Project Dialog -->
    <el-dialog v-model="createDialogVisible" title="新建项目" :width="canUseAiEstimate ? '880px' : '520px'" :close-on-click-modal="false">
      <el-form label-width="80px">
        <el-form-item label="项目名称"><el-input v-model="createForm.name" placeholder="请输入项目名称" /></el-form-item>
        <el-form-item label="项目目标"><el-input v-model="createForm.goal" type="textarea" :rows="2" placeholder="请输入项目目标" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="createForm.description" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="开始日期"><el-date-picker v-model="createForm.start_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
        <el-form-item label="截止日期"><el-date-picker v-model="createForm.end_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
        <template v-if="canUseAiEstimate">
          <el-divider content-position="left">AI 创建</el-divider>
          <el-form-item label="项目目标">
            <el-input
              v-model="projectPlanPrompt"
              type="textarea"
              :rows="4"
              placeholder="项目目标、周期、交付物、约束条件"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="warning" :loading="projectPlanLoading" :disabled="!projectPlanPrompt.trim()" @click="previewProjectPlan">生成计划</el-button>
            <span v-if="projectPlanStatus" class="ai-st">{{ projectPlanStatus }}</span>
          </el-form-item>
        </template>
      </el-form>

      <div v-if="projectPlanPreview" class="ai-result">
        <div class="ai-result-title">{{ projectPlanPreview.project?.name || 'AI 项目计划' }}</div>
        <p class="ai-result-summary">{{ projectPlanPreview.project?.goal || '暂无项目目标' }}</p>
        <p class="ai-result-summary">{{ projectPlanPreview.project?.description }}</p>
        <div class="ai-result-meta">
          {{ projectPlanPreview.project?.start_date || '-' }} 至 {{ projectPlanPreview.project?.end_date || '-' }}
        </div>
        <el-table :data="projectPlanPreview.tasks || []" size="small" border style="width:100%;margin-top:10px">
          <el-table-column prop="title" label="任务" min-width="180" show-overflow-tooltip />
          <el-table-column prop="assignee_name" label="建议负责人" width="110" show-overflow-tooltip />
          <el-table-column prop="priority" label="优先级" width="90" />
          <el-table-column prop="estimated_hours" label="工时" width="80" />
          <el-table-column prop="deadline" label="截止" width="110" />
          <el-table-column label="子任务" width="80" align="center">
            <template #default="{ row }">{{ asList(row.children).length }}</template>
          </el-table-column>
        </el-table>
      </div>

      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建项目</el-button>
        <el-button
          v-if="canUseAiEstimate"
          type="warning"
          :loading="projectPlanSubmitting"
          :disabled="!projectPlanPreview"
          @click="commitProjectPlan"
        >
          确认 AI 创建
        </el-button>
      </template>
    </el-dialog>

    <!-- Inspection Report Dialog -->
    <el-dialog v-model="dailyBriefDialogVisible" title="巡检报告" width="860px">
      <div class="report-toolbar">
        <el-radio-group :model-value="reportType" size="small" @change="changeReportType">
          <el-radio-button value="daily">日报</el-radio-button>
          <el-radio-button value="weekly">周报</el-radio-button>
        </el-radio-group>
        <el-input
          v-model="reportRecipients"
          class="report-recipient-input"
          placeholder="接收人邮箱，多个用逗号分隔；留空使用默认接收人"
          clearable
        />
        <div class="report-actions">
          <el-button plain :loading="dailyBriefLoading" :disabled="reportSending" @click="refreshInspectionReport()">刷新</el-button>
          <el-button type="primary" :loading="reportSending" :disabled="dailyBriefLoading" @click="sendInspectionReport">邮件发送</el-button>
        </div>
      </div>
      <div v-loading="dailyBriefLoading" class="ai-result">
        <span v-if="dailyBriefStatus" class="ai-st">{{ dailyBriefStatus }}</span>
        <template v-if="dailyBriefResult">
          <div class="ai-result-head">
            <div class="ai-result-title">{{ reportType === 'weekly' ? '本周摘要' : '今日摘要' }}</div>
            <el-tag
              size="small"
              :type="dailyBriefResult.source === 'ai' ? 'success' : 'warning'"
              effect="plain"
            >
              {{ dailyBriefResult.source_label || (dailyBriefResult.source === 'ai' ? 'AI 生成' : '系统规则巡检') }}
            </el-tag>
            <span v-if="reportGeneratedAt" class="report-generated-at">更新时间：{{ formatDateTime(reportGeneratedAt) }}</span>
          </div>
          <p class="ai-result-summary">{{ dailyBriefResult.summary }}</p>
          <div v-if="reportType === 'weekly' && asList(dailyBriefResult.project_progress_table).length" class="ai-section">
            <h4>项目进展情况表</h4>
            <el-table :data="dailyBriefResult.project_progress_table" size="small" border class="report-project-table">
              <el-table-column prop="project_name" label="项目" min-width="160" show-overflow-tooltip />
              <el-table-column prop="progress_pct" label="总进度" width="86" align="center">
                <template #default="{ row }">{{ row.progress_pct }}%</template>
              </el-table-column>
              <el-table-column prop="weekly_progress" label="本周进展" width="110" />
              <el-table-column prop="task_completion" label="任务完成" width="96" align="center" />
              <el-table-column prop="overdue_tasks" label="逾期" width="70" align="center" />
              <el-table-column prop="risk_level" label="风险" width="70" align="center" />
              <el-table-column prop="next_action" label="下周建议" min-width="220" show-overflow-tooltip />
            </el-table>
          </div>
          <div class="ai-section" v-for="section in reportSectionKeys" :key="section">
            <h4>{{ dailySectionLabel(section) }}</h4>
            <ul>
              <li v-for="(item, idx) in asList(dailyBriefResult[section])" :key="idx">{{ typeof item === 'string' ? item : JSON.stringify(item) }}</li>
            </ul>
          </div>
        </template>
        <el-empty
          v-else-if="!dailyBriefLoading && !dailyBriefStatus"
          description="暂无巡检报告，请点击刷新生成"
          :image-size="72"
        />
      </div>
    </el-dialog>

    <!-- Add Subtask Dialog -->
    <el-dialog
      v-model="subtaskDialogVisible"
      :title="(subtaskParent?.id ? '添加子任务 — ' : '添加任务 — ') + (subtaskParent?.title || '')"
      width="640px"
      class="task-create-dialog"
    >
      <el-form label-width="88px" class="task-create-form">
        <el-form-item label="任务标题"><el-input v-model="subtaskForm.title" /></el-form-item>
        <el-form-item label="任务目标"><el-input v-model="subtaskForm.goal" type="textarea" :rows="2" placeholder="可选，说明任务要达到的结果" /></el-form-item>
        <el-form-item label="任务描述"><el-input v-model="subtaskForm.description" type="textarea" :rows="2" placeholder="可选，有助 AI 更准推荐" /></el-form-item>
        <el-form-item>
          <div class="ai-row">
            <el-button v-if="canUseAiEstimate" type="warning" :loading="aiEstimating" @click="handleAiEstimate" :disabled="!subtaskForm.title.trim()">AI 推荐人选 + 预估工时</el-button>
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
        <el-form-item label="负责人" class="assignee-form-item">
          <el-select
            v-model="subtaskForm.assignee_ids"
            placeholder="选择负责人"
            clearable
            filterable
            multiple
            :teleported="false"
            popper-class="task-create-assignee-popper"
            class="full-assignee-select"
          >
            <el-option v-for="u in users" :key="u.id" :label="u.full_name" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="预估工时"><el-input-number v-model="subtaskForm.estimated_hours" :min="0" :max="999" :precision="1" style="width:100%" /></el-form-item>
        <el-form-item label="截止日期"><el-date-picker v-model="subtaskForm.deadline" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="subtaskDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creatingSubtask" @click="handleCreateSubtask">创建</el-button>
      </template>
    </el-dialog>

    <!-- Group Progress Import Dialog -->
    <el-dialog v-model="progressImportDialogVisible" title="进展更新" width="900px" :close-on-click-modal="false">
      <el-form label-width="80px">
        <el-form-item label="群消息">
          <el-input
            v-model="progressImportText"
            type="textarea"
            :rows="8"
            placeholder="粘贴格式：姓名&#10;时间&#10;任务进展。一个人的多条任务进展可以放在同一段。"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="warning" :loading="progressImportLoading" :disabled="!progressImportText.trim()" @click="previewProgressImport">AI 识别进展</el-button>
          <span v-if="progressImportStatus" class="ai-st">{{ progressImportStatus }}</span>
        </el-form-item>
      </el-form>

      <div v-if="progressImportPreview.length" class="import-preview">
        <div class="import-title">识别结果</div>
        <el-table :data="progressImportPreview" size="small" border style="width:100%">
          <el-table-column width="48" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.selected" />
            </template>
          </el-table-column>
          <el-table-column prop="person_name" label="姓名" width="90" />
          <el-table-column prop="reported_at" label="时间" width="130" show-overflow-tooltip />
          <el-table-column prop="project_name" label="匹配项目" width="140" show-overflow-tooltip />
          <el-table-column prop="task_title" label="匹配任务" min-width="180" show-overflow-tooltip />
          <el-table-column label="进度" width="150">
            <template #default="{ row }">
              <el-input-number v-model="row.progress_pct" :min="0" :max="100" size="small" style="width:110px" />
            </template>
          </el-table-column>
          <el-table-column prop="note" label="进展说明" min-width="220" show-overflow-tooltip />
          <el-table-column label="置信度" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="row.confidence >= 80 ? 'success' : row.confidence >= 50 ? 'warning' : 'info'" size="small">{{ row.confidence || 0 }}%</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <el-alert
        v-if="progressImportUnmatched.length"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top:12px"
      >
        <template #title>
          有 {{ progressImportUnmatched.length }} 段进展未能可靠匹配，请确认原文或手动录入。
        </template>
      </el-alert>

      <template #footer>
        <el-button @click="progressImportDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="progressImportSubmitting" :disabled="!progressImportPreview.some((i: any) => i.selected)" @click="commitProgressImport">确认同步</el-button>
      </template>
    </el-dialog>

    <!-- Project Retrospective Dialog -->
    <el-dialog v-model="retrospectiveDialogVisible" :title="'项目复盘 - ' + (retrospectiveProject?.name || '')" width="760px">
      <div v-loading="retrospectiveLoading" class="ai-result">
        <span v-if="retrospectiveStatus" class="ai-st">{{ retrospectiveStatus }}</span>
        <template v-if="retrospectiveResult">
          <div class="ai-result-title">复盘摘要</div>
          <p class="ai-result-summary">{{ retrospectiveResult.summary }}</p>
          <div class="ai-section" v-for="section in ['wins','issues','estimation_lessons','process_improvements','reusable_template']" :key="section">
            <h4>{{ retrospectiveSectionLabel(section) }}</h4>
            <ul>
              <li v-for="(item, idx) in asList(retrospectiveResult[section])" :key="idx">{{ typeof item === 'string' ? item : JSON.stringify(item) }}</li>
            </ul>
          </div>
        </template>
      </div>
    </el-dialog>

    <el-drawer v-model="taskDetailVisible" :title="'任务详情 — ' + (taskDetail?.title || '')" size="560px" direction="rtl">
      <div v-if="taskDetail" class="task-detail-drawer">
        <el-alert
          v-if="taskDetail.is_deleted"
          type="warning"
          :closable="false"
          show-icon
          title="任务当前处于删除状态。"
          style="margin-bottom: 12px"
        />
        <div class="detail-section">
          <div class="detail-section-head">
            <h4>任务信息</h4>
            <el-button
              v-if="canEditTask && !taskDetail.is_deleted"
              type="primary"
              size="small"
              :loading="taskDetailSaving"
              @click="saveTaskDetail"
            >
              保存
            </el-button>
          </div>
          <el-form v-if="canEditTask && !taskDetail.is_deleted" label-width="72px" class="task-detail-edit-form">
            <el-form-item label="任务名称">
              <el-input v-model="taskDetailForm.title" maxlength="300" show-word-limit />
            </el-form-item>
            <el-form-item label="任务目标">
              <el-input
                v-model="taskDetailForm.goal"
                type="textarea"
                :rows="4"
                placeholder="说明这项任务要达成的结果"
              />
            </el-form-item>
            <el-form-item label="任务描述">
              <el-input
                v-model="taskDetailForm.description"
                type="textarea"
                :rows="5"
                placeholder="补充背景、约束和执行要求"
              />
            </el-form-item>
          </el-form>
          <template v-else>
            <h4 class="detail-subtitle">任务名称</h4>
            <p class="task-description">{{ taskDetail.title }}</p>
            <h4 class="detail-subtitle">任务目标</h4>
            <p class="task-detail-goal">{{ taskDetail.goal || '暂无任务目标' }}</p>
            <h4 class="detail-subtitle">任务描述</h4>
            <p class="task-description">{{ taskDetail.description || '暂无任务描述' }}</p>
          </template>
        </div>
        <div class="detail-section">
          <h4>基本信息</h4>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="状态">
              <el-tag :type="(taskDisplayStatusType(taskDetail) as any)" size="small">{{ taskDisplayStatusLabel(taskDetail) }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="负责人">
              {{ taskDetail.assignee_names?.join('、') || taskDetail.assignee_name || '未分配' }}
            </el-descriptions-item>
            <el-descriptions-item label="当前进度">
              <el-progress :percentage="taskDetail.progress_pct ?? 0" :stroke-width="8" />
            </el-descriptions-item>
            <el-descriptions-item label="开始日期">
              {{ formatDate(taskDetail.start_date || taskDetail.created_at) }}
            </el-descriptions-item>
            <el-descriptions-item label="截止日期">
              {{ formatDate(taskDetail.deadline) }}
            </el-descriptions-item>
            <el-descriptions-item label="预估工时">
              {{ taskDetail.estimated_hours ?? '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="最后更新时间">
              {{ formatDateTime(taskDetail.updated_at || taskDetail.created_at) }}
            </el-descriptions-item>
          </el-descriptions>
        </div>
        <div class="detail-section">
          <h4>数据 Skill</h4>
          <TaskDataSkillPanel
            :task="taskDetail"
            :can-manage-progress="canManageProgress"
            @progress-adopted="handleTaskDetailDataSkillAdopted"
          />
        </div>
      </div>
    </el-drawer>

    <el-drawer v-model="projectDetailVisible" :title="'项目详情 — ' + (projectDetail?.name || '')" size="520px" direction="rtl">
      <div v-loading="projectDetailLoading" class="project-detail-drawer">
        <template v-if="projectDetail">
          <div class="detail-section">
            <h4>项目目标</h4>
            <el-input
              v-model="projectDetailForm.goal"
              type="textarea"
              :rows="4"
              :disabled="!canEditProject"
              placeholder="暂无项目目标"
            />
          </div>
          <div class="detail-section">
            <h4>项目描述</h4>
            <el-input
              v-model="projectDetailForm.description"
              type="textarea"
              :rows="6"
              :disabled="!canEditProject"
              placeholder="暂无项目描述"
            />
          </div>
          <div class="detail-section">
            <h4>基本信息</h4>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="状态">
                <el-tag :type="(statusType(projectDetail.status) as any)" size="small">{{ statusLabel(projectDetail.status) }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="成员数">{{ projectDetail.member_count }}</el-descriptions-item>
              <el-descriptions-item label="任务数">{{ projectDetail.task_count }}</el-descriptions-item>
              <el-descriptions-item label="已完成">{{ projectDetail.completed_count }}</el-descriptions-item>
              <el-descriptions-item label="开始日期">{{ formatDate(projectDetail.start_date) }}</el-descriptions-item>
              <el-descriptions-item label="截止日期">{{ formatDate(projectDetail.end_date) }}</el-descriptions-item>
              <el-descriptions-item label="创建时间">{{ formatDateTime(projectDetail.created_at) }}</el-descriptions-item>
            </el-descriptions>
          </div>
          <div v-if="canEditProject" class="project-detail-actions">
            <el-button type="primary" :loading="projectDetailSaving" @click="saveProjectDetail">保存</el-button>
          </div>
        </template>
      </div>
    </el-drawer>

    <!-- Progress History Drawer -->
    <el-drawer v-model="feedbackDialogVisible" :title="'任务进展 — ' + (feedbackTask?.title || '')" size="420px" direction="rtl">
      <div v-if="feedbackTask" class="fb-drawer">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="支持手动补充真实进展；顶部进展更新适合批量导入群消息。"
          style="margin-bottom: 16px"
        />
        <div v-if="canManageProgress && !feedbackTask.is_deleted" class="fb-form">
          <h4>手动提交</h4>
          <el-form label-width="74px" size="small">
            <el-form-item label="进度 (%)">
              <el-slider v-model="feedbackForm.progress_pct" :min="0" :max="100" :step="5" show-input />
            </el-form-item>
            <el-form-item label="投入工时">
              <el-input-number v-model="feedbackForm.hours_spent" :min="0" :max="999" :precision="1" style="width: 100%" />
            </el-form-item>
            <el-form-item label="进展说明">
              <el-input
                v-model="feedbackForm.note"
                type="textarea"
                :rows="3"
                placeholder="填写当前真实进展、风险、阻塞或结果"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="feedbackSubmitting" @click="submitFeedback">提交进展</el-button>
            </el-form-item>
          </el-form>
        </div>
        <el-alert
          v-if="feedbackTask.is_deleted"
          type="warning"
          :closable="false"
          show-icon
          title="任务已删除，当前只保留历史记录。"
          style="margin-bottom: 16px"
        />
        <el-alert
          v-else-if="!canManageProgress"
          type="warning"
          :closable="false"
          show-icon
          title="当前账号没有手动提交进展的权限。"
          style="margin-bottom: 16px"
        />
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
.summary-bar { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; padding: 14px 20px; background: #fff; border-radius: 8px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.summary-stats { display: flex; align-items: center; gap: 24px; flex: 0 0 auto; }
.summary-progress-action { display: flex; align-items: center; flex: 0 0 auto; padding-left: 2px; }
.summary-actions { margin-left: auto; display: flex; align-items: center; justify-content: flex-end; gap: 10px; flex-wrap: wrap; }
.si { display: flex; flex-direction: column; align-items: center; }
.sv { font-size: 22px; font-weight: 700; color: #303133; }
.sv.active { color: #409EFF; } .sv.done { color: #67C23A; } .sv.warn { color: #E6A23C; }
.sl { font-size: 11px; color: #909399; margin-top: 2px; }

.ptree { display: flex; flex-direction: column; gap: 2px; }
.pblock { background: #fff; border-radius: 6px; overflow-x: auto; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }

/* Grid: 9 columns, auto-fill width */
.prow, .trow, .thead {
  display: grid;
  grid-template-columns: 64px 3fr 2fr 1.2fr 0.7fr 1.2fr 1.2fr 1.2fr 2fr;
  align-items: center; padding: 0 8px; min-height: 40px; gap: 2px;
  border-left: 4px solid transparent;
  box-sizing: border-box;
}
.prow { background: #fafbfc; border-left-color: #409EFF; cursor: pointer; min-height: 48px; }
.prow:hover { background: #f0f5ff; }
.pn strong { font-size: 13px; }
.thead { background: #f5f7fa; font-size: 11px; color: #909399; font-weight: 600; min-height: 30px; border-bottom: 1px solid #ebeef5; }
.trow { border-bottom: 1px solid #f2f3f5; font-size: 12px; min-height: 40px; padding-top: 3px; padding-bottom: 3px; }
.trow:last-child { border-bottom: none; }
.d0 { background: #fff; } .d1 { background: #fafbfc; } .d2 { background: #f5f7fa; }

.col-exp { display: flex; justify-content: center; align-items: center; gap: 4px; color: #909399; }
.ei { transition: transform 0.2s; } .ei.rot { transform: rotate(90deg); }
.sbadge { flex: 0 0 auto; font-size: 10px; color: #409EFF; background: #ecf5ff; padding: 1px 5px; border-radius: 8px; white-space: nowrap; }
.task-drag-list { display: block; }
.task-tools { justify-content: flex-start; padding-left: 4px; box-sizing: border-box; }
.task-drag-handle {
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: #a8abb2;
  cursor: grab;
}
.task-drag-handle:hover { background: #ecf5ff; color: #409EFF; }
.task-drag-handle:active { cursor: grabbing; }
.task-drag-spacer,
.task-collapse-spacer,
.task-collapse-toggle {
  width: 22px;
  height: 22px;
  flex: 0 0 22px;
}
.task-collapse-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: #909399;
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease, transform 0.15s ease;
}
.task-collapse-toggle:hover { background: #ecf5ff; color: #409EFF; }
.task-collapse-toggle.collapsed svg { transform: rotate(-90deg); }
.task-collapse-toggle svg { transition: transform 0.15s ease; }
.ghost-row { opacity: 0.48; background: #ecf5ff !important; }

.col-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.task-name-cell {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 4px;
  padding-left: calc(var(--task-depth) * 22px + 4px);
  box-sizing: border-box;
}
.task-branch {
  position: relative;
  width: 14px;
  height: 20px;
  flex: 0 0 14px;
}
.task-branch::before {
  content: "";
  position: absolute;
  left: 4px;
  top: 0;
  width: 9px;
  height: 10px;
  border-left: 1px solid #dcdfe6;
  border-bottom: 1px solid #dcdfe6;
}
.tname {
  display: inline-block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-link {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  max-width: 100%;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
}
.task-link:hover .tname { color: #409EFF; text-decoration: underline; }

.col-fb { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fb-text { font-size: 11px; color: #909399; cursor: pointer; padding: 2px 4px; border-radius: 3px; }
.fb-text:hover { background: #ecf5ff; color: #409EFF; }

.col-who { font-size: 11px; color: #606266; min-width: 0; }
.who-text { white-space: normal; line-height: 1.4; }

.col-hrs { font-size: 11px; color: #606266; }
.col-hrs.center { text-align: center; }
.col-prog { display: flex; align-items: center; }
.ptxt { font-size: 10px; color: #909399; white-space: nowrap; margin-left: 4px; }
.col-sd, .col-ed { font-size: 11px; color: #909399; }
.col-act { font-size: 11px; }
.col-act.center { text-align: center; display: flex; align-items: center; justify-content: center; gap: 2px; white-space: nowrap; flex-wrap: nowrap; }
.ovd { color: #F56C6C !important; font-weight: 600; }

/* Inline controls */
.isel { width: 100%; }
.isel :deep(.el-select__wrapper),
.isel :deep(.el-input__wrapper) { box-shadow: none !important; background: transparent; padding: 2px; min-height: 28px; align-items: flex-start; }
.isel :deep(.el-select__wrapper:hover),
.isel :deep(.el-input__wrapper:hover) { box-shadow: 0 0 0 1px #dcdfe6 inset !important; }
.isel :deep(.el-select__selection) { flex-wrap: wrap; align-items: center; gap: 2px; min-width: 0; }
.isel :deep(.el-tag) { height: auto; min-height: 20px; margin: 1px 0; white-space: normal; max-width: 100%; }
.isel :deep(.el-input__inner) { font-size: 11px; }
.ist { width: 82px; }
/* Clickable text for inline edit */
.dt-click { cursor: pointer; padding: 2px 4px; border-radius: 3px; border-bottom: 1px dashed #c0c4cc; }
.dt-click:hover { background: #ecf5ff; color: #409EFF; border-bottom-color: #409EFF; }
.date-popover-body { width: 220px; }

/* Deleted */
.tdel { opacity: 0.75; }
.tdel .tname { text-decoration: line-through; }
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

.import-preview { margin-top: 8px; }
.import-title { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 8px; }
.ai-result { min-height: 80px; }
.ai-result-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.ai-result-title { font-size: 15px; font-weight: 700; color: #303133; margin-bottom: 8px; }
.ai-result-head .ai-result-title { margin-bottom: 0; }
.ai-result-summary { margin: 0 0 8px; font-size: 13px; line-height: 1.6; color: #606266; white-space: pre-wrap; }
.ai-result-meta { font-size: 12px; color: #909399; }
.ai-section { margin-top: 14px; }
.ai-section h4 { margin: 0 0 6px; font-size: 13px; color: #303133; }
.ai-section ul { margin: 0; padding-left: 18px; color: #606266; font-size: 13px; line-height: 1.6; }
.report-toolbar {
  display: grid;
  grid-template-columns: auto minmax(260px, 1fr) auto;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.report-recipient-input { min-width: 0; }
.report-generated-at {
  font-size: 12px;
  color: #909399;
}
.report-project-table { width: 100%; }
.report-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  white-space: nowrap;
}
@media (max-width: 760px) {
  .report-toolbar { grid-template-columns: 1fr; align-items: stretch; }
  .report-actions { justify-content: stretch; }
  .report-actions :deep(.el-button) { flex: 1; }
}

.task-create-dialog :deep(.el-dialog__body) {
  overflow: visible;
}

.task-create-form :deep(.el-form-item) {
  align-items: flex-start;
}

.task-create-form :deep(.el-form-item__label) {
  min-height: 32px;
  line-height: 32px;
}

.assignee-form-item :deep(.el-form-item__content) {
  min-width: 0;
  align-items: flex-start;
}

.full-assignee-select {
  width: 100%;
}

.full-assignee-select :deep(.el-select__wrapper) {
  min-height: 32px;
  width: 100%;
  align-items: center;
  padding-top: 1px;
  padding-bottom: 1px;
  box-sizing: border-box;
}

.full-assignee-select :deep(.el-select__selection) {
  flex: 1;
  min-width: 0;
  min-height: 24px;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}

.full-assignee-select :deep(.el-select__input-wrapper) {
  min-width: 96px;
  height: 24px;
  line-height: 24px;
}

.full-assignee-select :deep(.el-select__placeholder) {
  height: 24px;
  line-height: 24px;
  display: inline-flex;
  align-items: center;
}

.full-assignee-select :deep(.el-tag) {
  height: auto;
  min-height: 24px;
  margin: 2px 0;
  white-space: normal;
}

:global(.task-create-assignee-popper) {
  max-width: 520px;
}

:global(.task-create-assignee-popper .el-select-dropdown__wrap) {
  max-height: 168px;
}

.project-detail-drawer,
.task-detail-drawer { padding: 0 4px; }
.detail-section { margin-bottom: 16px; }
.detail-section-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.detail-section-head h4 { margin: 0; }
.detail-subtitle { margin: 12px 0 6px; font-size: 13px; color: #303133; }
.project-detail-actions { display: flex; justify-content: flex-end; margin-top: 8px; }
.task-detail-edit-form :deep(.el-form-item:last-child) { margin-bottom: 0; }
.task-detail-goal, .task-description {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: #606266;
  white-space: pre-wrap;
}

/* Feedback drawer */
.fb-drawer { padding: 0 4px; }
.fb-form { margin-bottom: 20px; }
.fb-form h4, .fb-history h4 { font-size: 14px; font-weight: 600; margin: 0 0 10px 0; color: #303133; }
.fb-log { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.fb-user { font-weight: 500; color: #409EFF; }
.fb-hrs { color: #909399; }
.fb-note { margin: 4px 0 0; font-size: 12px; color: #606266; line-height: 1.5; }
</style>
