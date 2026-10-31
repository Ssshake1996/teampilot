<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { skillsApi } from '@/api/skills'
import { dataSkillsApi } from '@/api/dataSkills'
import http from '@/api/index'
import { useAuthStore } from '@/stores/auth'
import type { DataConnector, Skill } from '@/types/models'

const authStore = useAuthStore()
const activeTab = ref(
  authStore.can('system.role_manage') ? 'permissions'
    : authStore.can('system.skill_manage') ? 'skill-management'
      : authStore.can('system.connector_manage') ? 'data-connectors' : '',
)







// ==================== RBAC Permission Management ====================
const permCatalog = ref<Record<string, { label: string; items: [string, string][] }>>({})
const rolesData = ref<Record<string, { permissions: string[]; builtin: boolean }>>({})
const permsLoading = ref(false)
const permsError = ref('')
const permsUpdatedAt = ref('')
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
  permsError.value = ''
  try {
    const [catRes, rolesRes] = await Promise.all([
      http.get('/permissions/catalog'),
      http.get('/permissions/roles'),
    ])
    permCatalog.value = catRes.data
    rolesData.value = rolesRes.data
    permsUpdatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } catch { permsError.value = '权限配置加载失败，已有配置可能不是最新数据。请重试。' }
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
  if (addingRole.value) return
  if (!newRoleName.value.trim()) { ElMessage.warning('请输入角色名称'); return }
  addingRole.value = true
  const name = newRoleName.value.trim()
  try {
    await http.post('/permissions/roles', { name, copy_from: newRoleCopyFrom.value })
    ElMessage.success('角色已创建')
    addRoleDialogVisible.value = false
    newRoleName.value = ''; newRoleCopyFrom.value = ''
    await loadPermissions()
    activeRole.value = name
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
const skillsError = ref('')
const skillsUpdatedAt = ref('')
const skillSaving = ref(false)
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
  skillsError.value = ''
  try {
    const res = await skillsApi.list(categoryFilter.value || undefined)
    skillList.value = res.data

    const catSet = new Set<string>()
    res.data.forEach((s) => {
      if (s.category) catSet.add(s.category)
    })
    categories.value = Array.from(catSet).sort()
    skillsUpdatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } catch {
    skillsError.value = '技能列表加载失败，已保留已有数据。'
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
  if (skillSaving.value) return
  if (!skillForm.value.name.trim()) {
    ElMessage.warning('请输入技能名称')
    return
  }
  skillSaving.value = true
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
  } finally { skillSaving.value = false }
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

// ==================== Data Connector Management ====================
const connectorList = ref<DataConnector[]>([])
const connectorsLoading = ref(false)
const connectorsError = ref('')
const connectorsUpdatedAt = ref('')
const connectorDialogVisible = ref(false)
const editingConnector = ref<DataConnector | null>(null)
const connectorSaving = ref(false)
const connectorForm = ref({
  name: '',
  key: '',
  description: '',
  base_url: '',
  auth_type: 'none' as DataConnector['auth_type'],
  auth_config_text: '{}',
  headers_text: '{}',
  timeout_seconds: 30,
  verify_tls: false,
  is_enabled: true,
})

async function loadConnectors() {
  connectorsLoading.value = true
  connectorsError.value = ''
  try {
    const res = await dataSkillsApi.listConnectors()
    connectorList.value = res.data
    connectorsUpdatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } catch {
    connectorsError.value = '连接器列表加载失败，已保留已有数据。'
  } finally {
    connectorsLoading.value = false
  }
}

function openAddConnector() {
  editingConnector.value = null
  connectorForm.value = {
    name: '',
    key: '',
    description: '',
    base_url: '',
    auth_type: 'none',
    auth_config_text: '{}',
    headers_text: '{}',
    timeout_seconds: 30,
    verify_tls: false,
    is_enabled: true,
  }
  connectorDialogVisible.value = true
}

function openEditConnector(connector: DataConnector) {
  editingConnector.value = connector
  connectorForm.value = {
    name: connector.name,
    key: connector.key,
    description: connector.description || '',
    base_url: connector.base_url,
    auth_type: connector.auth_type,
    auth_config_text: JSON.stringify(connector.auth_config_json || {}, null, 2),
    headers_text: JSON.stringify(connector.headers_json || {}, null, 2),
    timeout_seconds: connector.timeout_seconds,
    verify_tls: connector.verify_tls,
    is_enabled: connector.is_enabled,
  }
  connectorDialogVisible.value = true
}

function parseConnectorJson(text: string, field: string) {
  try {
    return JSON.parse(text || '{}')
  } catch {
    throw new Error(`${field} JSON 格式不正确`)
  }
}

function applyDynamicTokenTemplate() {
  connectorForm.value.auth_type = 'dynamic_token'
  connectorForm.value.auth_config_text = JSON.stringify({
    token_url: '/api/auth/login',
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: { app_id: 'xxx', app_secret: 'xxx' },
    token_path: '$.data.access_token',
    expires_in_path: '$.data.expires_in',
    token_prefix: 'Bearer',
    target: 'header',
    target_name: 'Authorization',
    cache_seconds: 3600,
  }, null, 2)
}

async function saveConnector() {
  if (!connectorForm.value.name.trim() || !connectorForm.value.key.trim() || !connectorForm.value.base_url.trim()) {
    ElMessage.warning('请填写名称、Key 和 API 地址')
    return
  }
  connectorSaving.value = true
  try {
    const payload = {
      name: connectorForm.value.name.trim(),
      key: connectorForm.value.key.trim(),
      description: connectorForm.value.description.trim() || undefined,
      base_url: connectorForm.value.base_url.trim(),
      auth_type: connectorForm.value.auth_type,
      auth_config_json: parseConnectorJson(connectorForm.value.auth_config_text, '认证配置'),
      headers_json: parseConnectorJson(connectorForm.value.headers_text, '请求头'),
      timeout_seconds: connectorForm.value.timeout_seconds,
      verify_tls: connectorForm.value.verify_tls,
      is_enabled: connectorForm.value.is_enabled,
    }
    if (editingConnector.value) {
      await dataSkillsApi.updateConnector(editingConnector.value.id, payload)
    } else {
      await dataSkillsApi.createConnector(payload)
    }
    connectorDialogVisible.value = false
    ElMessage.success('数据连接器已保存')
    await loadConnectors()
  } catch (err: any) {
    ElMessage.error(err?.message || err?.response?.data?.detail || '保存失败')
  } finally {
    connectorSaving.value = false
  }
}

async function deleteConnector(connector: DataConnector) {
  try {
    await ElMessageBox.confirm(`确认删除数据连接器「${connector.name}」？`, '删除确认', { type: 'warning' })
    await dataSkillsApi.deleteConnector(connector.id)
    ElMessage.success('数据连接器已删除')
    await loadConnectors()
  } catch {
    // cancelled
  }
}





// ==================== Tab Change ====================
function handleTabChange(name: string | number) {
  const tab = String(name)
  if (tab === 'permissions' && authStore.can('system.role_manage')) loadPermissions()
  else if (tab === 'skill-management' && authStore.can('system.skill_manage')) loadSkills()
  else if (tab === 'data-connectors' && authStore.can('system.connector_manage')) loadConnectors()
}

onMounted(() => {
  handleTabChange(activeTab.value)
})
</script>

<template>
  <div class="settings-view">
    <h2 class="page-title">系统设置</h2>

    <el-empty v-if="!activeTab" description="暂无系统设置权限" />
    <el-tabs v-else v-model="activeTab" @tab-change="handleTabChange">

      <!-- User Management Tab -->
      <el-tab-pane v-if="authStore.can('system.role_manage')" label="权限管理" name="permissions">
        <p v-if="permsUpdatedAt" class="settings-data-status">上次更新 {{ permsUpdatedAt }}</p>
        <el-alert v-if="permsError" :title="permsError" type="error" :closable="false" show-icon><el-button text @click="loadPermissions">重试</el-button></el-alert>
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
      <el-tab-pane v-if="authStore.can('system.skill_manage')" label="技能管理" name="skill-management">
        <p v-if="skillsUpdatedAt" class="settings-data-status">上次更新 {{ skillsUpdatedAt }}</p>
        <el-alert v-if="skillsError" :title="skillsError" type="error" :closable="false" show-icon><el-button text @click="loadSkills">重试</el-button></el-alert>
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
            <el-button type="primary" :loading="skillSaving" @click="saveSkill">确定</el-button>
          </template>
        </el-dialog>
      </el-tab-pane>

      <el-tab-pane v-if="authStore.can('system.connector_manage')" label="数据连接器" name="data-connectors">
        <p v-if="connectorsUpdatedAt" class="settings-data-status">上次更新 {{ connectorsUpdatedAt }}</p>
        <el-alert v-if="connectorsError" :title="connectorsError" type="error" :closable="false" show-icon><el-button text @click="loadConnectors">重试</el-button></el-alert>
        <el-card v-loading="connectorsLoading">
          <div class="connector-toolbar">
            <span class="connector-hint">内部平台 API 白名单，任务数据 Skill 只能调用这里配置的平台。</span>
            <el-button type="primary" @click="openAddConnector">新增连接器</el-button>
          </div>
          <el-table :data="connectorList" stripe style="width: 100%">
            <el-table-column label="名称" prop="name" min-width="140" />
            <el-table-column label="Key" prop="key" min-width="140" />
            <el-table-column label="API 地址" prop="base_url" min-width="220" show-overflow-tooltip />
            <el-table-column label="鉴权" prop="auth_type" width="100" />
            <el-table-column label="TLS 校验" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="row.verify_tls ? 'success' : 'info'" size="small">
                  {{ row.verify_tls ? '开启' : '关闭' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90" align="center">
              <template #default="{ row }">
                <el-tag :type="row.is_enabled ? 'success' : 'info'" size="small">
                  {{ row.is_enabled ? '启用' : '停用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="150" align="center">
              <template #default="{ row }">
                <el-button type="primary" link size="small" @click="openEditConnector(row)">编辑</el-button>
                <el-button type="danger" link size="small" @click="deleteConnector(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-dialog
          v-model="connectorDialogVisible"
          :title="editingConnector ? '编辑数据连接器' : '新增数据连接器'"
          width="680px"
        >
          <el-form label-width="100px">
            <el-form-item label="名称">
              <el-input v-model="connectorForm.name" placeholder="测试平台" />
            </el-form-item>
            <el-form-item label="Key">
              <el-input v-model="connectorForm.key" placeholder="test_platform" />
            </el-form-item>
            <el-form-item label="API 地址">
              <el-input v-model="connectorForm.base_url" placeholder="https://test-platform.internal" />
            </el-form-item>
            <el-form-item label="描述">
              <el-input v-model="connectorForm.description" type="textarea" :rows="2" />
            </el-form-item>
            <el-form-item label="鉴权方式">
              <el-select v-model="connectorForm.auth_type" style="width: 100%">
                <el-option label="无" value="none" />
                <el-option label="Bearer Token" value="bearer" />
                <el-option label="API Key" value="api_key" />
                <el-option label="Basic" value="basic" />
                <el-option label="动态 Token" value="dynamic_token" />
              </el-select>
            </el-form-item>
            <el-alert
              v-if="connectorForm.auth_type === 'dynamic_token'"
              type="info"
              :closable="false"
              show-icon
              class="connector-auth-tip"
            >
              <template #title>
                执行任务数据 Skill 前会先调用认证接口获取 token，并按 cache_seconds 缓存复用。
                <el-button type="primary" link size="small" @click="applyDynamicTokenTemplate">填入模板</el-button>
              </template>
            </el-alert>
            <el-form-item label="认证配置">
              <el-input
                v-model="connectorForm.auth_config_text"
                type="textarea"
                :rows="connectorForm.auth_type === 'dynamic_token' ? 9 : 4"
                placeholder='{"token":"xxx"}'
                class="json-input"
              />
            </el-form-item>
            <el-form-item label="请求头">
              <el-input
                v-model="connectorForm.headers_text"
                type="textarea"
                :rows="3"
                placeholder='{"X-App":"TeamPilot"}'
                class="json-input"
              />
            </el-form-item>
            <el-form-item label="超时秒数">
              <el-input-number v-model="connectorForm.timeout_seconds" :min="1" :max="180" />
            </el-form-item>
            <el-form-item label="选项">
              <div class="connector-switches">
                <el-checkbox v-model="connectorForm.verify_tls">开启 HTTPS 证书校验</el-checkbox>
                <el-checkbox v-model="connectorForm.is_enabled">启用</el-checkbox>
              </div>
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="connectorDialogVisible = false">取消</el-button>
            <el-button type="primary" :loading="connectorSaving" @click="saveConnector">保存</el-button>
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
.settings-data-status { font-size: 12px; color: var(--muted); margin: 8px 0; }

.page-title {
  margin: 0 0 20px 0;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.skill-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}

.connector-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.connector-hint {
  color: #909399;
  font-size: 13px;
}

.connector-switches {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
}

.connector-auth-tip {
  margin: -4px 0 16px;
}

.json-input :deep(textarea) {
  font-family: Consolas, 'Courier New', monospace;
  font-size: 12px;
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
