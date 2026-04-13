<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { dashboardApi } from '@/api/dashboard'
import type { OverviewStats } from '@/types/models'

const router = useRouter()
const loading = ref(true)

type QuadrantKey =
  | 'urgent_important'
  | 'important_not_urgent'
  | 'urgent_not_important'
  | 'not_urgent_not_important'

interface MyTaskItem {
  id: string
  title: string
  project_id: string
  project_name: string
  deadline: string | null
  is_overdue: boolean
}

type QuadrantTaskMap = Record<QuadrantKey, MyTaskItem[]>

const stats = ref<OverviewStats>({ total_tasks: 0, in_progress_tasks: 0, overdue_tasks: 0, completion_rate: 0 })
const quadrantKeys: QuadrantKey[] = ['urgent_important', 'important_not_urgent', 'urgent_not_important', 'not_urgent_not_important']
const myTasks = ref<QuadrantTaskMap>({ urgent_important: [], important_not_urgent: [], urgent_not_important: [], not_urgent_not_important: [] })
const projectProgress = ref<any[]>([])
const teamWorkload = ref<any[]>([])

const showMyTasks = ref(true)
const showProjects = ref(true)
const showWorkload = ref(true)

// Sorted team workload by total load descending
const sortedWorkload = computed(() =>
  [...teamWorkload.value]
    .map(w => ({ ...w, total_load: w.assigned_tasks + w.in_progress_tasks }))
    .filter(w => w.total_load > 0 || w.completed_tasks > 0)
    .sort((a, b) => b.total_load - a.total_load)
)

function loadColor(n: number): string {
  if (n >= 8) return '#F56C6C'
  if (n >= 5) return '#E6A23C'
  return '#67C23A'
}

function formatDate(d: string | null) { return d ? d.slice(0, 10) : '-' }
function goToProject(pid: string) { router.push('/projects/' + pid + '/board') }
function goToProjects() { router.push('/projects') }

/**
 * Calculate project risk level based on:
 * - Time elapsed vs progress achieved
 * - Overdue task count
 * Returns { level: 'low'|'medium'|'high', label, color, reasons[] }
 */
function projectRisk(p: any): { level: string; label: string; color: string; reasons: string[] } {
  const reasons: string[] = []

  // 1. Overdue tasks
  if (p.overdue_tasks >= 3) reasons.push(p.overdue_tasks + ' 个任务逾期')
  else if (p.overdue_tasks > 0) reasons.push(p.overdue_tasks + ' 个任务逾期')

  // 2. Time vs progress deviation
  if (p.start_date && p.end_date) {
    const now = Date.now()
    const start = new Date(p.start_date).getTime()
    const end = new Date(p.end_date).getTime()
    const span = end - start
    if (span > 0) {
      const timeRatio = Math.min((now - start) / span, 1) * 100
      const deviation = p.progress_pct - timeRatio
      if (deviation < -30) reasons.push('进度严重滞后于工期 (' + Math.round(Math.abs(deviation)) + '%)')
      else if (deviation < -15) reasons.push('进度略低于工期预期')
      if (now > end && p.progress_pct < 100) reasons.push('项目已超期')
    }
  }

  // 3. No tasks in progress
  if (p.total_tasks > 0 && p.in_progress_tasks === 0 && p.done_tasks < p.total_tasks) {
    reasons.push('无进行中的任务')
  }

  const score = reasons.length
  if (score >= 2 || reasons.some(r => r.includes('严重') || r.includes('超期')))
    return { level: 'high', label: '高风险', color: '#F56C6C', reasons }
  if (score >= 1)
    return { level: 'medium', label: '有风险', color: '#E6A23C', reasons }
  return { level: 'low', label: '正常', color: '#67C23A', reasons }
}

const quadrantLabels: Record<QuadrantKey, { title: string; color: string; desc: string }> = {
  urgent_important: { title: '紧急且重要', color: '#F56C6C', desc: '立即处理' },
  important_not_urgent: { title: '重要不紧急', color: '#E6A23C', desc: '计划安排' },
  urgent_not_important: { title: '紧急不重要', color: '#409EFF', desc: '委派他人' },
  not_urgent_not_important: { title: '不紧急不重要', color: '#909399', desc: '适时处理' },
}

