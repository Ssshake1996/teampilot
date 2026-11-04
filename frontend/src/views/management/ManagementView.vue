<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { projectsApi } from '@/api/projects'
import { usersApi } from '@/api/users'
import { managementApi } from '@/api/management'
import { fetchAllPages } from '@/utils/pagination'
import { calendarMonday, managementError } from '@/utils/management'
import type { Project, User } from '@/types/models'
import type { ManagedTask, ProjectAccess } from '@/types/management'
import TaskManagementPanel from '@/components/management/TaskManagementPanel.vue'
import CapacityPanel from '@/components/management/CapacityPanel.vue'
import ProjectPlanPanel from '@/components/management/ProjectPlanPanel.vue'
import WeeklyReviewPanel from '@/components/management/WeeklyReviewPanel.vue'
import ReportHistoryPanel from '@/components/management/ReportHistoryPanel.vue'

const route = useRoute()
const router = useRouter()
const projects = ref<Project[]>([])
const users = ref<User[]>([])
const tasks = ref<ManagedTask[]>([])
const projectId = ref(typeof route.query.project_id === 'string' ? route.query.project_id : '')
const tabNames = ['tasks', 'capacity', 'plan', 'weekly', 'reports']
const tab = ref(typeof route.query.tab === 'string' && tabNames.includes(route.query.tab) ? route.query.tab : 'tasks')
const week = ref(calendarMonday())
const access = ref<ProjectAccess | null>(null)
const loading = ref(false)
const accessSaving = ref(false)
const transferVisible = ref(false)
const transferSaving = ref(false)
const transferOwnerId = ref('')
const transferError = ref('')
const error = ref('')
let generation = 0
let loadedProjectId = ''
const project = computed(() => projects.value.find(item => item.id === projectId.value))
function normalizeWeek(value: string) { week.value = calendarMonday(new Date(`${value}T12:00:00`)) }

async function loadProject() {
  const request = ++generation
  if (loadedProjectId !== projectId.value) { tasks.value = []; access.value = null }
  error.value = ''
  if (!projectId.value) return
  loading.value = true
  try {
    const [taskResponse, accessResponse] = await Promise.all([managementApi.tasks(projectId.value), managementApi.access(projectId.value)])
    if (request !== generation) return
    tasks.value = taskResponse.data; access.value = accessResponse.data; loadedProjectId = projectId.value
  } catch (err) { if (request === generation) error.value = managementError(err, '项目管理数据加载失败，请重试。') }
  finally { if (request === generation) loading.value = false }
}
async function load() {
  loading.value = true; error.value = ''
  try {
    const [projectRows, userRows] = await Promise.all([
      fetchAllPages(page => projectsApi.list(page, 100)),
      fetchAllPages(page => usersApi.list(page, 100)),
    ])
    projects.value = projectRows; users.value = userRows.filter(item => item.is_active)
    if (!projectRows.some(item => item.id === projectId.value)) projectId.value = projectRows[0]?.id || ''
    await loadProject()
  } catch (err) { error.value = managementError(err, '团队协作数据加载失败，请重试。') }
  finally { loading.value = false }
}
async function saveAccess(value: ProjectAccess['visibility']) {
  if (!access.value || accessSaving.value) return
  const targetProject = projectId.value
  accessSaving.value = true
  try { const response = await managementApi.saveAccess(targetProject, value); if (targetProject === projectId.value) access.value = response.data; ElMessage.success('项目访问范围已保存') }
  catch (err) { ElMessage.error(managementError(err)) }
  finally { accessSaving.value = false }
}
function openTransfer() {
  transferOwnerId.value = ''; transferError.value = ''; transferVisible.value = true
}
async function transferOwner() {
  if (transferSaving.value || !transferOwnerId.value) { transferError.value = '请选择新项目负责人'; return }
  const targetProject = projectId.value
  transferSaving.value = true; transferError.value = ''
  try {
    await managementApi.transferOwner(targetProject, transferOwnerId.value)
    transferVisible.value = false
    await load()
    ElMessage.success('项目负责人已移交')
  } catch (err) { transferError.value = managementError(err, '移交失败，请重试。') }
  finally { transferSaving.value = false }
}
watch(projectId, () => { transferVisible.value = false; void loadProject() })
watch([projectId, tab], () => {
  if (route.query.project_id === projectId.value && route.query.tab === tab.value) return
  void router.replace({ query: { ...route.query, task_id: route.query.project_id === projectId.value ? route.query.task_id : undefined, project_id: projectId.value || undefined, tab: tab.value } })
})
watch(() => [route.query.project_id, route.query.tab], ([nextProject, nextTab]) => {
  if (typeof nextProject === 'string' && nextProject !== projectId.value) projectId.value = nextProject
  tab.value = typeof nextTab === 'string' && tabNames.includes(nextTab) ? nextTab : 'tasks'
})
onMounted(load)
</script>

