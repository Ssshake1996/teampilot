<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { usersApi } from '@/api/users'
import http from '@/api/index'
import { useAuthStore } from '@/stores/auth'
import { useUserStore } from '@/stores/user'
import type { User, UserSkill } from '@/types/models'

const router = useRouter()
const auth = useAuthStore()
const userStore = useUserStore()
const queryClient = useQueryClient()
const canAdd = computed(() => auth.can('personnel.add'))
const canEditProfile = computed(() => auth.can('personnel.edit'))
const canDeactivate = computed(() => auth.can('personnel.deactivate'))
const canManageRoles = computed(() => auth.can('system.role_manage'))

const currentPage = ref(1)

const searchText = ref('')
const filterDept = ref('')

// Add user dialog
const addDialogVisible = ref(false)
const addForm = ref({ username: '', full_name: '', password: '123456', department: '', role: 'member' })
const adding = ref(false)

// Edit user dialog
const editDialogVisible = ref(false)
const editUser = ref<User | null>(null)
const editForm = ref({ full_name: '', department: '', role: 'member' })
const savingEdit = ref(false)

const roleTagType: Record<string, string> = { admin: 'danger', manager: 'warning', member: 'info' }
const roleLabel: Record<string, string> = { admin: '管理员', manager: '经理', member: '成员' }

type PersonnelOverviewItem = {
  user: User
  skills?: UserSkill[]
  workload?: { assigned_tasks?: number; in_progress_tasks?: number }
}

const queryParams = computed(() => ({
  page: currentPage.value,
  pageSize: 100,
  search: searchText.value.trim(),
  department: filterDept.value,
}))

const usersQuery = useQuery({
  queryKey: computed(() => ['personnel', 'users', 'list', queryParams.value]),
  queryFn: async () => {
    const p = queryParams.value
    const res = await usersApi.list(p.page, p.pageSize, p.search, p.department)
    return res.data
  },
  placeholderData: (previousData) => previousData,
})

const overviewQuery = useQuery({
  queryKey: computed(() => ['personnel', 'users', 'overview', queryParams.value]),
  queryFn: async () => {
    const p = queryParams.value
    const res = await usersApi.overview({
      page: p.page,
      page_size: p.pageSize,
      search: p.search,
      department: p.department,
    })
    return res.data
  },
  enabled: computed(() => Boolean(usersQuery.data.value)),
  placeholderData: (previousData) => previousData,
})

const departmentsQuery = useQuery({
  queryKey: ['personnel', 'departments'],
  queryFn: async () => (await usersApi.departments()).data,
  placeholderData: (previousData) => previousData,
})

const availableRoles = ref<string[]>(['admin', 'manager', 'member'])
async function loadRoles() {
  if (!canManageRoles.value) return
  try {
    const res = await http.get('/permissions/roles')
    availableRoles.value = Object.keys(res.data)
  } catch {}
}

const users = computed<User[]>(() => usersQuery.data.value?.items || [])
const total = computed(() => usersQuery.data.value?.total || 0)
const overviewItems = computed(() => Array.isArray((overviewQuery.data.value as any)?.items) ? (overviewQuery.data.value as any).items : [])
const overviewByUserId = computed<Map<string, PersonnelOverviewItem>>(() => new Map(overviewItems.value.map((item: any) => {
  const user = item.user || item
  return [user.id, { ...item, user }]
})))
const departments = computed(() => {
  const fromOverview = (overviewQuery.data.value as any)?.departments
  if (Array.isArray(fromOverview) && fromOverview.length) return fromOverview
  if (departmentsQuery.data.value?.length) return departmentsQuery.data.value
  return [...new Set(users.value.map((u) => u.department).filter(Boolean) as string[])]
})
const userSkillsMap = computed<Record<string, UserSkill[]>>(() => Object.fromEntries(
  users.value.map((user) => [user.id, overviewByUserId.value.get(user.id)?.skills || []]),
))
const userTaskCountMap = computed<Record<string, number>>(() => Object.fromEntries(
  users.value.map((user) => [user.id, overviewByUserId.value.get(user.id)?.workload?.assigned_tasks ?? 0]),
))
const initialLoading = computed(() => usersQuery.isLoading.value && !users.value.length)
const isRefreshing = computed(() => usersQuery.isFetching.value || overviewQuery.isFetching.value)
const listError = computed(() => usersQuery.error.value as any)
const overviewError = computed(() => overviewQuery.error.value as any)
const dataUpdatedLabel = computed(() => {
  const updatedAt = Math.max(usersQuery.dataUpdatedAt.value || 0, overviewQuery.dataUpdatedAt.value || 0)
  return updatedAt ? new Date(updatedAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : ''
})

async function refreshPersonnel() {
  await queryClient.invalidateQueries({ queryKey: ['personnel'] })
}

function handleSearch() { currentPage.value = 1; refreshPersonnel() }
function handleDeptFilter() { currentPage.value = 1; refreshPersonnel() }

// Group users by department
const groupedUsers = computed(() => {
  const groups: Record<string, typeof users.value> = {}
  for (const u of users.value) {
    const dept = (u as any).department || '未分组'
    if (!groups[dept]) groups[dept] = []
    groups[dept].push(u)
  }
  // Sort: put "未分组" last
  const sorted: { dept: string; members: typeof users.value }[] = []
  for (const [dept, members] of Object.entries(groups)) {
    if (dept !== '未分组') sorted.push({ dept, members })
  }
  if (groups['未分组']) sorted.push({ dept: '未分组', members: groups['未分组'] })
  return sorted
})

function navigateToDetail(id: string) { router.push('/personnel/' + id) }

async function handleAdd() {
  if (!addForm.value.username.trim() || !addForm.value.full_name.trim()) {
    ElMessage.warning('请填写用户名和姓名'); return
  }
  adding.value = true
  try {
    const payload = { ...addForm.value }
    if (!canManageRoles.value) payload.role = 'member'
    await http.post('/users', payload)
    ElMessage.success('人员已添加')
    addDialogVisible.value = false
    addForm.value = { username: '', full_name: '', password: '123456', department: '', role: 'member' }
    userStore.invalidate()
    await refreshPersonnel()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '添加失败')
  } finally { adding.value = false }
}

