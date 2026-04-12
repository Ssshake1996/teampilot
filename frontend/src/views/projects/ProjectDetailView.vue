<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Plus } from '@element-plus/icons-vue'
import { projectsApi } from '@/api/projects'
import { usersApi } from '@/api/users'
import type { Project, ProjectMember, User } from '@/types/models'
import { ProjectStatus } from '@/types/enums'

const route = useRoute()
const router = useRouter()
const projectId = route.params.id as string

const project = ref<Project | null>(null)
const members = ref<ProjectMember[]>([])
const allUsers = ref<User[]>([])
const activeTab = ref('board')
const loading = ref(false)

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
  [ProjectStatus.PAUSED]: 'warning',
  [ProjectStatus.COMPLETED]: '',
  [ProjectStatus.ARCHIVED]: 'danger',
}

const statusLabel: Record<string, string> = {
  [ProjectStatus.PLANNING]: '规划中',
  [ProjectStatus.ACTIVE]: '进行中',
  [ProjectStatus.PAUSED]: '已暂停',
  [ProjectStatus.COMPLETED]: '已完成',
  [ProjectStatus.ARCHIVED]: '已归档',
}

const roleLabel: Record<string, string> = {
  owner: '负责人',
  admin: '管理员',
  member: '成员',
}

async function fetchProject() {
  loading.value = true
  try {
    const res = await projectsApi.get(projectId)
    project.value = res.data
  } catch {
    ElMessage.error('加载项目信息失败')
  } finally {
    loading.value = false
  }
}

async function fetchMembers() {
  try {
    const res = await projectsApi.getMembers(projectId)
    members.value = res.data
  } catch {
    ElMessage.error('加载成员列表失败')
  }
}

async function fetchUsers() {
  try {
    const res = await usersApi.list(1, 100)
    allUsers.value = res.data.items
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
          <el-button @click="router.push('/projects')">返回列表</el-button>
        </div>
      </div>
      <p class="project-description">{{ project.description || '暂无项目描述' }}</p>

      <!-- Tabs -->
      <el-tabs v-model="activeTab" @tab-click="handleTabClick">
        <el-tab-pane label="看板" name="board">
          <div class="tab-placeholder">
            <el-button type="primary" @click="router.push(`/projects/${projectId}/board`)">
              进入看板视图
            </el-button>
          </div>
        </el-tab-pane>

        <el-tab-pane label="列表" name="list">
          <div class="tab-placeholder">
            <el-button type="primary" @click="router.push(`/projects/${projectId}/tasks`)">
              进入列表视图
            </el-button>
          </div>
        </el-tab-pane>

        <el-tab-pane label="成员" name="members">
          <div class="members-section">
            <div class="members-header">
              <span class="members-title">项目成员 ({{ members.length }})</span>
              <el-button type="primary" :icon="Plus" size="small" @click="openAddMemberDialog">
                添加成员
              </el-button>
            </div>

            <el-table :data="members" stripe style="width: 100%">
              <el-table-column prop="full_name" label="姓名" min-width="150" />
              <el-table-column prop="role_in_project" label="角色" width="120">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.role_in_project === 'owner' ? 'danger' : 'info'">
                    {{ roleLabel[row.role_in_project] || row.role_in_project }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="100" align="center">
                <template #default="{ row }">
                  <el-button
                    v-if="row.role_in_project !== 'owner'"
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

            <el-empty v-if="members.length === 0" description="暂无成员" />
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
            <el-option label="管理员" value="admin" />
            <el-option label="成员" value="member" />
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
  padding: 20px;
}

.project-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-left h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
}

.project-description {
  color: #606266;
  font-size: 14px;
  margin: 0 0 24px 0;
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
</style>
