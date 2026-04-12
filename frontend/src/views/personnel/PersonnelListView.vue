<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { usersApi } from '@/api/users'
import type { User, UserSkill } from '@/types/models'
import { UserRole } from '@/types/enums'

const router = useRouter()

const users = ref<User[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const loading = ref(false)

const userSkillsMap = ref<Record<string, UserSkill[]>>({})
const userTaskCountMap = ref<Record<string, number>>({})

const roleTagType: Record<string, 'danger' | 'warning' | 'info' | 'success' | 'primary'> = {
  [UserRole.ADMIN]: 'danger',
  [UserRole.MANAGER]: 'warning',
  [UserRole.MEMBER]: 'info',
}

const roleLabel: Record<string, string> = {
  [UserRole.ADMIN]: '管理员',
  [UserRole.MANAGER]: '经理',
  [UserRole.MEMBER]: '成员',
}

async function loadUsers() {
  loading.value = true
  try {
    const res = await usersApi.list(currentPage.value, pageSize.value)
    users.value = res.data.items
    total.value = res.data.total

    const skillPromises = users.value.map(async (user) => {
      try {
        const skillRes = await usersApi.getSkills(user.id)
        userSkillsMap.value[user.id] = skillRes.data
      } catch {
        userSkillsMap.value[user.id] = []
      }
    })

    const workloadPromises = users.value.map(async (user) => {
      try {
        const wlRes = await usersApi.getWorkload(user.id)
        userTaskCountMap.value[user.id] = (wlRes.data as { assigned_tasks: number }).assigned_tasks ?? 0
      } catch {
        userTaskCountMap.value[user.id] = 0
      }
    })

    await Promise.allSettled([...skillPromises, ...workloadPromises])
  } finally {
    loading.value = false
  }
}

function handlePageChange(page: number) {
  currentPage.value = page
  loadUsers()
}

function navigateToDetail(id: string) {
  router.push(`/personnel/${id}`)
}

onMounted(() => {
  loadUsers()
})
</script>

<template>
  <div class="personnel-list">
    <div class="page-header">
      <h2>人员管理</h2>
    </div>

    <el-table v-loading="loading" :data="users" stripe style="width: 100%">
      <el-table-column label="姓名" min-width="200">
        <template #default="{ row }">
          <div class="user-cell" @click="navigateToDetail(row.id)">
            <el-avatar :size="36" :src="row.avatar_url || undefined">
              {{ row.full_name?.charAt(0) || row.username?.charAt(0) }}
            </el-avatar>
            <span class="user-name">{{ row.full_name || row.username }}</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="角色" width="120">
        <template #default="{ row }">
          <el-tag :type="roleTagType[row.role] || 'info'" size="small">
            {{ roleLabel[row.role] || row.role }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="技能" min-width="250">
        <template #default="{ row }">
          <div class="skills-cell">
            <template v-if="userSkillsMap[row.id]?.length">
              <el-tag
                v-for="skill in userSkillsMap[row.id].slice(0, 4)"
                :key="skill.skill_id"
                size="small"
                type="success"
                class="skill-tag"
              >
                {{ skill.skill_name }}
              </el-tag>
              <el-tag
                v-if="userSkillsMap[row.id].length > 4"
                size="small"
                type="info"
              >
                +{{ userSkillsMap[row.id].length - 4 }}
              </el-tag>
            </template>
            <span v-else class="no-skills">暂无技能</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="当前任务数" width="120" align="center">
        <template #default="{ row }">
          <span>{{ userTaskCountMap[row.id] ?? '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="150" align="center">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="navigateToDetail(row.id)">
            查看详情
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-wrapper">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="handlePageChange"
      />
    </div>
  </div>
</template>

<style scoped>
.personnel-list {
  padding: 0;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.user-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}

.user-name {
  color: #409eff;
  font-weight: 500;
}

.user-cell:hover .user-name {
  text-decoration: underline;
}

.skills-cell {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.skill-tag {
  margin: 0;
}

.no-skills {
  color: #c0c4cc;
  font-size: 13px;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
