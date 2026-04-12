<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DatasetComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import { dashboardApi } from '@/api/dashboard'
import type { OverviewStats, TeamWorkload, RecentActivity } from '@/types/models'

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent, LegendComponent, DatasetComponent])

const loading = ref(true)

const stats = ref<OverviewStats>({
  total_tasks: 0,
  in_progress_tasks: 0,
  overdue_tasks: 0,
  completion_rate: 0,
})

const teamWorkload = ref<TeamWorkload[]>([])
const recentActivities = ref<RecentActivity[]>([])

const projectChartOption = computed(() => {
  const names = teamWorkload.value.map((w) => w.full_name)
  const completed = teamWorkload.value.map((w) => w.completed_tasks)
  const inProgress = teamWorkload.value.map((w) => w.in_progress_tasks)
  const overdue = teamWorkload.value.map((w) => w.overdue_tasks)

  return {
    tooltip: {
      trigger: 'axis' as const,
      axisPointer: { type: 'shadow' as const },
    },
    legend: {
      data: ['已完成', '进行中', '已逾期'],
      bottom: 0,
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '14%',
      top: '8%',
      containLabel: true,
    },
    xAxis: {
      type: 'category' as const,
      data: names,
      axisLabel: {
        rotate: names.length > 6 ? 30 : 0,
      },
    },
    yAxis: {
      type: 'value' as const,
      minInterval: 1,
    },
    series: [
      {
        name: '已完成',
        type: 'bar' as const,
        stack: 'total',
        data: completed,
        itemStyle: { color: '#67C23A' },
      },
      {
        name: '进行中',
        type: 'bar' as const,
        stack: 'total',
        data: inProgress,
        itemStyle: { color: '#409EFF' },
      },
      {
        name: '已逾期',
        type: 'bar' as const,
        stack: 'total',
        data: overdue,
        itemStyle: { color: '#F56C6C' },
      },
    ],
  }
})

const workloadChartOption = computed(() => {
  const sorted = [...teamWorkload.value].sort((a, b) => a.assigned_tasks - b.assigned_tasks)
  const names = sorted.map((w) => w.full_name)
  const assigned = sorted.map((w) => w.assigned_tasks)
  const completed = sorted.map((w) => w.completed_tasks)

  return {
    tooltip: {
      trigger: 'axis' as const,
      axisPointer: { type: 'shadow' as const },
    },
    legend: {
      data: ['分配任务', '已完成'],
      bottom: 0,
    },
    grid: {
      left: '3%',
      right: '6%',
      bottom: '14%',
      top: '8%',
      containLabel: true,
    },
    xAxis: {
      type: 'value' as const,
      minInterval: 1,
    },
    yAxis: {
      type: 'category' as const,
      data: names,
    },
    series: [
      {
        name: '分配任务',
        type: 'bar' as const,
        data: assigned,
        itemStyle: { color: '#409EFF' },
      },
      {
        name: '已完成',
        type: 'bar' as const,
        data: completed,
        itemStyle: { color: '#67C23A' },
      },
    ],
  }
})

