<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
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
import http from '@/api/index'
import { usersApi } from '@/api/users'
import { capabilitiesApi } from '@/api/capabilities'
import { aiApi } from '@/api/ai'
import { skillsApi } from '@/api/skills'
import { useAuthStore } from '@/stores/auth'
import type { User, UserSkill, CapabilityProfile } from '@/types/models'
import { UserRole } from '@/types/enums'

use([CanvasRenderer, RadarChart, TitleComponent, TooltipComponent, RadarComponent])

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const userId = computed(() => route.params.id as string)
const canEditSkills = computed(() => auth.can('personnel.edit_skills'))
const canAnalyzeCapability = computed(() => auth.can('ai.capability'))
const canEditBio = computed(() => auth.user?.id === userId.value || auth.can('personnel.edit'))

const user = ref<User | null>(null)
const skills = ref<UserSkill[]>([])
const capability = ref<CapabilityProfile | null>(null)
const workload = ref<any>(null)
const userTasks = ref<any[]>([])
const loading = ref(false)
const analyzing = ref(false)
const editingBio = ref(false)
const savingBio = ref(false)
const bioDraft = ref('')

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

// Editable radar dimensions
const editingSkills = ref(false)
const allSkills = ref<{ id: string; name: string; category: string | null }[]>([])
const newSkillId = ref('')
const newProficiency = ref(3)

const radarOption = computed(() => {
  if (!skills.value.length) return null

  const indicators = skills.value.map((s) => ({
    name: s.skill_name,
    max: 5,
  }))
  const values = skills.value.map((s) => s.proficiency)

  return {
    tooltip: { trigger: 'item' },
    radar: {
      indicator: indicators,
      shape: 'polygon',
      radius: '65%',
      axisName: { color: '#606266', fontSize: 12 },
      splitNumber: 5,
    },
    series: [{
      type: 'radar',
      data: [{
        value: values,
        name: user.value?.full_name || '技能水平',
        areaStyle: { color: 'rgba(64, 158, 255, 0.2)' },
        lineStyle: { color: '#409eff' },
        itemStyle: { color: '#409eff' },
      }],
    }],
  }
})

const onTimeRateDisplay = computed(() => {
  if (capability.value?.on_time_rate == null) return '--'
  return `${Math.min(capability.value.on_time_rate, 100).toFixed(1)}%`
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
    bioDraft.value = userRes.data.bio || ''
    skills.value = skillsRes.data

    try {
      const capRes = await capabilitiesApi.get(userId.value)
      capability.value = capRes.data
    } catch {
      capability.value = null
    }

    try {
      const wlRes = await usersApi.getWorkload(userId.value)
      workload.value = wlRes.data
    } catch { workload.value = null }

    // Load user's tasks across all projects
    try {
      const res = await http.get('/users/' + userId.value + '/tasks')
      userTasks.value = res.data
    } catch { userTasks.value = [] }
  } finally {
    loading.value = false
  }
}

async function loadAllSkills() {
  try {
    const res = await skillsApi.list()
    allSkills.value = res.data
  } catch { /* silent */ }
}

function openSkillEditor() {
  if (!canEditSkills.value) return
  editingSkills.value = true
  loadAllSkills()
}

async function removeSkill(skillId: string) {
  const updated = skills.value.filter(s => s.skill_id !== skillId)
  await saveSkills(updated)
}

async function addSkill() {
  if (!newSkillId.value) { ElMessage.warning('请选择技能'); return }
  if (skills.value.some(s => s.skill_id === newSkillId.value)) { ElMessage.warning('该技能已存在'); return }
  const skill = allSkills.value.find(s => s.id === newSkillId.value)
  const updated = [...skills.value, { skill_id: newSkillId.value, skill_name: skill?.name || '', category: skill?.category || null, proficiency: newProficiency.value }]
  await saveSkills(updated)
  newSkillId.value = ''
  newProficiency.value = 3
}

async function updateProficiency(skillId: string, val: number) {
  const updated = skills.value.map(s => s.skill_id === skillId ? { ...s, proficiency: val } : s)
  await saveSkills(updated)
}

async function saveSkills(updatedSkills: UserSkill[]) {
  try {
    await usersApi.updateSkills(userId.value, updatedSkills.map(s => ({ skill_id: s.skill_id, proficiency: s.proficiency })))
    const res = await usersApi.getSkills(userId.value)
    skills.value = res.data
    ElMessage.success('技能已更新')
  } catch {
    ElMessage.error('技能更新失败')
  }
}

function openBioEditor() {
  bioDraft.value = user.value?.bio || ''
  editingBio.value = true
}

