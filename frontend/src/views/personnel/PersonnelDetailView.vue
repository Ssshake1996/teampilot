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
import { usersApi } from '@/api/users'

import { skillsApi } from '@/api/skills'
import { useAuthStore } from '@/stores/auth'
import { useUserStore } from '@/stores/user'
import type { User, UserSkill, CapabilityProfile } from '@/types/models'
import { UserRole } from '@/types/enums'

use([CanvasRenderer, RadarChart, TitleComponent, TooltipComponent, RadarComponent])

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const userStore = useUserStore()
const userId = computed(() => route.params.id as string)
const canEditSkills = computed(() => auth.can('personnel.edit_skills'))

const canEditBio = computed(() => auth.user?.id === userId.value || auth.can('personnel.edit'))

const user = ref<User | null>(null)
const skills = ref<UserSkill[]>([])
const capability = ref<CapabilityProfile | null>(null)
const workload = ref<any>(null)
const userTasks = ref<any[]>([])
const loading = ref(false)
const loadError = ref('')
const updatedAt = ref('')
const savingSkills = ref(false)
const skillOptionsError = ref('')

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

async function loadData(force = false) {
  loading.value = true
  loadError.value = ''
  try {
    const data = await userStore.fetchDetailBundle(userId.value, force)
    user.value = data.user
    bioDraft.value = data.user?.bio || ''
    skills.value = data.skills || []
    capability.value = data.capability || null
    workload.value = data.workload || null
    userTasks.value = data.tasks || []
    updatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } catch (error: any) {
    loadError.value = error?.response?.data?.detail || '人员详情读取失败，请重试'
  } finally {
    loading.value = false
  }
}

async function refreshData() { userStore.invalidate(userId.value); await loadData(true) }

async function loadAllSkills() {
  skillOptionsError.value = ''
  try {
    const res = await skillsApi.list()
    allSkills.value = res.data
  } catch { skillOptionsError.value = '技能选项读取失败，请重试' }
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
  if (await saveSkills(updated)) { newSkillId.value = ''; newProficiency.value = 3 }
}

async function updateProficiency(skillId: string, val: number) {
  const updated = skills.value.map(s => s.skill_id === skillId ? { ...s, proficiency: val } : s)
  await saveSkills(updated)
}

async function saveSkills(updatedSkills: UserSkill[]) {
  if (savingSkills.value) return false
  savingSkills.value = true
  try {
    await usersApi.updateSkills(userId.value, updatedSkills.map(s => ({ skill_id: s.skill_id, proficiency: s.proficiency })))
    await refreshData()
    ElMessage.success('技能已更新')
    return true
  } catch {
    ElMessage.error('技能更新失败，请重试')
    return false
  } finally { savingSkills.value = false }
}

function openBioEditor() {
  bioDraft.value = user.value?.bio || ''
  editingBio.value = true
}

async function saveBio() {
  if (!user.value || savingBio.value) return
  savingBio.value = true
  try {
    const res = await usersApi.update(userId.value, { bio: bioDraft.value.trim() || null })
    user.value = res.data
    bioDraft.value = res.data.bio || ''
    editingBio.value = false
    userStore.invalidate(userId.value)
    ElMessage.success('个人介绍已保存')
    if (auth.user?.id === userId.value) await auth.fetchUser()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    savingBio.value = false
  }
}


function formatDateTime(d: string | null) { return d ? d.replace('T', ' ').slice(0, 16) : '' }
function taskStatusLabel(s: string) { return ({ not_started: '待开始', in_progress: '进行中', done: '已完成' } as any)[s] || s }
function taskDetailLink(task: any) { return { path: `/projects/${task.project_id}/board`, query: { taskId: task.id, from: route.fullPath } } }
function taskStatusType(s: string) { return ({ not_started: 'info', in_progress: 'warning', done: 'success' } as any)[s] || 'info' }

onMounted(() => {
  loadData()
})
</script>

