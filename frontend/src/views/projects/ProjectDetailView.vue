<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Plus } from '@element-plus/icons-vue'
import { projectsApi } from '@/api/projects'
import { usersApi } from '@/api/users'
import { fetchAllPages } from '@/utils/pagination'
import { useProjectUpdates } from '@/composables/useProjectUpdates'
import { useAuthStore } from '@/stores/auth'
import type { Project, ProjectMember, User } from '@/types/models'
import { ProjectStatus } from '@/types/enums'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const projectId = route.params.id as string
const canManageMembers = computed(() => auth.can('project.member.manage'))

const project = ref<Project | null>(null)
const members = ref<ProjectMember[]>([])
const allUsers = ref<User[]>([])
const activeTab = ref('members')
useProjectUpdates(async pid => { if (!pid || pid === projectId) await Promise.all([fetchProject(), fetchMembers()]) })
const loading = ref(false)
const projectError = ref('')
const membersError = ref('')

// Add member dialog
const addMemberVisible = ref(false)
const addMemberForm = ref({
  userId: '',
  role: 'member',
})
const addingMember = ref(false)

const statusTagType: Record<string, string> = {
  [ProjectStatus.PLANNING]: 'info',
  [ProjectStatus.ACTIVE]: 'success',
  [ProjectStatus.COMPLETED]: '',
  [ProjectStatus.ARCHIVED]: 'danger',
}

const statusLabel: Record<string, string> = {
  [ProjectStatus.PLANNING]: '规划中',
  [ProjectStatus.ACTIVE]: '进行中',
  [ProjectStatus.COMPLETED]: '已完成',
  [ProjectStatus.ARCHIVED]: '已归档',
}

const roleLabel: Record<string, string> = {
  lead: '接口人',
  member: '成员',
  observer: '观察者',
}

async function fetchProject() {
  loading.value = true
  projectError.value = ''
  try {
    const res = await projectsApi.get(projectId)
    project.value = res.data
  } catch {
    projectError.value = '加载项目信息失败，请重试。'
  } finally {
    loading.value = false
  }
}

async function fetchMembers() {
  membersError.value = ''
  try {
    const res = await projectsApi.getMembers(projectId)
    members.value = res.data
  } catch {
    membersError.value = '加载成员列表失败，请重试。'
  }
}

async function fetchUsers() {
  try {
    allUsers.value = await fetchAllPages(page => usersApi.list(page, 500))
  } catch {
    ElMessage.error('加载用户列表失败')
  }
}

function handleTabClick(tab: any) {
  const name = tab.paneName || tab.props?.name
  if (name === 'board') {
    router.push(`/projects/${projectId}/board`)
  } else if (name === 'list') {
    router.push(`/projects/${projectId}/tasks`)
  }
}

function openAddMemberDialog() {
  addMemberForm.value = { userId: '', role: 'member' }
  addMemberVisible.value = true
}

async function handleAddMember() {
  if (!addMemberForm.value.userId) {
    ElMessage.warning('请选择用户')
    return
  }
  addingMember.value = true
  try {
    await projectsApi.addMember(projectId, addMemberForm.value.userId, addMemberForm.value.role)
    ElMessage.success('成员添加成功')
    addMemberVisible.value = false
    await fetchMembers()
  } catch {
    ElMessage.error('添加成员失败')
  } finally {
    addingMember.value = false
  }
}

async function handleRemoveMember(userId: string, name: string) {
  try {
    await ElMessageBox.confirm(`确定要移除成员 "${name}" 吗？`, '确认移除', {
      type: 'warning',
    })
    await projectsApi.removeMember(projectId, userId)
    ElMessage.success('成员已移除')
    await fetchMembers()
  } catch {
    // cancelled or error
  }
}

function availableUsers() {
  const memberIds = new Set(members.value.map((m) => m.user_id))
  return allUsers.value.filter((u) => !memberIds.has(u.id))
}

onMounted(async () => {
  await fetchProject()
  await Promise.all([fetchMembers(), fetchUsers()])
})
</script>

