<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { aiApi } from '@/api/ai'
import { usersApi } from '@/api/users'
import { skillsApi } from '@/api/skills'
import { useAuthStore } from '@/stores/auth'
import type { User, Skill } from '@/types/models'
import { UserRole } from '@/types/enums'

const authStore = useAuthStore()
const activeTab = ref('ai-config')

// ==================== AI Config ====================
const aiConfig = ref({
  api_base_url: '',
  api_key: '',
  model_name: '',
  temperature: 0.7,
  max_tokens: 2048,
})
const aiConfigLoading = ref(false)
const savingConfig = ref(false)
const testingConnection = ref(false)
const showApiKey = ref(false)
const apiKeyPlaceholder = ref('sk-...')

async function loadAiConfig() {
  aiConfigLoading.value = true
  try {
    const res = await aiApi.getConfig()
    const data = res.data as any
    aiConfig.value = {
      api_base_url: data.api_base_url || '',
      api_key: '',  // API Key 不回显，需要用户重新输入才会更新
      model_name: data.model_name || '',
      temperature: data.temperature ?? 0.7,
      max_tokens: data.max_tokens ?? 2048,
    }
    // 显示脱敏的 key 作为 placeholder 提示
    apiKeyPlaceholder.value = data.api_key_masked || 'sk-...'
  } catch {
    // Config may not exist yet
  } finally {
    aiConfigLoading.value = false
  }
}

async function saveAiConfig() {
  savingConfig.value = true
  try {
    await aiApi.updateConfig(aiConfig.value)
    ElMessage.success('AI 配置已保存')
  } catch {
    ElMessage.error('保存失败，请检查配置')
  } finally {
    savingConfig.value = false
  }
}

async function testConnection() {
  testingConnection.value = true
  try {
    const res = await aiApi.testConnection()
    const result = res.data as { success: boolean; message?: string }
    if (result.success) {
      ElMessage.success(result.message || '连接成功')
    } else {
      ElMessage.warning(result.message || '连接失败')
    }
  } catch {
    ElMessage.error('连接测试失败，请检查配置是否正确')
  } finally {
    testingConnection.value = false
  }
}

// ==================== User Management ====================
const users = ref<User[]>([])
const usersTotal = ref(0)
const usersPage = ref(1)
const usersLoading = ref(false)

const roleOptions = [
  { label: '管理员', value: UserRole.ADMIN },
  { label: '经理', value: UserRole.MANAGER },
  { label: '成员', value: UserRole.MEMBER },
]

async function loadUsers() {
  usersLoading.value = true
  try {
    const res = await usersApi.list(usersPage.value, 20)
    users.value = res.data.items
    usersTotal.value = res.data.total
  } finally {
    usersLoading.value = false
  }
}

async function handleRoleChange(user: User, newRole: UserRole) {
  try {
    await usersApi.update(user.id, { role: newRole })
    user.role = newRole
    ElMessage.success(`已将 ${user.full_name || user.username} 的角色更改为 ${roleOptions.find((r) => r.value === newRole)?.label}`)
  } catch {
    ElMessage.error('角色更新失败')
    loadUsers()
  }
}

function handleUsersPageChange(page: number) {
  usersPage.value = page
  loadUsers()
}

// ==================== Skill Management ====================
const skillList = ref<Skill[]>([])
const skillsLoading = ref(false)
const categoryFilter = ref('')
const categories = ref<string[]>([])

const skillDialogVisible = ref(false)
const editingSkill = ref<Skill | null>(null)
const skillForm = ref({
  name: '',
  category: '',
  description: '',
})

async function loadSkills() {
  skillsLoading.value = true
  try {
    const res = await skillsApi.list(categoryFilter.value || undefined)
    skillList.value = res.data

    const catSet = new Set<string>()
    res.data.forEach((s) => {
      if (s.category) catSet.add(s.category)
    })
    categories.value = Array.from(catSet).sort()
  } finally {
    skillsLoading.value = false
  }
}