<template>
  <div class="management-view">
    <header class="management-heading"><div><h2>团队协作</h2><p>明确交付责任，处理阻塞，协调本周计划。</p></div><el-button :loading="loading" @click="load">刷新</el-button></header>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false"><el-button link @click="load">重试</el-button></el-alert>
    <div class="management-scope">
      <el-select v-model="projectId" aria-label="选择管理项目" placeholder="选择项目" filterable :disabled="accessSaving || transferSaving"><el-option v-for="item in projects" :key="item.id" :label="item.name" :value="item.id" /></el-select>
      <el-date-picker v-model="week" type="date" value-format="YYYY-MM-DD" aria-label="计划周起始日期" placeholder="选择计划周" :clearable="false" @change="normalizeWeek" />
      <span v-if="access" class="access-control">访问范围 <el-select :model-value="access.visibility" :disabled="!access.can_manage || accessSaving || transferSaving" aria-label="项目访问范围" @change="saveAccess"><el-option label="公司内可见" value="company" /><el-option label="仅项目授权成员" value="private" /></el-select><el-button v-if="access.can_transfer_owner" size="small" :disabled="accessSaving || transferSaving" @click="openTransfer">移交项目负责人</el-button></span>
    </div>
    <el-empty v-if="!projects.length && !loading && !error" description="暂无可管理的项目，请先创建或加入项目" />
    <template v-else-if="projectId">
      <div class="management-context"><strong>{{ project?.name }}</strong><span>{{ tasks.length }} 项任务</span><RouterLink :to="`/projects/${projectId}/tasks`">打开任务列表</RouterLink></div>
      <el-tabs v-model="tab">
        <el-tab-pane label="责任与交付" name="tasks"><TaskManagementPanel v-if="tab === 'tasks' && access" :key="projectId" :project-id="projectId" :tasks="tasks" :users="users" :can-write="access.can_write" @changed="loadProject" /></el-tab-pane>
        <el-tab-pane label="本周容量" name="capacity"><CapacityPanel v-if="tab === 'capacity' && access" :key="`${projectId}:${week}`" :week="week" :tasks="tasks" :users="users" :can-write="access.can_write" /></el-tab-pane>
        <el-tab-pane label="交付计划" name="plan"><ProjectPlanPanel v-if="tab === 'plan' && access" :key="projectId" :project-id="projectId" :tasks="tasks" :users="users" :projects="projects" :can-write="access.can_write" @changed="loadProject" /></el-tab-pane>
        <el-tab-pane label="承诺与复盘" name="weekly"><WeeklyReviewPanel v-if="tab === 'weekly' && access" :key="`${projectId}:${week}`" :project-id="projectId" :week="week" :tasks="tasks" :users="users" :can-write="access.can_write" @changed="loadProject" /></el-tab-pane>
        <el-tab-pane label="历史报告" name="reports"><ReportHistoryPanel v-if="tab === 'reports'" /></el-tab-pane>
      </el-tabs>
    </template>
    <el-dialog v-model="transferVisible" title="移交项目负责人" width="min(480px, calc(100vw - 24px))" :close-on-click-modal="false" :show-close="!transferSaving" :close-on-press-escape="!transferSaving">
      <p class="transfer-help">将项目管理责任移交给新的负责人。私有项目请先在项目成员中添加新负责人。</p>
      <el-select v-model="transferOwnerId" filterable aria-label="选择新项目负责人" placeholder="选择新项目负责人" :disabled="transferSaving" style="width:100%"><el-option v-for="user in users.filter(item => item.id !== access?.owner_id)" :key="user.id" :label="user.full_name" :value="user.id" /></el-select>
      <el-alert v-if="transferError" :title="transferError" type="error" :closable="false" show-icon style="margin-top:12px" />
      <template #footer><el-button :disabled="transferSaving" @click="transferVisible = false">取消</el-button><el-button type="primary" :loading="transferSaving" :disabled="transferSaving || !transferOwnerId" @click="transferOwner">确认移交</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.management-heading { display:flex; justify-content:space-between; align-items:center; gap:16px; margin-bottom:20px; }
.management-heading h2 { font-size:20px; margin:0 0 6px; }.management-heading p { margin:0; font-size:13px; color:var(--muted); }
.management-scope { display:flex; gap:14px; flex-wrap:wrap; align-items:center; margin:20px 0 12px; }.management-scope>.el-select { width:260px; }
.access-control { display:flex; align-items:center; gap:8px; font-size:12px; color:var(--muted); }.access-control .el-select { width:170px; }
.management-context { display:flex; gap:14px; align-items:center; font-size:13px; margin-bottom:12px; flex-wrap:wrap; }.management-context span { color:var(--muted); }.management-context a { color:var(--brand); }
.transfer-help { font-size:13px; line-height:1.8; color:var(--muted); margin:0 0 16px; }
@media(max-width:600px) { .management-scope { gap:10px; }.management-scope>.el-select,.management-scope :deep(.el-date-editor) { width:100%; }.access-control { width:100%; flex-wrap:wrap; justify-content:space-between; }.management-context { font-size:12px; }.management-heading p { max-width:240px; } }
</style>