function formatTime(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)

  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin} 分钟前`
  if (diffHour < 24) return `${diffHour} 小时前`
  if (diffDay < 30) return `${diffDay} 天前`
  return date.toLocaleDateString('zh-CN')
}

function activityColor(pct: number): string {
  if (pct >= 100) return '#67C23A'
  if (pct >= 50) return '#409EFF'
  if (pct >= 25) return '#E6A23C'
  return '#909399'
}

onMounted(async () => {
  try {
    const [overviewRes, workloadRes, activityRes] = await Promise.all([
      dashboardApi.overview(),
      dashboardApi.teamWorkload(),
      dashboardApi.recentActivity(),
    ])
    stats.value = overviewRes.data
    teamWorkload.value = workloadRes.data
    recentActivities.value = activityRes.data
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div v-loading="loading" class="dashboard-page">
    <!-- Stat Cards -->
    <el-row :gutter="20" class="stat-row">
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon total">
            <el-icon size="28"><Tickets /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.total_tasks }}</div>
            <div class="stat-label">总任务数</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon progress">
            <el-icon size="28"><Loading /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.in_progress_tasks }}</div>
            <div class="stat-label">进行中</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover" class="stat-card stat-card--danger">
          <div class="stat-icon overdue">
            <el-icon size="28"><WarningFilled /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value danger-text">{{ stats.overdue_tasks }}</div>
            <div class="stat-label">已逾期</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon rate">
            <el-icon size="28"><TrendCharts /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ (stats.completion_rate * 100).toFixed(1) }}%</div>
            <div class="stat-label">完成率</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Charts Row -->
    <el-row :gutter="20" class="chart-row">
      <el-col :xs="24" :lg="12">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <span class="card-title">项目进度概览</span>
          </template>
          <div class="chart-container">
            <v-chart
              v-if="teamWorkload.length > 0"
              :option="projectChartOption"
              autoresize
              class="chart"
            />
            <el-empty v-else description="暂无数据" />
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="12">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <span class="card-title">团队工作量</span>
          </template>
          <div class="chart-container">
            <v-chart
              v-if="teamWorkload.length > 0"
              :option="workloadChartOption"
              autoresize
              class="chart"
            />
            <el-empty v-else description="暂无数据" />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Recent Activity -->
    <el-card shadow="hover" class="activity-card">
      <template #header>
        <span class="card-title">最近动态</span>
      </template>
      <el-timeline v-if="recentActivities.length > 0">
        <el-timeline-item
          v-for="activity in recentActivities"
          :key="activity.id"
          :color="activityColor(activity.progress_pct)"
          :timestamp="formatTime(activity.created_at)"
          placement="top"
        >
          <div class="activity-content">
            <span class="activity-user">{{ activity.user_name }}</span>
            更新了
            <span class="activity-project">{{ activity.project_name }}</span>
            中的任务
            <span class="activity-task">{{ activity.task_title }}</span>
            <el-tag
              size="small"
              :type="activity.progress_pct >= 100 ? 'success' : 'primary'"
              class="activity-tag"
            >
              {{ activity.progress_pct }}%
            </el-tag>
            <div v-if="activity.note" class="activity-note">{{ activity.note }}</div>
          </div>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else description="暂无动态" />
    </el-card>
  </div>
</template>

<style scoped>
.dashboard-page {
  max-width: 1400px;
}

.stat-row {
  margin-bottom: 20px;
}

.stat-card {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}

.stat-card :deep(.el-card__body) {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
  padding: 20px;
}

.stat-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  border-radius: 12px;
  flex-shrink: 0;
}

.stat-icon.total {
  background: rgba(64, 158, 255, 0.1);
  color: #409eff;
}

.stat-icon.progress {
  background: rgba(230, 162, 60, 0.1);
  color: #e6a23c;
}

.stat-icon.overdue {
  background: rgba(245, 108, 108, 0.1);
  color: #f56c6c;
}

.stat-icon.rate {
  background: rgba(103, 194, 58, 0.1);
  color: #67c23a;
}

.stat-info {
  flex: 1;
  min-width: 0;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #303133;
  line-height: 1.2;
}

.danger-text {
  color: #f56c6c;
}

.stat-label {
  font-size: 13px;
  color: #909399;
  margin-top: 4px;
}

.chart-row {
  margin-bottom: 20px;
}

.chart-card {
  margin-bottom: 12px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.chart-container {
  height: 350px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.chart {
  width: 100%;
  height: 100%;
}

.activity-card {
  margin-bottom: 20px;
}

.activity-content {
  font-size: 14px;
  color: #606266;
  line-height: 1.6;
}

.activity-user {
  font-weight: 600;
  color: #303133;
}

.activity-project {
  color: #409eff;
  font-weight: 500;
}

.activity-task {
  color: #303133;
  font-weight: 500;
}

.activity-tag {
  margin-left: 8px;
  vertical-align: middle;
}

.activity-note {
  margin-top: 4px;
  font-size: 13px;
  color: #909399;
  padding-left: 2px;
}
</style>
