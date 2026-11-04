<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { dashboardApi } from '@/api/dashboard'
import { useProjectUpdates } from '@/composables/useProjectUpdates'
import { useDashboardPanel } from '@/composables/useDashboardPanel'
import { ArrowDown } from '@element-plus/icons-vue'
import type { OverviewStats, RecentActivity, TeamWorkload } from '@/types/models'

type QuadrantKey = 'urgent_important' | 'important_not_urgent' | 'urgent_not_important' | 'not_urgent_not_important'
interface MyTaskItem { id: string; title: string; project_id: string; project_name: string; deadline: string | null; is_overdue: boolean }
type QuadrantTaskMap = Record<QuadrantKey, MyTaskItem[]>
interface ProjectProgress { id: string; name: string; start_date: string | null; end_date: string | null; total_tasks: number; done_tasks: number; in_progress_tasks: number; overdue_tasks: number; progress_pct: number }
const auth = useAuthStore()
const management = computed(() => auth.isManager || auth.can('project.edit'))
const overview = reactive(useDashboardPanel<OverviewStats>(dashboardApi.overview))
const mine = reactive(useDashboardPanel<QuadrantTaskMap>(dashboardApi.myTasks))
const projects = reactive(useDashboardPanel<ProjectProgress[]>(dashboardApi.projectProgress))
const workload = reactive(useDashboardPanel<TeamWorkload[]>(dashboardApi.teamWorkload))
const activity = reactive(useDashboardPanel<RecentActivity[]>(() => dashboardApi.recentActivity(8)))
const showMyTasks = ref(true)
const showProjects = ref(true)
const showWorkload = ref(true)
const quadrantKeys: QuadrantKey[] = ['urgent_important', 'important_not_urgent', 'urgent_not_important', 'not_urgent_not_important']
const quadrantLabels: Record<QuadrantKey, { title: string; color: string }> = {
  urgent_important: { title: '紧急且重要', color: '#c83d47' },
  important_not_urgent: { title: '重要不紧急', color: '#a56b17' },
  urgent_not_important: { title: '紧急不重要', color: '#3474b9' },
  not_urgent_not_important: { title: '不紧急不重要', color: '#687880' },
}
const myTaskCount = computed(() => quadrantKeys.reduce((sum, key) => sum + (mine.data?.[key]?.length || 0), 0))
const sortedWorkload = computed(() => [...(workload.data || [])]
  .filter(item => item.workload_hours > 0 || item.assigned_tasks > 0)
  .sort((a, b) => b.workload_hours - a.workload_hours))
const maxWorkload = computed(() => Math.max(1, ...sortedWorkload.value.map(item => item.workload_hours)))
function workloadPercent(hours: number) { return Math.round(hours / maxWorkload.value * 100) }
function formatHours(hours: number) { return Number(hours || 0).toFixed(Number.isInteger(hours || 0) ? 0 : 1) }
function formatDate(value: string | null) { return value ? value.slice(0, 10) : '未设置' }
function updatedLabel(value: number | null) { return value ? new Date(value).toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '' }
function activityTime(value: string) { return value.replace('T', ' ').slice(0, 16) }
function taskLink(projectId: string, taskId: string) { return { path: `/projects/${projectId}/board`, query: { taskId, from: '/dashboard' } } }
function projectRisk(project: ProjectProgress) {
  const reasons: string[] = []
  if (project.overdue_tasks > 0) reasons.push(`${project.overdue_tasks} 个任务逾期`)
  if (project.start_date && project.end_date) {
    const now = Date.now(), start = new Date(project.start_date).getTime(), end = new Date(project.end_date).getTime()
    if (end > start && now > start) {
      const elapsed = Math.min((now - start) / (end - start), 1) * 100
      if (project.progress_pct - elapsed < -30) reasons.push('完成比例明显低于已用工期')
      else if (project.progress_pct - elapsed < -15) reasons.push('完成比例低于已用工期')
      if (now > end && project.progress_pct < 100) reasons.push('项目已超期')
    }
  }
  if (project.total_tasks > 0 && !project.in_progress_tasks && project.done_tasks < project.total_tasks) reasons.push('无进行中的任务')
  const high = reasons.length >= 2 || reasons.includes('项目已超期')
  return { reasons, rank: high ? 2 : reasons.length ? 1 : 0, label: high ? '高风险' : reasons.length ? '有风险' : '正常', color: high ? '#c83d47' : reasons.length ? '#a56b17' : '#168377' }
}
const sortedProjects = computed(() => (projects.data || []).map(project => ({ ...project, risk: projectRisk(project) }))
  .sort((a, b) => b.risk.rank - a.risk.rank || b.overdue_tasks - a.overdue_tasks))