function openEditDialog(user: User) {
  editUser.value = user
  editForm.value = {
    full_name: user.full_name || '',
    department: user.department || '',
    role: user.role || 'member',
  }
  editDialogVisible.value = true
}

async function handleSaveEdit() {
  if (!editUser.value) return
  if (!editForm.value.full_name.trim()) {
    ElMessage.warning('请填写姓名'); return
  }
  savingEdit.value = true
  try {
    const payload: any = {}
    if (canEditProfile.value) {
      payload.full_name = editForm.value.full_name.trim()
      payload.department = editForm.value.department || null
    }
    if (canManageRoles.value) payload.role = editForm.value.role
    await usersApi.update(editUser.value.id, payload)
    ElMessage.success('人员信息已更新')
    editDialogVisible.value = false
    userStore.invalidate(editUser.value.id)
    await refreshPersonnel()
    if (editUser.value.id === auth.user?.id) await auth.fetchUser()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally { savingEdit.value = false }
}

async function handleDeactivate(user: User) {
  try {
    await ElMessageBox.confirm(`删除/停用 ${user.full_name}？该用户将无法登录，历史数据会保留。`, '确认删除', { type: 'warning' })
    await http.delete('/users/' + user.id)
    ElMessage.success('已删除/停用')
    userStore.invalidate(user.id)
    await refreshPersonnel()
  } catch {}
}

onMounted(async () => {
  if (canManageRoles.value) await loadRoles()
})
</script>

<template>
  <div class="pl">
    <!-- Header -->
    <div class="pl-hd">
      <h2>人员管理</h2>
      <div class="pl-actions">
        <el-input v-model="searchText" placeholder="搜索姓名/用户名" clearable style="width:200px" size="default" @clear="handleSearch" @keyup.enter="handleSearch">
          <template #prefix><span style="color:#909399">搜</span></template>
        </el-input>
        <el-select v-model="filterDept" placeholder="全部分组" clearable style="width:140px" @change="handleDeptFilter">
          <el-option v-for="d in departments" :key="d" :label="d" :value="d" />
        </el-select>
        <el-button :loading="isRefreshing" @click="refreshPersonnel">刷新</el-button>
        <el-button v-if="canAdd" type="primary" @click="addDialogVisible = true">添加人员</el-button>
      </div>
    </div>

    <div class="data-status">
      <span v-if="dataUpdatedLabel">上次更新 {{ dataUpdatedLabel }}</span>
      <span v-if="isRefreshing">正在后台刷新</span>
      <span v-if="overviewError && users.length">概览数据暂不可用，已保留人员列表</span>
    </div>
    <el-alert
      v-if="listError && !users.length"
      type="error"
      :closable="false"
      show-icon
      :title="listError?.response?.data?.detail || listError?.message || '人员列表加载失败'"
      style="margin-bottom:12px"
    />

    <!-- Grouped Table -->
    <div v-loading="initialLoading">
      <div v-for="group in groupedUsers" :key="group.dept" class="dept-group">
        <div class="dept-hd">
          <span class="dept-name">{{ group.dept }}</span>
          <el-badge :value="group.members.length" type="info" />
        </div>
        <el-table :data="group.members" size="small" style="width:100%">
          <el-table-column label="姓名" min-width="160">
            <template #default="{ row }">
              <div class="u-cell" @click="navigateToDetail(row.id)">
                <el-avatar :size="30">{{ row.full_name?.charAt(0) }}</el-avatar>
                <span class="u-name">{{ row.full_name }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="角色" width="110">
            <template #default="{ row }">
              <el-tag :type="(roleTagType[row.role] as any) || 'info'" size="small">{{ roleLabel[row.role] || row.role }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="技能" min-width="200">
            <template #default="{ row }">
              <div class="sk-cell">
                <el-tag v-for="s in (userSkillsMap[row.id] || []).slice(0, 4)" :key="s.skill_id" size="small" type="success" class="sk-tag">{{ s.skill_name }}</el-tag>
                <el-tag v-if="(userSkillsMap[row.id] || []).length > 4" size="small" type="info">+{{ (userSkillsMap[row.id] || []).length - 4 }}</el-tag>
                <span v-if="!(userSkillsMap[row.id] || []).length" class="no-sk">-</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="任务" width="60" align="center">
            <template #default="{ row }">{{ userTaskCountMap[row.id] ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="180" align="center">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="navigateToDetail(row.id)">详情</el-button>
              <el-button v-if="canEditProfile || canManageRoles" type="primary" link size="small" @click="openEditDialog(row)">编辑</el-button>
              <el-button v-if="canDeactivate && row.id !== auth.user?.id" type="danger" link size="small" @click="handleDeactivate(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <el-empty v-if="!groupedUsers.length && !initialLoading && !listError" description="暂无人员" />
    </div>

    <!-- Add User Dialog -->
    <el-dialog v-model="addDialogVisible" title="添加人员" width="480px">
      <el-form label-width="80px">
        <el-form-item label="用户名"><el-input v-model="addForm.username" placeholder="登录用户名" /></el-form-item>
        <el-form-item label="姓名"><el-input v-model="addForm.full_name" placeholder="显示名称" /></el-form-item>
        <el-form-item label="初始密码"><el-input v-model="addForm.password" placeholder="默认 123456" /></el-form-item>
        <el-form-item label="分组">
          <el-select v-model="addForm.department" placeholder="选择或输入" filterable allow-create style="width:100%">
            <el-option v-for="d in departments" :key="d" :label="d" :value="d" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="canManageRoles" label="角色">
          <el-select v-model="addForm.role" filterable allow-create style="width:100%">
            <el-option v-for="r in availableRoles" :key="r" :label="r" :value="r" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="adding" @click="handleAdd">添加</el-button>
      </template>
    </el-dialog>

    <!-- Edit User Dialog -->
    <el-dialog v-model="editDialogVisible" :title="'编辑人员 — ' + (editUser?.full_name || '')" width="480px">
      <el-form label-width="80px">
        <el-form-item label="姓名"><el-input v-model="editForm.full_name" :disabled="!canEditProfile" placeholder="显示名称" /></el-form-item>
        <el-form-item label="分组">
          <el-select v-model="editForm.department" :disabled="!canEditProfile" placeholder="选择或输入" filterable allow-create clearable style="width:100%">
            <el-option v-for="d in departments" :key="d" :label="d" :value="d" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="canManageRoles" label="角色">
          <el-select v-model="editForm.role" filterable style="width:100%">
            <el-option v-for="r in availableRoles" :key="r" :label="roleLabel[r] || r" :value="r" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingEdit" @click="handleSaveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.pl { padding: 0; }
.pl-hd { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.pl-hd h2 { margin: 0; font-size: 20px; font-weight: 600; color: #303133; }
.pl-actions { display: flex; gap: 8px; align-items: center; }
.data-status { min-height: 20px; display: flex; align-items: center; gap: 12px; margin: -8px 0 10px; font-size: 12px; color: #909399; }

.dept-group { margin-bottom: 16px; background: #fff; border-radius: 6px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
.dept-hd { display: flex; align-items: center; gap: 8px; padding: 10px 16px; background: #f5f7fa; border-bottom: 1px solid #ebeef5; font-weight: 600; font-size: 13px; color: #303133; }
.dept-name { }

.u-cell { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.u-name { color: #409EFF; font-weight: 500; font-size: 13px; }
.u-cell:hover .u-name { text-decoration: underline; }

.sk-cell { display: flex; flex-wrap: wrap; gap: 3px; }
.sk-tag { margin: 0; }
.no-sk { color: #c0c4cc; font-size: 12px; }
</style>
