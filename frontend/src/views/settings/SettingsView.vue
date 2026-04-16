<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { aiApi } from '@/api/ai'
import { skillsApi } from '@/api/skills'
import http from '@/api/index'
import { useAuthStore } from '@/stores/auth'
import type { Skill } from '@/types/models'

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
    const result = res.data as {
      success: boolean
      message?: string
      status_code?: number | null
      error_type?: string | null
      backend_detail?: string | null
    }
    if (result.success) {
      ElMessage.success(result.message || '连接成功')
    } else {
      await ElMessageBox.alert(
        [
          `消息: ${result.message || '连接失败'}`,
          `状态码: ${result.status_code ?? '-'}`,
          `错误类型: ${result.error_type || '-'}`,
          `后端返回: ${result.backend_detail || '-'}`,
        ].join('\n'),
        '测试连接失败',
        { confirmButtonText: '知道了' },
      )
    }
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err?.message || '连接测试失败，请检查配置是否正确')
  } finally {
    testingConnection.value = false
  }
}

// ==================== RBAC Permission Management ====================
const permCatalog = ref<Record<string, { label: string; items: [string, string][] }>>({})
const rolesData = ref<Record<string, { permissions: string[]; builtin: boolean }>>({})
const permsLoading = ref(false)
const savingRole = ref('')
const activeRole = ref('admin')
const builtinLabels: Record<string, string> = { admin: '管理员', manager: '经理', member: '成员' }

const addRoleDialogVisible = ref(false)
const newRoleName = ref('')
const newRoleCopyFrom = ref('')
const addingRole = ref(false)

const roleList = computed(() => Object.keys(rolesData.value))

function roleLabel(r: string) { return builtinLabels[r] || r }
function isBuiltin(r: string) { return rolesData.value[r]?.builtin ?? false }

async function loadPermissions() {
  permsLoading.value = true
  try {
    const [catRes, rolesRes] = await Promise.all([
      http.get('/permissions/catalog'),
      http.get('/permissions/roles'),
    ])
    permCatalog.value = catRes.data
    rolesData.value = rolesRes.data
  } catch {}
  finally { permsLoading.value = false }
}

function hasPermission(role: string, perm: string): boolean {
  return (rolesData.value[role]?.permissions || []).includes(perm)
}

function togglePermission(role: string, perm: string) {
  if (role === 'admin') return
  const perms = rolesData.value[role]?.permissions || []
  const idx = perms.indexOf(perm)
  if (idx >= 0) perms.splice(idx, 1)
  else perms.push(perm)
}

async function saveRolePerms(role: string) {
  savingRole.value = role
  try {
    await http.put('/permissions/roles', { role, permissions: rolesData.value[role]?.permissions || [] })
    if (authStore.user?.role === role) await authStore.fetchPermissions()
    ElMessage.success(roleLabel(role) + ' 权限已保存')
  } catch { ElMessage.error('保存失败') }
  finally { savingRole.value = '' }
}

async function handleAddRole() {
  if (!newRoleName.value.trim()) { ElMessage.warning('请输入角色名称'); return }
  addingRole.value = true
  try {
    await http.post('/permissions/roles', { name: newRoleName.value.trim(), copy_from: newRoleCopyFrom.value })
    ElMessage.success('角色已创建')
    addRoleDialogVisible.value = false
    newRoleName.value = ''; newRoleCopyFrom.value = ''
    await loadPermissions()
    activeRole.value = newRoleName.value.trim() || activeRole.value
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '创建失败') }
  finally { addingRole.value = false }
}