async function loadDashboard() { await Promise.all([overview.load(), mine.load(), projects.load(), workload.load(), activity.load()]) }
onMounted(loadDashboard)
useProjectUpdates(loadDashboard)
</script>

<template>
  <div class="dash">
    <div class="dashboard-title"><div><h1>{{ management ? '项目工作台' : '我的工作台' }}</h1><p>{{ management ? '优先关注项目风险、逾期任务和最近进展' : '查看个人待办及项目进展' }}</p></div><el-button @click="loadDashboard">刷新全部</el-button></div>
    <div class="data-status" role="status"><span v-if="overview.loading">{{ overview.data ? '正在更新总览…' : '正在读取总览…' }}</span><span v-if="overview.updatedAt">总览更新于 {{ updatedLabel(overview.updatedAt) }}</span></div>
    <el-alert v-if="overview.error" type="error" :closable="false" show-icon :title="overview.error + (overview.data ? '，下方保留上次成功数据' : '，总览暂不可用')"><el-button link @click="overview.load">重试总览</el-button></el-alert>
    <div v-if="overview.data" class="stats">
      <div class="sc"><span class="sv">{{ overview.data.total_tasks }}</span><span class="sl">总任务</span></div>
      <div class="sc"><span class="sv">{{ overview.data.in_progress_tasks }}</span><span class="sl">进行中</span></div>
      <div class="sc"><span class="sv overdue-number">{{ overview.data.overdue_tasks }}</span><span class="sl">已逾期</span></div>
      <div class="sc"><span class="sv">{{ Math.min(overview.data.completion_rate, 100).toFixed(1) }}%</span><span class="sl">完成任务 / 总任务</span></div>
    </div>
    <div class="dashboard-sections">
      <section class="section" :style="{ order: management ? 2 : 0 }">
        <header class="section-header"><button class="sec-hd" type="button" :aria-expanded="showMyTasks" aria-controls="my-task-panel" @click="showMyTasks = !showMyTasks"><span>我的任务 <small v-if="mine.data">{{ myTaskCount }} 项待办</small></span><el-icon :class="{ rot: !showMyTasks }"><ArrowDown /></el-icon></button></header>
        <div v-show="showMyTasks" id="my-task-panel">
          <div class="data-status" role="status"><span v-if="mine.loading">正在读取个人任务…</span><span v-if="mine.updatedAt">更新于 {{ updatedLabel(mine.updatedAt) }}</span></div>
          <el-alert v-if="mine.error" type="error" :closable="false" :title="mine.error + (mine.data ? '，已保留上次任务' : '')"><el-button link @click="mine.load">重试</el-button></el-alert>
          <p v-if="mine.data && !myTaskCount" class="compact-empty">当前没有分配给你的未完成任务。</p>
          <div v-if="mine.data && myTaskCount" class="quadrant-grid">
            <div v-for="key in quadrantKeys" :key="key" class="q-box" :style="{ borderTopColor: quadrantLabels[key].color }"><div class="q-hd"><span :style="{ color: quadrantLabels[key].color }">{{ quadrantLabels[key].title }}</span><span class="count">{{ mine.data[key]?.length || 0 }}</span></div>
              <RouterLink v-for="task in mine.data[key]" :key="task.id" class="q-item" :to="taskLink(task.project_id, task.id)"><span class="qi-title" :class="{ overdue: task.is_overdue }">{{ task.title }}</span><span class="qi-proj">{{ task.project_name }}</span><span class="qi-dl" :class="{ overdue: task.is_overdue }">截止 {{ formatDate(task.deadline) }}</span></RouterLink><p v-if="!mine.data[key]?.length" class="compact-empty">暂无此类待办</p>
            </div>
          </div>
        </div>
      </section>
      <section class="section" :style="{ order: management ? 0 : 1 }">
        <header class="section-header"><button class="sec-hd" type="button" :aria-expanded="showProjects" aria-controls="project-panel" @click="showProjects = !showProjects"><span>{{ management ? '优先关注的项目' : '项目进度概览' }}</span><el-icon :class="{ rot: !showProjects }"><ArrowDown /></el-icon></button></header>
        <div v-show="showProjects" id="project-panel">
          <div class="data-status" role="status"><span v-if="projects.loading">正在读取项目…</span><span v-if="projects.updatedAt">更新于 {{ updatedLabel(projects.updatedAt) }}</span></div>
          <el-alert v-if="projects.error" type="error" :closable="false" :title="projects.error + (projects.data ? '，已保留上次项目数据' : '')"><el-button link @click="projects.load">重试</el-button></el-alert>
          <RouterLink v-for="project in sortedProjects" :key="project.id" class="pp-row" :to="{ path: `/projects/${project.id}/board`, query: { from: '/dashboard' } }">
            <div class="pp-name"><strong>{{ project.name }}</strong><el-tag size="small" :type="project.risk.rank === 2 ? 'danger' : project.risk.rank === 1 ? 'warning' : 'success'">{{ project.risk.label }}</el-tag><span class="open-label">查看看板 →</span></div>
            <div v-if="project.risk.reasons.length" class="pp-risks"><span v-for="reason in project.risk.reasons" :key="reason">{{ reason }}</span></div>
            <div class="pp-stats"><span class="pp-num">已完成 {{ project.done_tasks }}/{{ project.total_tasks }}</span><el-progress :percentage="project.progress_pct" :stroke-width="8" :color="project.risk.color" /><span class="pp-date">开始 {{ formatDate(project.start_date) }} · 截止 {{ formatDate(project.end_date) }}</span></div>
          </RouterLink>
          <p v-if="projects.data && !projects.data.length" class="compact-empty">暂无未归档项目。</p>
          <p v-if="projects.data?.length" class="metric-note">完成比例按已完成任务数 / 总任务数计算；风险提示结合截止日期与完成比例，需结合实际情况核查。</p>
        </div>
      </section>
      <section class="section" :style="{ order: management ? 1 : 2 }">
        <header class="section-header"><h2>最近进展</h2></header>
        <div class="data-status" role="status"><span v-if="activity.loading">正在读取进展…</span><span v-if="activity.updatedAt">更新于 {{ updatedLabel(activity.updatedAt) }}</span></div>
        <el-alert v-if="activity.error" type="error" :closable="false" :title="activity.error + (activity.data ? '，已保留上次记录' : '')"><el-button link @click="activity.load">重试</el-button></el-alert>
        <ul v-if="activity.data?.length" class="activity-list"><li v-for="entry in activity.data" :key="entry.id"><RouterLink :to="taskLink(entry.project_id, entry.task_id)"><span class="activity-task">{{ entry.task_title }} <small>{{ entry.project_name }}</small></span><span class="activity-meta">{{ entry.user_name }} · {{ entry.progress_pct }}% · {{ activityTime(entry.created_at) }}</span><span v-if="entry.note" class="activity-note">{{ entry.note }}</span></RouterLink></li></ul>
        <p v-else-if="activity.data" class="compact-empty">暂无原始进展记录；这不代表没有实际工作。</p>
        <p v-if="activity.data?.length" class="metric-note">这里展示原始进展记录，记录百分比可能与父任务的当前加权进度不同。</p>
      </section>
      <section class="section" style="order:3">
        <header class="section-header"><button class="sec-hd" type="button" :aria-expanded="showWorkload" aria-controls="workload-panel" @click="showWorkload = !showWorkload"><span>未完成任务预计总工时</span><el-icon :class="{ rot: !showWorkload }"><ArrowDown /></el-icon></button></header>
        <div v-show="showWorkload" id="workload-panel">
          <div class="data-status" role="status"><span v-if="workload.loading">正在读取预计工时…</span><span v-if="workload.updatedAt">更新于 {{ updatedLabel(workload.updatedAt) }}</span></div>
          <el-alert v-if="workload.error" type="error" :closable="false" :title="workload.error + (workload.data ? '，已保留上次数据' : '')"><el-button link @click="workload.load">重试</el-button></el-alert>
          <p class="metric-note">汇总全部未完成任务，不限定本周；条形长度仅在当前人员间比较，不表示容量利用率。无有效工时的任务按层级暂估 8/4/2h；同一任务会计入每位负责人的总工时。</p>
          <RouterLink class="capacity-entry" :to="{ path: '/management', query: { tab: 'capacity' } }">打开本周容量排期 →</RouterLink>
          <div v-if="workload.data" class="wl-grid"><div v-for="person in sortedWorkload" :key="person.user_id" class="wl-item"><RouterLink v-if="auth.can('personnel.view_detail') || auth.user?.id === person.user_id" class="wl-name" :to="`/personnel/${person.user_id}`">{{ person.full_name }}</RouterLink><span v-else class="wl-name">{{ person.full_name }}</span><div class="wl-bar-wrap" aria-hidden="true"><div class="wl-bar" :style="{ width: workloadPercent(person.workload_hours) + '%' }"></div></div><span class="wl-hours">{{ formatHours(person.workload_hours) }}h</span><div class="wl-detail"><span>未完成 {{ person.assigned_tasks }} · 进行中 {{ person.in_progress_tasks }}</span><span v-if="person.overdue_tasks" class="overdue">{{ person.overdue_tasks }} 项逾期</span><span v-if="person.fallback_task_count">含 {{ person.fallback_task_count }} 项暂估 {{ formatHours(person.fallback_hours) }}h</span></div></div></div>
          <p v-if="workload.data && !sortedWorkload.length" class="compact-empty">暂无已分配的未完成任务。</p>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.capacity-entry { display:inline-block; font-size:13px; color:var(--brand); margin:0 0 14px; }
