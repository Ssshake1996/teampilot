<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { usersApi } from '@/api/users'
import http from '@/api/index'
import { useAuthStore } from '@/stores/auth'
import type { User, UserSkill } from '@/types/models'
import { UserRole } from '@/types/enums'

const router = useRouter()
const auth = useAuthStore()
const canEdit = computed(() => auth.user?.role === 'admin')

const users = ref<User[]>([])
const total = ref(0)
const currentPage = ref(1)
const loading = ref(false)

const searchText = ref('')
const filterDept = ref('')
const departments = ref<string[]>([])
const userSkillsMap = ref<Record<string, UserSkill[]>>({})
const userTaskCountMap = ref<Record<string, number>>({})

// Add user dialog
const addDialogVisible = ref(false)
const addForm = ref({ username: '', full_name: '', email: '', password: '123456', department: '', role: 'member' })
const adding = ref(false)

const roleTagType: Record<string, string> = { admin: 'danger', manager: 'warning', member: 'info' }
const roleLabel: Record<string, string> = { admin: '管理员', manager: '经理', member: '成员' }

async function loadDepartments() {
  try {
    const res = await http.get('/users/departments')
    departments.value = res.data
  } catch {}
}

async function loadUsers() {
  loading.value = true
  try {
    const res = await usersApi.list(currentPage.value, 50)
    // Client-side filter (backend also supports it, but for instant feedback)
    let items = res.data.items as (User & { department?: string })[]
    if (searchText.value) {
      const s = searchText.value.toLowerCase()
      items = items.filter(u => u.full_name?.toLowerCase().includes(s) || u.username?.toLowerCase().includes(s))
    }
    if (filterDept.value) {
      items = items.filter(u => (u as any).department === filterDept.value)
    }
    users.value = items
    total.value = items.length

    // Load skills & workload in parallel (only for visible users)
    await Promise.allSettled(items.map(async u => {
      try { userSkillsMap.value[u.id] = (await usersApi.getSkills(u.id)).data } catch { userSkillsMap.value[u.id] = [] }
      try { userTaskCountMap.value[u.id] = ((await usersApi.getWorkload(u.id)).data as any).assigned_tasks ?? 0 } catch { userTaskCountMap.value[u.id] = 0 }
    }))
  } finally { loading.value = false }
}

function handleSearch() { currentPage.value = 1; loadUsers() }
function handleDeptFilter() { currentPage.value = 1; loadUsers() }

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
    await http.post('/users', addForm.value)
    ElMessage.success('人员已添加')
    addDialogVisible.value = false
    addForm.value = { username: '', full_name: '', email: '', password: '123456', department: '', role: 'member' }
    await loadDepartments()
    await loadUsers()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '添加失败')
  } finally { adding.value = false }
}

async function handleDeactivate(user: User) {
  try {
    await ElMessageBox.confirm(`停用 ${user.full_name}？停用后不可登录，数据保留。`, '确认停用', { type: 'warning' })
    await http.delete('/users/' + user.id)
    ElMessage.success('已停用')
    await loadUsers()
  } catch {}
}

onMounted(async () => {
  await loadDepartments()
  await loadUsers()
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
        <el-button v-if="canEdit" type="primary" @click="addDialogVisible = true">添加人员</el-button>
      </div>
    </div>

    <!-- Grouped Table -->
    <div v-loading="loading">
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
          <el-table-column label="角色" width="90">
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
          <el-table-column label="操作" width="140" align="center">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="navigateToDetail(row.id)">详情</el-button>
              <el-button v-if="canEdit && row.id !== auth.user?.id" type="danger" link size="small" @click="handleDeactivate(row)">停用</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <el-empty v-if="!groupedUsers.length && !loading" description="暂无人员" />
    </div>

    <!-- Add User Dialog -->
    <el-dialog v-model="addDialogVisible" title="添加人员" width="480px">
      <el-form label-width="80px">
        <el-form-item label="用户名"><el-input v-model="addForm.username" placeholder="登录用户名" /></el-form-item>
        <el-form-item label="姓名"><el-input v-model="addForm.full_name" placeholder="显示名称" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="addForm.email" placeholder="可选" /></el-form-item>
        <el-form-item label="初始密码"><el-input v-model="addForm.password" placeholder="默认 123456" /></el-form-item>
        <el-form-item label="分组">
          <el-select v-model="addForm.department" placeholder="选择或输入" filterable allow-create style="width:100%">
            <el-option v-for="d in departments" :key="d" :label="d" :value="d" />
          </el-select>
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="addForm.role" style="width:100%">
            <el-option label="成员" value="member" />
            <el-option label="经理" value="manager" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="adding" @click="handleAdd">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.pl { padding: 0; }
.pl-hd { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.pl-hd h2 { margin: 0; font-size: 20px; font-weight: 600; color: #303133; }
.pl-actions { display: flex; gap: 8px; align-items: center; }

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