onMounted(async () => {
  loading.value = true
  try {
    const [overviewRes, myRes, projRes, wlRes] = await Promise.allSettled([
      dashboardApi.overview(),
      dashboardApi.myTasks(),
      dashboardApi.projectProgress(),
      dashboardApi.teamWorkload(),
    ])
    if (overviewRes.status === 'fulfilled') stats.value = overviewRes.value.data
    if (myRes.status === 'fulfilled') myTasks.value = myRes.value.data as QuadrantTaskMap
    if (projRes.status === 'fulfilled') projectProgress.value = projRes.value.data
    if (wlRes.status === 'fulfilled') teamWorkload.value = wlRes.value.data
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div v-loading="loading" class="dash">
    <!-- Stats Row -->
    <div class="stats">
      <div class="sc"><span class="sv">{{ stats.total_tasks }}</span><span class="sl">总任务</span></div>
      <div class="sc"><span class="sv" style="color:#E6A23C">{{ stats.in_progress_tasks }}</span><span class="sl">进行中</span></div>
      <div class="sc"><span class="sv" :style="{ color: stats.overdue_tasks > 0 ? '#F56C6C' : '#303133' }">{{ stats.overdue_tasks }}</span><span class="sl">已逾期</span></div>
      <div class="sc"><span class="sv" style="color:#67C23A">{{ Math.min(stats.completion_rate, 100).toFixed(1) }}%</span><span class="sl">完成率</span></div>
    </div>

    <!-- My Tasks Quadrant -->
    <el-card class="section">
      <template #header>
        <div class="sec-hd" @click="showMyTasks = !showMyTasks" style="cursor:pointer">
          <span>我的任务</span>
          <el-icon :class="{ rot: !showMyTasks }"><svg viewBox="0 0 1024 1024" width="14" height="14"><path d="M256 384l256 320 256-320z" fill="currentColor"/></svg></el-icon>
        </div>
      </template>
      <div v-show="showMyTasks" class="quadrant-grid">
        <div v-for="(qkey, idx) in quadrantKeys" :key="qkey" class="q-box" :style="{ borderTopColor: quadrantLabels[qkey].color }">
          <div class="q-hd">
            <span class="q-title" :style="{ color: quadrantLabels[qkey].color }">{{ quadrantLabels[qkey].title }}</span>
            <span class="q-desc">{{ quadrantLabels[qkey].desc }}</span>
            <el-badge :value="myTasks[qkey]?.length || 0" :type="myTasks[qkey]?.length ? (idx === 0 ? 'danger' : 'info') : 'info'" />
          </div>
          <div class="q-list">
            <div v-for="t in myTasks[qkey]" :key="t.id" class="q-item" @click="goToProject(t.project_id)">
              <span class="qi-title" :class="{ ovd: t.is_overdue }">{{ t.title }}</span>
              <span class="qi-proj">{{ t.project_name }}</span>
              <span class="qi-dl" :class="{ ovd: t.is_overdue }">{{ formatDate(t.deadline) }}</span>
            </div>
            <div v-if="!myTasks[qkey]?.length" class="q-empty">无</div>
          </div>
        </div>
      </div>
    </el-card>

    <!-- Project Progress -->
    <el-card class="section">
      <template #header>
        <div class="sec-hd" @click="showProjects = !showProjects" style="cursor:pointer">
          <span>项目进度概览</span>
          <el-icon :class="{ rot: !showProjects }"><svg viewBox="0 0 1024 1024" width="14" height="14"><path d="M256 384l256 320 256-320z" fill="currentColor"/></svg></el-icon>
        </div>
      </template>
      <div v-show="showProjects">
        <div v-for="p in projectProgress" :key="p.id" class="pp-row" @click="goToProject(p.id)">
          <div class="pp-name">
            {{ p.name }}
            <el-tag :color="projectRisk(p).color" size="small" effect="dark" style="margin-left:6px;border:none;color:#fff">
              {{ projectRisk(p).label }}
            </el-tag>
            <el-tag v-if="p.overdue_tasks > 0" type="danger" size="small" style="margin-left:4px">{{ p.overdue_tasks }} 逾期</el-tag>
          </div>
          <div v-if="projectRisk(p).reasons.length" class="pp-risks">
            <span v-for="(r, i) in projectRisk(p).reasons" :key="i" class="pp-risk-item">{{ r }}</span>
          </div>
          <div class="pp-stats">
            <span class="pp-num">{{ p.done_tasks }}/{{ p.total_tasks }}</span>
            <el-progress :percentage="p.progress_pct" :stroke-width="10" :color="projectRisk(p).color" style="flex:1" />
            <span class="pp-date">{{ formatDate(p.start_date) }} ~ {{ formatDate(p.end_date) }}</span>
          </div>
        </div>
        <el-empty v-if="!projectProgress.length" description="暂无活跃项目" :image-size="50" />
      </div>
    </el-card>

    <!-- Team Workload -->
    <el-card class="section">
      <template #header>
        <div class="sec-hd" @click="showWorkload = !showWorkload" style="cursor:pointer">
          <span>团队工作负荷</span>
          <el-icon :class="{ rot: !showWorkload }"><svg viewBox="0 0 1024 1024" width="14" height="14"><path d="M256 384l256 320 256-320z" fill="currentColor"/></svg></el-icon>
        </div>
      </template>
      <div v-show="showWorkload" class="wl-grid">
        <div v-for="w in sortedWorkload" :key="w.user_id" class="wl-item">
          <div class="wl-name">{{ w.full_name }}</div>
          <div class="wl-bar-wrap">
            <div class="wl-bar" :style="{ width: Math.min(w.total_load * 10, 100) + '%', background: loadColor(w.total_load) }"></div>
          </div>
          <div class="wl-nums">
            <span :style="{ color: loadColor(w.total_load), fontWeight: '700' }">{{ w.total_load }}</span>
            <span class="wl-detail">待办{{ w.assigned_tasks }} + 进行{{ w.in_progress_tasks }}</span>
            <span v-if="w.overdue_tasks > 0" class="wl-ovd">{{ w.overdue_tasks }}逾期</span>
          </div>
        </div>
        <el-empty v-if="!sortedWorkload.length" description="暂无数据" :image-size="50" />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.dash { padding: 0; }

/* Stats */
.stats { display: flex; gap: 16px; margin-bottom: 16px; }
.sc { flex: 1; background: #fff; border-radius: 8px; padding: 16px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.sv { font-size: 28px; font-weight: 700; color: #303133; display: block; }
.sl { font-size: 12px; color: #909399; }

/* Sections */
.section { margin-bottom: 16px; }
.sec-hd { display: flex; justify-content: space-between; align-items: center; font-weight: 600; font-size: 15px; }
.sec-hd .el-icon { transition: transform 0.2s; color: #909399; }
.sec-hd .el-icon.rot { transform: rotate(-90deg); }

/* Quadrant */
.quadrant-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.q-box { border: 1px solid #ebeef5; border-top: 3px solid #909399; border-radius: 6px; padding: 10px; min-height: 100px; }
.q-hd { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; }
.q-title { font-weight: 600; font-size: 13px; }
.q-desc { font-size: 11px; color: #c0c4cc; }
.q-list { }
.q-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; border-bottom: 1px solid #f5f7fa; cursor: pointer; font-size: 12px; }
.q-item:hover { background: #f0f5ff; }
.q-item:last-child { border-bottom: none; }
.qi-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #303133; }
.qi-title.ovd { color: #F56C6C; font-weight: 600; }
.qi-proj { color: #c0c4cc; font-size: 11px; max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.qi-dl { color: #909399; font-size: 11px; white-space: nowrap; }
.qi-dl.ovd { color: #F56C6C; font-weight: 600; }
.q-empty { font-size: 12px; color: #c0c4cc; text-align: center; padding: 12px; }

/* Project Progress */
.pp-row { display: flex; flex-direction: column; padding: 8px 0; border-bottom: 1px solid #f5f7fa; cursor: pointer; }
.pp-row:hover { background: #f9fbfd; }
.pp-row:last-child { border-bottom: none; }
.pp-name { font-size: 13px; font-weight: 500; color: #303133; margin-bottom: 4px; }
.pp-stats { display: flex; align-items: center; gap: 8px; }
.pp-num { font-size: 12px; color: #909399; min-width: 40px; }
.pp-date { font-size: 11px; color: #c0c4cc; white-space: nowrap; }
.pp-risks { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 4px; }
.pp-risk-item { font-size: 11px; color: #E6A23C; background: #fdf6ec; padding: 1px 6px; border-radius: 3px; }

/* Workload */
.wl-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 8px; }
.wl-item { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid #f5f7fa; }
.wl-name { font-size: 12px; color: #303133; min-width: 50px; font-weight: 500; }
.wl-bar-wrap { flex: 1; height: 8px; background: #f0f2f5; border-radius: 4px; overflow: hidden; }
.wl-bar { height: 100%; border-radius: 4px; transition: width 0.3s; }
.wl-nums { display: flex; align-items: center; gap: 4px; font-size: 11px; min-width: 120px; }
.wl-detail { color: #909399; }
.wl-ovd { color: #F56C6C; font-weight: 600; }
</style>