async function handleDeleteRole(role: string) {
  try {
    await ElMessageBox.confirm('删除角色 "' + role + '"？使用此角色的用户不受影响，但失去角色权限配置。', '确认删除', { type: 'warning' })
    await http.delete('/permissions/roles/' + role)
    ElMessage.success('角色已删除')
    if (activeRole.value === role) activeRole.value = 'admin'
    await loadPermissions()
  } catch {}
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

// ==================== AI Prompt Config ====================
const prompts = ref<{ key: string; label: string; value: string; default: string; is_custom: boolean }[]>([])
const promptsLoading = ref(false)
const savingPromptKey = ref('')

async function loadPrompts() {
  promptsLoading.value = true
  try {
    const res = await aiApi.getPrompts()
    prompts.value = res.data
  } catch { /* not configured */ }
  finally { promptsLoading.value = false }
}

async function savePrompt(p: any) {
  savingPromptKey.value = p.key
  try {
    await aiApi.updatePrompt(p.key, p.value)
    p.is_custom = !!p.value.trim()
    ElMessage.success(`"${p.label}" 已保存`)
  } catch { ElMessage.error('保存失败') }
  finally { savingPromptKey.value = '' }
}

function resetPrompt(p: any) {
  p.value = ''
  savePrompt(p)
}

// ==================== Tab Change ====================
function handleTabChange(name: string | number) {
  const tab = String(name)
  if (tab === 'ai-config') {
    loadAiConfig()
  } else if (tab === 'permissions') {
    loadPermissions()
  } else if (tab === 'skill-management') {
    loadSkills()
  } else if (tab === 'ai-prompts') {
    loadPrompts()
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
      <el-tab-pane label="权限管理" name="permissions">
        <el-card v-loading="permsLoading">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
            <span style="color:#909399;font-size:13px">配置各角色权限。管理员默认全部权限。支持自定义角色。</span>
            <el-button type="primary" size="small" @click="addRoleDialogVisible = true">新建角色</el-button>
          </div>
          <el-tabs v-model="activeRole" type="card">
            <el-tab-pane v-for="role in roleList" :key="role" :label="roleLabel(role)" :name="role">
              <div v-for="(cat, catKey) in permCatalog" :key="catKey" class="perm-cat">
                <div class="perm-cat-hd">{{ cat.label }}</div>
                <div class="perm-items">
                  <el-checkbox
                    v-for="[perm, plabel] in cat.items" :key="perm"
                    :model-value="hasPermission(role, perm)"
                    :disabled="role === 'admin'"
                    @change="togglePermission(role, perm)"
                  >{{ plabel }}</el-checkbox>
                </div>
              </div>
              <div style="margin-top:12px;display:flex;gap:8px">
                <el-button type="primary" :loading="savingRole === role" :disabled="role === 'admin'" @click="saveRolePerms(role)">
                  保存权限
                </el-button>
                <el-button v-if="!isBuiltin(role)" type="danger" plain size="small" @click="handleDeleteRole(role)">
                  删除此角色
                </el-button>
                <el-tag v-if="isBuiltin(role)" type="info" size="small" effect="plain" style="margin-left:8px">内置角色</el-tag>
              </div>
            </el-tab-pane>
          </el-tabs>
        </el-card>

        <!-- Add Role Dialog -->
        <el-dialog v-model="addRoleDialogVisible" title="新建角色" width="400px">
          <el-form label-width="80px">
            <el-form-item label="角色名称">
              <el-input v-model="newRoleName" placeholder="如: 测试组长、项目总监" />
            </el-form-item>
            <el-form-item label="复制权限">
              <el-select v-model="newRoleCopyFrom" placeholder="从已有角色复制(可选)" clearable style="width:100%">
                <el-option v-for="r in roleList" :key="r" :label="roleLabel(r)" :value="r" />
              </el-select>
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="addRoleDialogVisible = false">取消</el-button>
            <el-button type="primary" :loading="addingRole" @click="handleAddRole">创建</el-button>
          </template>
        </el-dialog>
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

      <!-- AI Prompt Config Tab -->
      <el-tab-pane label="AI Prompt" name="ai-prompts">
        <el-card v-loading="promptsLoading">
          <div style="margin-bottom:12px;color:#909399;font-size:13px">
            自定义各 AI 功能的 System Prompt。留空则使用系统默认值。
          </div>
          <el-collapse v-if="prompts.length">
            <el-collapse-item v-for="p in prompts" :key="p.key" :name="p.key">
              <template #title>
                <span style="font-weight:600">{{ p.label }}</span>
                <el-tag v-if="p.is_custom" type="warning" size="small" style="margin-left:8px">已自定义</el-tag>
                <el-tag v-else type="info" size="small" effect="plain" style="margin-left:8px">默认</el-tag>
              </template>
              <div style="margin-bottom:8px">
                <el-input
                  v-model="p.value"
                  type="textarea"
                  :rows="8"
                  :placeholder="p.default"
                  style="font-family:monospace;font-size:13px"
                />
              </div>
              <div style="display:flex;gap:8px">
                <el-button type="primary" size="small" :loading="savingPromptKey === p.key" @click="savePrompt(p)">保存</el-button>
                <el-button size="small" @click="resetPrompt(p)">恢复默认</el-button>
                <el-button size="small" type="info" link @click="p.value = p.default">查看默认值</el-button>
              </div>
            </el-collapse-item>
          </el-collapse>
          <el-empty v-else description="请先配置 AI 连接" />
        </el-card>
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

/* Permission management */
.perm-cat { margin-bottom: 16px; }
.perm-cat-hd { font-weight: 600; font-size: 13px; color: #303133; margin-bottom: 6px; padding-bottom: 4px; border-bottom: 1px solid #ebeef5; }
.perm-items { display: flex; flex-wrap: wrap; gap: 8px 24px; }
</style>