async function saveBio() {
  if (!user.value) return
  savingBio.value = true
  try {
    const res = await usersApi.update(userId.value, { bio: bioDraft.value.trim() || null })
    user.value = res.data
    bioDraft.value = res.data.bio || ''
    editingBio.value = false
    ElMessage.success('个人介绍已保存')
    if (auth.user?.id === userId.value) await auth.fetchUser()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    savingBio.value = false
  }
}

const aiStatusMsg = ref('')

async function analyzeCapability() {
  analyzing.value = true
  aiStatusMsg.value = '正在启动...'
  try {
    await aiApi.analyzeCapability(userId.value, (msg: string) => { aiStatusMsg.value = msg })
    ElMessage.success('AI 能力分析已完成')
    // Refresh all data so report and stats are in sync
    await loadData()
  } catch {
    ElMessage.error('AI 能力分析失败，请稍后重试')
  } finally {
    analyzing.value = false
    aiStatusMsg.value = ''
  }
}

function formatDateTime(d: string | null) { return d ? d.replace('T', ' ').slice(0, 16) : '' }
function taskStatusLabel(s: string) { return ({ not_started: '待开始', in_progress: '进行中', done: '已完成' } as any)[s] || s }
function taskStatusType(s: string) { return ({ not_started: 'info', in_progress: 'warning', done: 'success' } as any)[s] || 'info' }

onMounted(() => {
  loadData()
})
</script>