.dashboard-title { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:12px; }
.dashboard-title h1 { font-size:22px; margin:0 0 6px; }
.dashboard-title p,.metric-note { font-size:12px; color:var(--muted); line-height:1.7; }
.data-status { display:flex; flex-wrap:wrap; gap:12px; min-height:20px; font-size:12px; color:var(--muted); margin:6px 0; }
.stats { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:16px; border-block:1px solid var(--border); padding:18px 0; margin:16px 0 24px; }
.sc { padding-inline:16px; border-right:1px solid var(--border); }.sc:last-child { border:0; }
.sv { display:block; font-size:28px; font-weight:700; }.sl { font-size:12px; color:var(--muted); }.overdue-number,.overdue { color:#c83d47; }
.dashboard-sections { display:flex; flex-direction:column; }.section { margin-bottom:24px; min-width:0; }
.section-header { border-bottom:1px solid var(--border); padding-bottom:10px; margin-bottom:10px; }.section-header h2 { font-size:16px; }
.sec-hd { display:flex; width:100%; align-items:center; justify-content:space-between; background:none; border:0; text-align:left; color:var(--ink); font-size:16px; font-weight:600; cursor:pointer; padding:4px 0; }.sec-hd small { font-size:12px; font-weight:400; color:var(--muted); margin-left:8px; }.sec-hd .el-icon.rot { transform:rotate(-90deg); }
.quadrant-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; }.q-box { min-width:0; padding-top:10px; border-top:2px solid; }.q-hd { display:flex; gap:8px; align-items:center; font-size:14px; font-weight:600; margin-bottom:8px; }.count { color:var(--muted); font-size:12px; }
.q-item { display:flex; align-items:center; flex-wrap:wrap; gap:6px 10px; padding:10px 0; border-bottom:1px solid var(--border); font-size:14px; }.q-item:hover,.pp-row:hover { background:#eaf5f3; }.qi-title { flex:1 1 180px; overflow-wrap:anywhere; }.qi-proj,.qi-dl { font-size:12px; color:var(--muted); }
.compact-empty { color:var(--muted); font-size:14px; padding:12px 0; }.pp-row { display:block; padding:14px 4px; border-bottom:1px solid var(--border); }.pp-name { display:flex; align-items:center; flex-wrap:wrap; gap:8px; font-size:14px; }.open-label { margin-left:auto; color:var(--brand); font-size:12px; }.pp-risks { display:flex; flex-wrap:wrap; gap:6px 12px; color:#a56b17; font-size:12px; margin-top:8px; }.pp-stats { display:flex; align-items:center; gap:12px; margin-top:10px; }.pp-stats .el-progress { flex:1; min-width:100px; }.pp-num,.pp-date { font-size:12px; color:var(--muted); }.metric-note { margin:10px 0; }
.activity-list { list-style:none; padding:0; }.activity-list li { border-bottom:1px solid var(--border); }.activity-list a { display:flex; flex-direction:column; gap:5px; padding:10px 4px; }.activity-task { font-size:14px; font-weight:600; }.activity-task small { font-size:12px; color:var(--muted); font-weight:400; margin-left:8px; }.activity-meta { font-size:12px; color:var(--muted); }.activity-note { font-size:13px; color:var(--ink); white-space:pre-wrap; overflow-wrap:anywhere; }
.wl-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:16px 24px; }.wl-item { display:grid; grid-template-columns:minmax(60px,auto) 1fr auto; align-items:center; gap:8px; border-bottom:1px solid var(--border); padding-bottom:10px; min-width:0; }.wl-name { font-size:14px; color:var(--brand); }.wl-bar-wrap { height:8px; background:#dfe9e7; border-radius:4px; overflow:hidden; }.wl-bar { height:100%; background:var(--brand); }.wl-hours { font-size:14px; font-weight:600; }.wl-detail { grid-column:1/-1; display:flex; flex-wrap:wrap; gap:6px 12px; font-size:12px; color:var(--muted); }
@media (max-width:760px) { .dashboard-title { align-items:flex-start; }.dashboard-title h1 { font-size:20px; }.stats { grid-template-columns:repeat(2,minmax(0,1fr)); }.sc { padding:0 8px; }.sv { font-size:24px; }.quadrant-grid { grid-template-columns:1fr; }.pp-stats { flex-wrap:wrap; }.pp-date { flex-basis:100%; }.wl-grid { grid-template-columns:minmax(0,1fr); }.open-label { flex-basis:100%; margin-left:0; } }
</style>