function openAddSkill() {
  editingSkill.value = null
  skillForm.value = { name: '', category: '', description: '' }
  skillDialogVisible.value = true
}

function openEditSkill(skill: Skill) {
  editingSkill.value = skill
  skillForm.value = {
    name: skill.name,
    category: skill.category || '',
    description: skill.description || '',
  }
  skillDialogVisible.value = true
}

async function saveSkill() {
  if (!skillForm.value.name.trim()) {
    ElMessage.warning('请输入技能名称')
    return
  }
  try {
    const payload = {
      name: skillForm.value.name.trim(),
      category: skillForm.value.category.trim() || undefined,
      description: skillForm.value.description.trim() || undefined,
    }
    if (editingSkill.value) {
      await skillsApi.update(editingSkill.value.id, payload)
      ElMessage.success('技能已更新')
    } else {
      await skillsApi.create(payload)
      ElMessage.success('技能已添加')
    }
    skillDialogVisible.value = false
    loadSkills()
  } catch {
    ElMessage.error('保存失败')
  }
}

async function deleteSkill(skill: Skill) {
  try {
    await ElMessageBox.confirm(`确定删除技能「${skill.name}」吗？`, '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await skillsApi.delete(skill.id)
    ElMessage.success('技能已删除')
    loadSkills()
  } catch {
    // Cancelled
  }
}

function handleCategoryFilterChange() {
  loadSkills()
}

// ==================== Tab Change ====================
function handleTabChange(name: string | number) {
  const tab = String(name)
  if (tab === 'ai-config') {
    loadAiConfig()
  } else if (tab === 'user-management') {
    loadUsers()
  } else if (tab === 'skill-management') {
    loadSkills()
  }
}

onMounted(() => {
  loadAiConfig()
})
</script>

<template>
  <div class="settings-view">
    <h2 class="page-title">系统设置</h2>

    <el-tabs v-model="activeTab" @tab-change="handleTabChange">
      <!-- AI Config Tab -->
      <el-tab-pane label="AI配置" name="ai-config">
        <el-card v-loading="aiConfigLoading">
          <el-form label-width="120px" class="config-form">
            <el-form-item label="API 地址">
              <el-input
                v-model="aiConfig.api_base_url"
                placeholder="https://api.openai.com/v1"
              />
            </el-form-item>
            <el-form-item label="API Key">
              <el-input
                v-model="aiConfig.api_key"
                :type="showApiKey ? 'text' : 'password'"
                :placeholder="apiKeyPlaceholder"
              >
                <template #suffix>
                  <span
                    class="api-key-toggle"
                    @click="showApiKey = !showApiKey"
                    style="cursor:pointer; color:#909399; font-size:12px"
                  >
                    {{ showApiKey ? '隐藏' : '显示' }}
                  </span>
                </template>
              </el-input>
              <div style="font-size:12px; color:#909399; margin-top:4px">
                留空表示不修改已保存的 Key
              </div>
            </el-form-item>
            <el-form-item label="模型名称">
              <el-input
                v-model="aiConfig.model_name"
                placeholder="gpt-4"
              />
            </el-form-item>
            <el-form-item label="Temperature">
              <div class="slider-wrapper">
                <el-slider
                  v-model="aiConfig.temperature"
                  :min="0"
                  :max="1"
                  :step="0.1"
                  show-stops
                />
                <span class="slider-value">{{ aiConfig.temperature }}</span>
              </div>
            </el-form-item>
            <el-form-item label="Max Tokens">
              <el-input-number
                v-model="aiConfig.max_tokens"
                :min="1"
                :max="128000"
                :step="256"
              />
            </el-form-item>
            <el-form-item>
              <div class="config-actions">
                <el-button type="primary" :loading="savingConfig" @click="saveAiConfig">
                  保存配置
                </el-button>
                <el-button :loading="testingConnection" @click="testConnection">
                  测试连接
                </el-button>
              </div>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <!-- User Management Tab -->
      <el-tab-pane label="用户管理" name="user-management">
        <el-card v-loading="usersLoading">
          <el-table :data="users" stripe style="width: 100%">
            <el-table-column label="用户名" prop="username" min-width="120" />
            <el-table-column label="姓名" prop="full_name" min-width="120" />
            <el-table-column label="邮箱" prop="email" min-width="180" />
            <el-table-column label="角色" width="160">
              <template #default="{ row }">
                <el-select
                  :model-value="row.role"
                  :disabled="!authStore.isAdmin || row.id === authStore.user?.id"
                  size="small"
                  @change="(val: UserRole) => handleRoleChange(row, val)"
                >
                  <el-option
                    v-for="opt in roleOptions"
                    :key="opt.value"
                    :label="opt.label"
                    :value="opt.value"
                  />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
                  {{ row.is_active ? '活跃' : '禁用' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
          <div class="pagination-wrapper">
            <el-pagination
              v-model:current-page="usersPage"
              :page-size="20"
              :total="usersTotal"
              layout="total, prev, pager, next"
              @current-change="handleUsersPageChange"
            />
          </div>
        </el-card>
      </el-tab-pane>

      <!-- Skill Management Tab -->
      <el-tab-pane label="技能管理" name="skill-management">
        <el-card v-loading="skillsLoading">
          <div class="skill-toolbar">
            <el-select
              v-model="categoryFilter"
              placeholder="按分类筛选"
              clearable
              style="width: 200px"
              @change="handleCategoryFilterChange"
            >
              <el-option label="全部" value="" />
              <el-option
                v-for="cat in categories"
                :key="cat"
                :label="cat"
                :value="cat"
              />
            </el-select>
            <el-button type="primary" @click="openAddSkill">
              添加技能
            </el-button>
          </div>

          <el-table :data="skillList" stripe style="width: 100%">
            <el-table-column label="技能名称" prop="name" min-width="150" />
            <el-table-column label="分类" min-width="120">
              <template #default="{ row }">
                <el-tag v-if="row.category" size="small" type="info">{{ row.category }}</el-tag>
                <span v-else class="no-data">未分类</span>
              </template>
            </el-table-column>
            <el-table-column label="描述" prop="description" min-width="200">
              <template #default="{ row }">
                <span>{{ row.description || '--' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="160" align="center">
              <template #default="{ row }">
                <el-button type="primary" link size="small" @click="openEditSkill(row)">
                  编辑
                </el-button>
                <el-button type="danger" link size="small" @click="deleteSkill(row)">
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- Add/Edit Skill Dialog -->
        <el-dialog
          v-model="skillDialogVisible"
          :title="editingSkill ? '编辑技能' : '添加技能'"
          width="480px"
        >
          <el-form label-width="80px">
            <el-form-item label="名称">
              <el-input v-model="skillForm.name" placeholder="请输入技能名称" />
            </el-form-item>
            <el-form-item label="分类">
              <el-input v-model="skillForm.category" placeholder="例如：前端、后端、设计" />
            </el-form-item>
            <el-form-item label="描述">
              <el-input
                v-model="skillForm.description"
                type="textarea"
                :rows="3"
                placeholder="请输入技能描述"
              />
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="skillDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="saveSkill">确定</el-button>
          </template>
        </el-dialog>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.settings-view {
  padding: 0;
}

.page-title {
  margin: 0 0 20px 0;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.config-form {
  max-width: 600px;
}

.slider-wrapper {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
}

.slider-wrapper .el-slider {
  flex: 1;
}

.slider-value {
  width: 36px;
  text-align: right;
  font-size: 14px;
  color: #606266;
  flex-shrink: 0;
}

.api-key-toggle {
  cursor: pointer;
  color: #909399;
}

.api-key-toggle:hover {
  color: #409eff;
}

.config-actions {
  display: flex;
  gap: 12px;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.skill-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.no-data {
  color: #c0c4cc;
  font-size: 13px;
}
</style>