<template>
  <div v-loading="loading" class="personnel-detail">
    <template v-if="user">
      <div class="detail-toolbar">
        <el-button @click="router.push('/personnel')">返回人员列表</el-button>
      </div>

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
              <span v-if="user.department" class="profile-department">{{ user.department }}</span>
            </div>
          </div>
          <div v-if="canAnalyzeCapability" class="profile-actions">
            <el-button type="primary" :loading="analyzing" @click="analyzeCapability">
              AI 能力分析
            </el-button>
            <div v-if="aiStatusMsg" class="ai-status-text">{{ aiStatusMsg }}</div>
          </div>
        </div>
      </el-card>

      <el-card class="bio-card">
        <template #header>
          <div class="card-header-row">
            <span>个人介绍</span>
            <el-button v-if="canEditBio && !editingBio" type="primary" link size="small" @click="openBioEditor">编辑</el-button>
          </div>
        </template>
        <div v-if="editingBio" class="bio-editor">
          <el-input
            v-model="bioDraft"
            type="textarea"
            :rows="5"
            maxlength="1000"
            show-word-limit
            placeholder="填写擅长领域、项目经验、偏好的工作类型、当前限制等，AI 分析工作安排时会作为参考。"
          />
          <div class="bio-actions">
            <el-button @click="editingBio = false">取消</el-button>
            <el-button type="primary" :loading="savingBio" @click="saveBio">保存</el-button>
          </div>
        </div>
        <p v-else-if="user.bio" class="bio-text">{{ user.bio }}</p>
        <el-empty v-else description="暂无个人介绍" :image-size="60" />
      </el-card>

      <!-- Stats Row -->
      <div class="stats-row">
        <el-card class="stat-card task-stats-card">
          <div class="task-stats-inner">
            <div class="ts-item"><span class="ts-val">{{ workload?.assigned_tasks ?? 0 }}</span><span class="ts-lbl">待完成</span></div>
            <div class="ts-div"></div>
            <div class="ts-item"><span class="ts-val" style="color:#E6A23C">{{ workload?.in_progress_tasks ?? 0 }}</span><span class="ts-lbl">进行中</span></div>
            <div class="ts-div"></div>
            <div class="ts-item"><span class="ts-val" style="color:#67C23A">{{ workload?.completed_tasks ?? 0 }}</span><span class="ts-lbl">已完成</span></div>
            <div class="ts-div"></div>
            <div class="ts-item"><span class="ts-val" :style="{ color: (workload?.overdue_tasks ?? 0) > 0 ? '#F56C6C' : '#303133' }">{{ workload?.overdue_tasks ?? 0 }}</span><span class="ts-lbl">已逾期</span></div>
          </div>
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
        <!-- Left: Radar Chart + Skill Editor -->
        <el-card class="radar-card">
          <template #header>
            <div class="card-header-row">
              <span>能力雷达图</span>
              <el-button v-if="canEditSkills" type="primary" link size="small" @click="openSkillEditor">
                {{ editingSkills ? '收起' : '编辑维度' }}
              </el-button>
            </div>
          </template>
          <div v-if="radarOption" class="radar-chart-wrapper">
            <v-chart :option="radarOption" autoresize class="radar-chart" />
          </div>
          <el-empty v-else :description="canEditSkills ? '暂无技能数据，请点击编辑维度添加' : '暂无技能数据'" />

          <!-- Skill Editor Panel -->
          <div v-if="editingSkills" class="skill-editor">
            <div class="skill-list">
              <div v-for="s in skills" :key="s.skill_id" class="skill-item">
                <span class="skill-name">{{ s.skill_name }}</span>
                <el-rate v-model="s.proficiency" :max="5" allow-half @change="(v: number) => updateProficiency(s.skill_id, v)" />
                <el-button type="danger" link size="small" @click="removeSkill(s.skill_id)">删除</el-button>
              </div>
            </div>
            <div class="skill-add-row">
              <el-select v-model="newSkillId" placeholder="添加技能" filterable size="small" style="flex:1">
                <el-option v-for="s in allSkills.filter(a => !skills.some(e => e.skill_id === a.id))" :key="s.id" :label="s.name + (s.category ? ' (' + s.category + ')' : '')" :value="s.id" />
              </el-select>
              <el-rate v-model="newProficiency" :max="5" style="margin:0 8px" />
              <el-button type="primary" size="small" @click="addSkill">添加</el-button>
            </div>
          </div>
        </el-card>

        <!-- Right: AI Analysis -->
        <el-card class="analysis-card">
          <template #header>
            <div class="card-header-row">
              <span>AI 分析报告</span>
              <span v-if="capability?.last_analyzed_at" class="analysis-time">{{ formatDateTime(capability.last_analyzed_at) }}</span>
            </div>
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

      <!-- Task List -->
      <el-card class="task-history-card">
        <template #header>
          <span>当前任务</span>
        </template>
        <el-table v-if="userTasks.length" :data="userTasks" stripe size="small" style="width:100%" :row-style="{ cursor: 'pointer' }" @row-click="(row: any) => $router.push('/projects/' + row.project_id + '/board')">
          <el-table-column label="任务名称" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span style="color:#409EFF">{{ row.title }}</span>
            </template>
          </el-table-column>
          <el-table-column label="所属项目" prop="project_name" min-width="160" show-overflow-tooltip />
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="(taskStatusType(row.status) as any)" size="small">{{ taskStatusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="优先级" width="70" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.priority === 'urgent'" type="danger" size="small">紧急</el-tag>
              <el-tag v-else-if="row.priority === 'high'" type="danger" size="small" effect="plain">高</el-tag>
              <span v-else style="font-size:12px;color:#909399">{{ row.priority === 'medium' ? '中' : '低' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="工时" width="60" align="center">
            <template #default="{ row }">{{ row.estimated_hours ? row.estimated_hours + 'h' : '-' }}</template>
          </el-table-column>
          <el-table-column label="截止日期" width="100">
            <template #default="{ row }">
              <span :style="{ color: row.deadline && new Date(row.deadline) < new Date() && row.status !== 'done' ? '#F56C6C' : '#909399', fontWeight: row.deadline && new Date(row.deadline) < new Date() && row.status !== 'done' ? '600' : 'normal' }">
                {{ row.deadline ? row.deadline.slice(0, 10) : '-' }}
              </span>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="暂无分配任务" />
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.personnel-detail {
  padding: 0;
  min-height: 300px;
}

.detail-toolbar {
  display: flex;
  justify-content: flex-start;
  margin-bottom: 12px;
}

.profile-header-card {
  margin-bottom: 20px;
}

.bio-card {
  margin-bottom: 20px;
}

.bio-text {
  margin: 0;
  color: #606266;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.bio-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 10px;
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

.profile-department {
  color: #909399;
  font-size: 14px;
}

.profile-actions {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}
.ai-status-text {
  font-size: 13px;
  color: #e6a23c;
  animation: pulse 1.5s infinite;
}
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.5; } }

.stats-row {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr;
  gap: 12px;
  margin-bottom: 20px;
}
.task-stats-card :deep(.el-card__body) { padding: 16px; }
.task-stats-inner { display: flex; align-items: center; justify-content: space-around; }
.ts-item { display: flex; flex-direction: column; align-items: center; }
.ts-val { font-size: 24px; font-weight: 700; color: #303133; }
.ts-lbl { font-size: 12px; color: #909399; margin-top: 2px; }
.ts-div { width: 1px; height: 32px; background: #ebeef5; }

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

.card-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.analysis-time {
  font-size: 12px;
  color: #909399;
  font-weight: normal;
}

.skill-editor {
  border-top: 1px solid #ebeef5;
  padding-top: 12px;
  margin-top: 8px;
}

.skill-list {
  margin-bottom: 12px;
}

.skill-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  border-bottom: 1px solid #f5f7fa;
}

.skill-item:last-child {
  border-bottom: none;
}

.skill-name {
  min-width: 80px;
  font-size: 13px;
  color: #303133;
}

.skill-add-row {
  display: flex;
  align-items: center;
  gap: 4px;
  padding-top: 8px;
  border-top: 1px dashed #dcdfe6;
}
</style>