<template>
  <div v-loading="loading" class="personnel-detail">
    <div class="detail-toolbar"><el-button @click="router.push('/personnel')">返回人员列表</el-button><el-button :loading="loading" :disabled="editingBio || savingSkills" @click="refreshData">刷新详情</el-button><span v-if="updatedAt">读取于 {{ updatedAt }}</span></div>
    <el-alert v-if="loadError" type="error" :closable="false" show-icon :title="loadError + (user ? '，下方保留上次数据' : '')"><el-button link @click="refreshData">重试</el-button></el-alert>
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
              <span v-if="user.department" class="profile-department">{{ user.department }}</span>
            </div>
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
            placeholder="填写擅长领域、项目经验、偏好的工作类型、当前限制等，用于工作安排参考。"
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
          <div v-if="editingSkills" v-loading="savingSkills" class="skill-editor">
            <div class="skill-list">
              <div v-for="s in skills" :key="s.skill_id" class="skill-item">
                <span class="skill-name">{{ s.skill_name }}</span>
                <el-rate v-model="s.proficiency" :max="5" allow-half @change="(v: number) => updateProficiency(s.skill_id, v)" />
                <el-button type="danger" link size="small" @click="removeSkill(s.skill_id)">删除</el-button>
              </div>
            </div>
            <p v-if="skillOptionsError" role="alert" class="options-error">{{ skillOptionsError }} <el-button link @click="loadAllSkills">重试</el-button></p><div class="skill-add-row">
              <el-select v-model="newSkillId" placeholder="添加技能" filterable size="small" style="flex:1">
                <el-option v-for="s in allSkills.filter(a => !skills.some(e => e.skill_id === a.id))" :key="s.id" :label="s.name + (s.category ? ' (' + s.category + ')' : '')" :value="s.id" />
              </el-select>
              <el-rate v-model="newProficiency" :max="5" style="margin:0 8px" />
              <el-button type="primary" :loading="savingSkills" size="small" @click="addSkill">添加</el-button>
            </div>
          </div>
        </el-card>

      </div>

      <!-- Task List -->
      <el-card class="task-history-card">
        <template #header>
          <span>当前任务</span>
        </template>
        <el-table v-if="userTasks.length" class="detail-task-table" :data="userTasks" stripe size="small" style="width:100%">
          <el-table-column label="任务名称" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <RouterLink class="task-detail-link" :to="taskDetailLink(row)">{{ row.title }}</RouterLink>
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
        <ul v-if="userTasks.length" class="detail-task-cards"><li v-for="task in userTasks" :key="task.id"><RouterLink :to="taskDetailLink(task)"><strong>{{ task.title }}</strong><span>{{ task.project_name }}</span><span>{{ taskStatusLabel(task.status) }} · 截止 {{ task.deadline ? task.deadline.slice(0, 10) : '未设置' }}</span></RouterLink></li></ul>
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
  align-items:center;
  flex-wrap:wrap;
  gap:8px;
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
  grid-template-columns: minmax(0, 1fr);
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

.task-history-card {
  margin-bottom: 20px;
}

.card-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
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
.detail-toolbar span { font-size:12px; color:var(--muted); }.options-error { color:#b83d43; font-size:13px; }.task-detail-link { color:var(--brand); text-decoration:underline; text-underline-offset:3px; }.detail-task-cards { display:none; list-style:none; padding:0; }.detail-task-cards li { border-bottom:1px solid var(--border); }.detail-task-cards a { display:flex; flex-direction:column; gap:8px; padding:12px 0; font-size:13px; }.detail-task-cards strong { font-size:14px; color:var(--brand); }.detail-task-cards span { color:var(--muted); }
@media (max-width:760px) { .stats-row { grid-template-columns:repeat(2,minmax(0,1fr)); }.task-stats-card { grid-column:1/-1; }.profile-header { gap:12px; }.profile-info { min-width:0; }.profile-name { font-size:20px; overflow-wrap:anywhere; }.profile-meta,.skill-add-row,.card-header-row { flex-wrap:wrap; gap:8px; }.skill-add-row .el-select { flex-basis:100% !important; }.detail-task-table { display:none; }.detail-task-cards { display:block; }.radar-chart { height:280px; }.skill-item { flex-wrap:wrap; } }
</style>