<template>
  <div v-loading="loading" class="project-detail-view">
    <el-alert v-if="projectError" type="error" :closable="false" show-icon :title="projectError"><el-button link @click="fetchProject">重试</el-button></el-alert>
    <template v-if="project">
      <!-- Project Header -->
      <div class="project-header">
        <div class="header-left">
          <h2>{{ project.name }}</h2>
          <el-tag :type="(statusTagType[project.status] as any)" size="default">
            {{ statusLabel[project.status] || project.status }}
          </el-tag>
        </div>
        <div class="header-actions">
          <el-button type="primary" plain @click="router.push({ path: '/management', query: { project_id: projectId } })">团队协作工作台</el-button>
          <el-button @click="router.push('/projects')">返回列表</el-button>
        </div>
      </div>
      <div class="project-overview">
        <div class="project-section project-basic-section">
          <h3>基本信息</h3>
          <div class="project-basic-grid">
            <span>创建人</span>
            <strong>{{ project.owner_name || '-' }}</strong>
            <span>接口人</span>
            <strong>{{ project.contact_names?.join('、') || project.owner_name || '-' }}</strong>
            <span>项目成员数</span>
            <strong>{{ project.member_count }}</strong>
            <span>任务完成率</span>
            <strong>{{ project.completed_count }}/{{ project.task_count }}（已完成任务 / 全部任务）</strong>
          </div>
        </div>
        <div class="project-section">
          <h3>项目目标</h3>
          <p class="project-text">{{ project.goal || '暂无项目目标' }}</p>
        </div>
        <div class="project-section">
          <h3>项目描述</h3>
          <p class="project-text">{{ project.description || '暂无项目描述' }}</p>
        </div>
      </div>

      <!-- Tabs -->
      <el-tabs v-model="activeTab" @tab-click="handleTabClick">
        <el-tab-pane label="看板" name="board" />
        <el-tab-pane label="列表" name="list" />

        <el-tab-pane label="成员" name="members">
          <div class="members-section">
            <div class="members-header">
              <span class="members-title">项目成员 ({{ members.length }})</span>
              <el-button v-if="canManageMembers" type="primary" :icon="Plus" size="small" @click="openAddMemberDialog">
                添加成员
              </el-button>
            </div>

            <el-alert v-if="membersError" type="error" :closable="false" :title="membersError"><el-button link @click="fetchMembers">重试</el-button></el-alert>
            <el-table :data="members" stripe style="width: 100%">
              <el-table-column prop="full_name" label="姓名" min-width="150" />
              <el-table-column prop="role_in_project" label="角色" width="120">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.role_in_project === 'lead' ? 'danger' : 'info'">
                    {{ roleLabel[row.role_in_project] || row.role_in_project }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="100" align="center">
                <template #default="{ row }">
                  <el-button
                    v-if="canManageMembers && row.role_in_project !== 'lead'"
                    type="danger"
                    :icon="Delete"
                    size="small"
                    link
                    @click="handleRemoveMember(row.user_id, row.full_name)"
                  >
                    移除
                  </el-button>
                  <span v-else class="owner-label">-</span>
                </template>
              </el-table-column>
            </el-table>

            <el-empty v-if="members.length === 0 && !membersError" description="暂无成员" />
          </div>
        </el-tab-pane>
      </el-tabs>
    </template>

    <!-- Add Member Dialog -->
    <el-dialog
      v-model="addMemberVisible"
      title="添加成员"
      width="420px"
      :close-on-click-modal="false"
    >
      <el-form label-width="70px">
        <el-form-item label="用户">
          <el-select
            v-model="addMemberForm.userId"
            placeholder="选择用户"
            filterable
            style="width: 100%"
          >
            <el-option
              v-for="user in availableUsers()"
              :key="user.id"
              :label="user.full_name"
              :value="user.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="addMemberForm.role" style="width: 100%">
            <el-option label="接口人" value="lead" />
            <el-option label="成员" value="member" />
            <el-option label="观察者" value="observer" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addMemberVisible = false">取消</el-button>
        <el-button type="primary" :loading="addingMember" @click="handleAddMember">确认添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.project-detail-view {
  padding: 0;
}

.project-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
  flex-wrap: wrap;
}

.header-left h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.project-overview {
  display: grid;
  gap: 12px;
  margin: 0 0 24px 0;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.project-section {
  padding: 16px 0;
  border-bottom: 1px solid var(--border);
}

.project-section h3 {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.project-basic-grid {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
  gap: 8px 12px;
  font-size: 13px;
  color: #909399;
}

.project-basic-grid strong {
  color: #303133;
  font-weight: 600;
}

.project-text {
  color: #606266;
  font-size: 14px;
  line-height: 1.7;
  margin: 0;
  white-space: pre-wrap;
}

.tab-placeholder {
  padding: 40px;
  text-align: center;
}

.members-section {
  padding: 8px 0;
}

.members-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.members-title {
  font-size: 15px;
  font-weight: 600;
}

.owner-label {
  color: #c0c4cc;
}
@media (max-width: 900px) { .project-overview { grid-template-columns: 1fr; gap: 0; } }
</style>
