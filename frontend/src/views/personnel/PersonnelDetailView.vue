<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { RadarChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  RadarComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import { usersApi } from '@/api/users'
import { capabilitiesApi } from '@/api/capabilities'
import { aiApi } from '@/api/ai'
import type { User, UserSkill, CapabilityProfile } from '@/types/models'
import { UserRole } from '@/types/enums'

use([CanvasRenderer, RadarChart, TitleComponent, TooltipComponent, RadarComponent])

const route = useRoute()
const userId = computed(() => route.params.id as string)

const user = ref<User | null>(null)
const skills = ref<UserSkill[]>([])
const capability = ref<CapabilityProfile | null>(null)
const workload = ref<{ assigned_tasks: number; in_progress_tasks: number; completed_tasks: number; overdue_tasks: number } | null>(null)
const loading = ref(false)
const analyzing = ref(false)

const roleLabel: Record<string, string> = {
  [UserRole.ADMIN]: '管理员',
  [UserRole.MANAGER]: '经理',
  [UserRole.MEMBER]: '成员',
}

const roleTagType: Record<string, 'danger' | 'warning' | 'info'> = {
  [UserRole.ADMIN]: 'danger',
  [UserRole.MANAGER]: 'warning',
  [UserRole.MEMBER]: 'info',
}

const radarOption = computed(() => {
  if (!skills.value.length) {
    return null
  }

  const indicators = skills.value.map((s) => ({
    name: s.skill_name,
    max: 100,
  }))
  const values = skills.value.map((s) => s.proficiency)

  return {
    title: {
      text: '技能雷达图',
      left: 'center',
      textStyle: { fontSize: 14, color: '#303133' },
    },
    tooltip: {
      trigger: 'item',
    },
    radar: {
      indicator: indicators,
      shape: 'polygon',
      radius: '65%',
      axisName: {
        color: '#606266',
        fontSize: 12,
      },
    },
    series: [
      {
        type: 'radar',
        data: [
          {
            value: values,
            name: user.value?.full_name || '技能水平',
            areaStyle: { color: 'rgba(64, 158, 255, 0.2)' },
            lineStyle: { color: '#409eff' },
            itemStyle: { color: '#409eff' },
          },
        ],
      },
    ],
  }
})

const onTimeRateDisplay = computed(() => {
  if (capability.value?.on_time_rate == null) return '--'
  return `${(capability.value.on_time_rate * 100).toFixed(1)}%`
})

const performanceScoreDisplay = computed(() => {
  if (capability.value?.performance_score == null) return '--'
  return capability.value.performance_score.toFixed(1)
})

const currentTaskCount = computed(() => {
  return workload.value?.assigned_tasks ?? 0
})

const taskHistory = computed(() => {
  if (!workload.value) return []
  const items: { label: string; count: number; type: 'primary' | 'success' | 'warning' | 'danger' }[] = []
  if (workload.value.in_progress_tasks > 0) {
    items.push({ label: '进行中', count: workload.value.in_progress_tasks, type: 'primary' })
  }
  if (workload.value.completed_tasks > 0) {
    items.push({ label: '已完成', count: workload.value.completed_tasks, type: 'success' })
  }
  if (workload.value.overdue_tasks > 0) {
    items.push({ label: '已逾期', count: workload.value.overdue_tasks, type: 'danger' })
  }
  return items
})

async function loadData() {
  loading.value = true
  try {
    const [userRes, skillsRes] = await Promise.all([
      usersApi.get(userId.value),
      usersApi.getSkills(userId.value),
    ])
    user.value = userRes.data
    skills.value = skillsRes.data

    try {
      const capRes = await capabilitiesApi.get(userId.value)
      capability.value = capRes.data
    } catch {
      capability.value = null
    }

    try {
      const wlRes = await usersApi.getWorkload(userId.value)
      workload.value = wlRes.data as typeof workload.value
    } catch {
      workload.value = null
    }
  } finally {
    loading.value = false
  }
}

async function analyzeCapability() {
  analyzing.value = true
  try {
    await aiApi.analyzeCapability(userId.value)
    ElMessage.success('AI 能力分析已完成')
    const capRes = await capabilitiesApi.get(userId.value)
    capability.value = capRes.data
  } catch {
    ElMessage.error('AI 能力分析失败，请稍后重试')
  } finally {
    analyzing.value = false
  }
}

onMounted(() => {
  loadData()
})
</script>

<template>
  <div v-loading="loading" class="personnel-detail">
    <template v-if="user">
      <!-- Profile Header -->
      <el-card class="profile-header-card">
        <div class="profile-header">
          <el-avatar :size="72" :src="user.avatar_url || undefined">
            {{ user.full_name?.charAt(0) || user.username?.charAt(0) }}
          </el-avatar>
          <div class="profile-info">
            <h2 class="profile-name">{{ user.full_name || user.username }}</h2>
            <div class="profile-meta">
              <el-tag :type="roleTagType[user.role] || 'info'" size="small">
                {{ roleLabel[user.role] || user.role }}
              </el-tag>
              <span class="profile-email">{{ user.email }}</span>
            </div>
          </div>
          <div class="profile-actions">
            <el-button
              type="primary"
              :loading="analyzing"
              @click="analyzeCapability"
            >
              AI 能力分析
            </el-button>
          </div>
        </div>
      </el-card>

      <!-- Stats Cards -->
      <div class="stats-row">
        <el-card class="stat-card">
          <div class="stat-value">{{ currentTaskCount }}</div>
          <div class="stat-label">当前任务</div>
        </el-card>
        <el-card class="stat-card">
          <div class="stat-value">{{ onTimeRateDisplay }}</div>
          <div class="stat-label">按时完成率</div>
        </el-card>
        <el-card class="stat-card">
          <div class="stat-value">{{ performanceScoreDisplay }}</div>
          <div class="stat-label">绩效评分</div>
        </el-card>
      </div>

      <!-- Two-column Layout -->
      <div class="detail-columns">
        <!-- Left: Radar Chart -->
        <el-card class="radar-card">
          <template #header>
            <span>能力雷达图</span>
          </template>
          <div v-if="radarOption" class="radar-chart-wrapper">
            <v-chart :option="radarOption" autoresize class="radar-chart" />
          </div>
          <el-empty v-else description="暂无技能数据" />
        </el-card>

        <!-- Right: AI Analysis -->
        <el-card class="analysis-card">
          <template #header>
            <span>AI 分析报告</span>
          </template>
          <template v-if="capability?.ai_analysis">
            <div class="analysis-section">
              <h4>优势</h4>
              <ul>
                <li v-for="(item, idx) in capability.ai_analysis.strengths" :key="'s-' + idx">
                  {{ item }}
                </li>
              </ul>
            </div>
            <div class="analysis-section">
              <h4>成长方向</h4>
              <ul>
                <li v-for="(item, idx) in capability.ai_analysis.growth_areas" :key="'g-' + idx">
                  {{ item }}
                </li>
              </ul>
            </div>
            <div class="analysis-section">
              <h4>推荐任务类型</h4>
              <div class="recommended-tags">
                <el-tag
                  v-for="(item, idx) in capability.ai_analysis.recommended_task_types"
                  :key="'r-' + idx"
                  type="success"
                  size="small"
                  class="rec-tag"
                >
                  {{ item }}
                </el-tag>
              </div>
            </div>
            <div v-if="capability.ai_analysis.summary" class="analysis-section">
              <h4>综合评价</h4>
              <p class="analysis-summary">{{ capability.ai_analysis.summary }}</p>
            </div>
          </template>
          <el-empty v-else description="暂无 AI 分析，请点击上方按钮进行分析" />
        </el-card>
      </div>

      <!-- Task History -->
      <el-card class="task-history-card">
        <template #header>
          <span>任务概览</span>
        </template>
        <div v-if="taskHistory.length" class="task-timeline">
          <el-timeline>
            <el-timeline-item
              v-for="item in taskHistory"
              :key="item.label"
              :type="item.type"
              :timestamp="item.label"
              placement="top"
            >
              <span>{{ item.count }} 个任务</span>
            </el-timeline-item>
          </el-timeline>
        </div>
        <el-empty v-else description="暂无任务记录" />
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.personnel-detail {
  padding: 0;
  min-height: 300px;
}

.profile-header-card {
  margin-bottom: 20px;
}

.profile-header {
  display: flex;
  align-items: center;
  gap: 20px;
}

.profile-info {
  flex: 1;
}

.profile-name {
  margin: 0 0 8px 0;
  font-size: 22px;
  font-weight: 600;
  color: #303133;
}

.profile-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.profile-email {
  color: #909399;
  font-size: 14px;
}

.profile-actions {
  flex-shrink: 0;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.stat-card {
  text-align: center;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #409eff;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 14px;
  color: #909399;
}

.detail-columns {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 20px;
}

.radar-chart-wrapper {
  width: 100%;
  display: flex;
  justify-content: center;
}

.radar-chart {
  width: 100%;
  height: 350px;
}

.analysis-card {
  overflow: auto;
}

.analysis-section {
  margin-bottom: 16px;
}

.analysis-section h4 {
  margin: 0 0 8px 0;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.analysis-section ul {
  margin: 0;
  padding-left: 20px;
}

.analysis-section li {
  margin-bottom: 4px;
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}

.recommended-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.rec-tag {
  margin: 0;
}

.analysis-summary {
  margin: 0;
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}

.task-history-card {
  margin-bottom: 20px;
}

.task-timeline {
  padding: 10px 0;
}
</style>
