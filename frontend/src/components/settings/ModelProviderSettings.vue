<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { modelProvidersApi } from '@/api/modelProviders'
import type {
  ModelConnectionResult,
  ModelProvider,
  ModelProviderCatalog,
  ModelProviderDraft,
  ModelProviderInput,
  ProviderModel,
} from '@/types/modelProviders'
import {
  editProviderHeaders,
  normalizeProviderModels,
  providerRequestError,
  serializeProviderHeaders,
  type ProviderHeaderRow,
} from '@/utils/modelProviderForm'

const providers = ref<ModelProvider[]>([])
const catalog = ref<ModelProviderCatalog | null>(null)
const loading = ref(false)
const loadError = ref('')
const catalogError = ref('')
const updatedAt = ref('')
const rowBusy = ref('')
const dialogVisible = ref(false)
const editing = ref<ModelProvider | null>(null)
const presetKey = ref('')
const form = ref<ModelProviderInput>(emptyForm())
const headerRows = ref<ProviderHeaderRow[]>([])
const advancedOpen = ref<string[]>([])
const operation = ref<'save' | 'models' | 'test' | ''>('')
const formError = ref('')
const discoveredModels = ref<ProviderModel[]>([])
const discoveryMessage = ref('')
const testResult = ref<ModelConnectionResult | null>(null)
const working = computed(() => !!operation.value)
const availableModels = computed(() => {
  const options = new Map(discoveredModels.value.map(model => [model.id, model]))
  for (const id of form.value.model_ids) {
    if (!options.has(id)) options.set(id, { id, name: id })
  }
  return [...options.values()]
})
const authHint = computed(() => form.value.protocol === 'anthropic-messages'
  ? '使用 x-api-key 请求头，按 Messages 协议接入。'
  : '使用 Authorization: Bearer 请求头。')

function emptyForm(): ModelProviderInput {
  return {
    key: '', name: '', protocol: 'openai-completions', base_url: '', api_key: '',
    clear_api_key: false, headers: {}, model_ids: [], default_model: '',
    is_enabled: true, timeout_seconds: 60, verify_tls: true,
  }
}

function protocolLabel(protocol: string) {
  return catalog.value?.protocols.find(item => item.id === protocol)?.label || protocol
}

async function refreshProviders() {
  loadError.value = ''
  try {
    providers.value = (await modelProvidersApi.list()).data
    updatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } catch (error) {
    loadError.value = providerRequestError(error, '供应商列表加载失败，已保留已有数据。')
  }
}

async function loadData() {
  if (loading.value) return
  loading.value = true
  catalogError.value = ''
  await Promise.all([
    refreshProviders(),
    modelProvidersApi.catalog().then(response => { catalog.value = response.data }).catch(error => {
      catalogError.value = providerRequestError(error, '协议与预设加载失败，请重试。')
    }),
  ])
  loading.value = false
}

function resetFeedback() {
  formError.value = ''
  discoveredModels.value = []
  discoveryMessage.value = ''
  testResult.value = null
}

function openNew() {
  editing.value = null
  presetKey.value = ''
  form.value = emptyForm()
  headerRows.value = []
  advancedOpen.value = []
  resetFeedback()
  dialogVisible.value = true
}

function openEdit(provider: ModelProvider) {
  editing.value = provider
  presetKey.value = ''
  form.value = {
    key: provider.key, name: provider.name, protocol: provider.protocol,
    base_url: provider.base_url, api_key: '', clear_api_key: false,
    headers: {}, model_ids: [...provider.model_ids], default_model: provider.default_model,
    is_enabled: provider.is_enabled, timeout_seconds: provider.timeout_seconds,
    verify_tls: provider.verify_tls,
  }
  headerRows.value = editProviderHeaders(provider.headers)
  advancedOpen.value = headerRows.value.length ? ['connection'] : []
  resetFeedback()
  dialogVisible.value = true
}

function applyPreset() {
  const preset = catalog.value?.presets.find(item => item.key === presetKey.value)
  if (!preset) return
  let key = preset.key
  let suffix = 2
  while (providers.value.some(item => item.id !== editing.value?.id && item.key === key)) {
    key = `${preset.key}-${suffix++}`
  }
  form.value.name = preset.name
  form.value.key = key
  form.value.protocol = preset.protocol
  form.value.base_url = preset.base_url
  form.value.model_ids = [...preset.model_ids]
  form.value.default_model = preset.default_model
}

function handleModelsChange() {
  form.value.model_ids = normalizeProviderModels(form.value.model_ids)
  if (!form.value.model_ids.includes(form.value.default_model)) {
    form.value.default_model = form.value.model_ids[0] || ''
  }
}

function buildDraft(requireModel: boolean): ModelProviderDraft {
  if (!form.value.name.trim() || !form.value.key.trim()) throw new Error('请填写供应商名称和标识')
  if (!/^[a-z][a-z0-9-]*$/.test(form.value.key.trim())) {
    throw new Error('供应商标识须以小写字母开头，仅支持小写字母、数字和连字符')
  }
  let url: URL
  try { url = new URL(form.value.base_url.trim()) }
  catch { throw new Error('请填写完整的 API 地址') }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) {
    throw new Error('API 地址须为不含用户名和密码的 HTTP 或 HTTPS 地址')
  }
  if (!Number.isInteger(form.value.timeout_seconds) || form.value.timeout_seconds < 1 || form.value.timeout_seconds > 180) {
    throw new Error('请求超时须为 1 到 180 之间的整数秒')
  }
  const models = normalizeProviderModels(form.value.model_ids)
  const defaultModel = form.value.default_model.trim()
  if (requireModel && (!models.length || !defaultModel)) throw new Error('请添加至少一个模型，并选择默认模型')
  if (defaultModel && !models.includes(defaultModel)) throw new Error('默认模型须在已配置的模型中')
  return {
    ...form.value,
    id: editing.value?.id,
    key: form.value.key.trim(), name: form.value.name.trim(),
    base_url: form.value.base_url.trim(), api_key: form.value.api_key?.trim(),
    headers: serializeProviderHeaders(headerRows.value), model_ids: models,
    default_model: defaultModel,
  }
}

async function saveProvider() {
  if (working.value) return
  formError.value = ''
  let draft: ModelProviderDraft
  try { draft = buildDraft(true) }
  catch (error) { formError.value = (error as Error).message; return }
  operation.value = 'save'
  try {
    const { id, ...payload } = draft
    if (id) await modelProvidersApi.update(id, payload)
    else await modelProvidersApi.create(payload)
    dialogVisible.value = false
    ElMessage.success('模型供应商已保存')
    await refreshProviders()
  } catch (error) {
    formError.value = providerRequestError(error, '保存失败，输入已保留，请重试。')
  } finally { operation.value = '' }
}

async function discoverModels() {
  if (working.value) return
  formError.value = ''
  discoveryMessage.value = ''
  let draft: ModelProviderDraft
  try { draft = buildDraft(false) }
  catch (error) { formError.value = (error as Error).message; return }
  operation.value = 'models'
  try {
    discoveredModels.value = (await modelProvidersApi.models(draft)).data.models
    discoveryMessage.value = discoveredModels.value.length
      ? `发现 ${discoveredModels.value.length} 个模型，请在下方选择。`
      : '服务未返回模型，可直接输入模型 ID 后按回车添加。'
  } catch (error) {
    formError.value = providerRequestError(error, '获取模型失败，可检查配置后重试，或手动输入模型 ID。')
  } finally { operation.value = '' }
}

async function testConnection() {
  if (working.value) return
  formError.value = ''
  testResult.value = null
  let draft: ModelProviderDraft
  try { draft = buildDraft(true) }
  catch (error) { formError.value = (error as Error).message; return }
  operation.value = 'test'
  try {
    testResult.value = (await modelProvidersApi.test(draft)).data
  } catch (error) {
    formError.value = providerRequestError(error, '模型测试失败，输入已保留，请检查地址、密钥和模型。')
  } finally { operation.value = '' }
}

async function toggleProvider(provider: ModelProvider) {
  if (rowBusy.value) return
  rowBusy.value = provider.id
  try {
    const updated = (await modelProvidersApi.update(provider.id, { is_enabled: !provider.is_enabled })).data
    providers.value = providers.value.map(item => item.id === provider.id ? updated : item)
    ElMessage.success(updated.is_enabled ? '供应商已启用' : '供应商已停用')
  } catch (error) {
    ElMessage.error(providerRequestError(error, '状态更新失败，请重试。'))
  } finally { rowBusy.value = '' }
}

async function deleteProvider(provider: ModelProvider) {
  if (rowBusy.value) return
  try {
    await ElMessageBox.confirm(`删除模型供应商「${provider.name}」及其保存的密钥？`, '删除供应商', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch { return }
  rowBusy.value = provider.id
  try {
    await modelProvidersApi.remove(provider.id)
    providers.value = providers.value.filter(item => item.id !== provider.id)
    ElMessage.success('供应商已删除')
  } catch (error) {
    ElMessage.error(providerRequestError(error, '删除失败，请重试。'))
  } finally { rowBusy.value = '' }
}

function closeDialog(done: () => void) {
  if (!working.value) done()
}

function clearDialog() {
  form.value = emptyForm()
  headerRows.value = []
  editing.value = null
  resetFeedback()
}

watch(() => [form.value.base_url, form.value.protocol, form.value.api_key, form.value.clear_api_key,
  JSON.stringify(headerRows.value)], resetFeedback)
watch(() => [form.value.default_model, form.value.model_ids.join('\n')], () => { testResult.value = null })
onMounted(loadData)
onBeforeUnmount(clearDialog)
</script>

<template>
  <section class="model-providers" aria-label="模型供应商配置">
    <div class="provider-toolbar">
      <div>
        <h3>模型供应商</h3>
        <p>选择接入协议，配置服务地址和可用模型。</p>
      </div>
      <el-button type="primary" :disabled="loading || !catalog" @click="openNew">新增供应商</el-button>
    </div>
    <el-alert v-if="loadError || catalogError" type="error" :closable="false" show-icon class="provider-alert">
      <template #title>{{ loadError || catalogError }}</template>
      <el-button link type="primary" :loading="loading" @click="loadData">重新加载</el-button>
    </el-alert>

    <div v-loading="loading" class="provider-list">
      <el-empty v-if="!providers.length && !loading && !loadError" description="还没有模型供应商">
        <el-button :disabled="!catalog" @click="openNew">配置第一个供应商</el-button>
      </el-empty>
      <article v-for="provider in providers" :key="provider.id" class="provider-row">
        <div class="provider-identity">
          <div class="provider-title"><h4>{{ provider.name }}</h4><el-tag effect="plain" size="small">{{ protocolLabel(provider.protocol) }}</el-tag></div>
          <span class="provider-key">{{ provider.key }}</span>
          <p class="provider-url">{{ provider.base_url }}</p>
          <div class="provider-model-summary">
            <span>默认模型 <strong>{{ provider.default_model || '未设置' }}</strong></span>
            <span>{{ provider.model_ids.length }} 个模型</span>
            <span>{{ provider.has_api_key ? '已保存 API Key' : '未设置 API Key' }}</span>
          </div>
        </div>
        <div class="provider-actions">
          <el-switch :model-value="provider.is_enabled" :loading="rowBusy === provider.id" :disabled="!!rowBusy"
            active-text="启用" :aria-label="`${provider.name} 启用状态`" @change="toggleProvider(provider)" />
          <div>
            <el-button link type="primary" :disabled="!!rowBusy || !catalog" @click="openEdit(provider)">编辑</el-button>
            <el-button link type="danger" :disabled="!!rowBusy" @click="deleteProvider(provider)">删除</el-button>
          </div>
        </div>
      </article>
    </div>
    <p v-if="updatedAt" class="provider-updated">上次更新 {{ updatedAt }}</p>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑模型供应商' : '新增模型供应商'"
      width="min(760px, calc(100vw - 24px))" top="5vh" :close-on-click-modal="false"
      :show-close="!working" :before-close="closeDialog" @closed="clearDialog">
      <el-form class="provider-form" label-position="top" :disabled="working" @submit.prevent="saveProvider">
        <el-form-item v-if="!editing" label="供应商预设">
          <el-select v-model="presetKey" placeholder="选择预设，或手动配置" clearable @change="applyPreset">
            <el-option v-for="preset in catalog?.presets" :key="preset.key" :label="preset.name" :value="preset.key" />
          </el-select>
        </el-form-item>
        <div class="provider-form-grid">
          <el-form-item label="供应商名称" required><el-input v-model="form.name" placeholder="例如：团队模型服务" maxlength="100" /></el-form-item>
          <el-form-item label="供应商标识" required><el-input v-model="form.key" placeholder="例如：team-models" maxlength="64" /></el-form-item>
        </div>
        <el-form-item label="接入协议" required>
          <el-select v-model="form.protocol">
            <el-option v-for="protocol in catalog?.protocols" :key="protocol.id" :label="protocol.label" :value="protocol.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="API 地址" required><el-input v-model="form.base_url" placeholder="https://api.example.com/v1" /></el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="form.api_key" type="password" show-password autocomplete="new-password"
            :disabled="working || form.clear_api_key" :placeholder="editing?.has_api_key ? '已保存，留空保留原密钥' : '输入 API Key；本地服务可留空'" />
          <div class="field-help">{{ authHint }}</div>
          <el-checkbox v-if="editing?.has_api_key" v-model="form.clear_api_key">清除已保存密钥</el-checkbox>
        </el-form-item>

        <div class="model-section-heading"><h4>可用模型</h4><el-button :loading="operation === 'models'" :disabled="working" @click="discoverModels">获取可用模型</el-button></div>
        <p v-if="discoveryMessage" class="field-help discovery-message" role="status">{{ discoveryMessage }}</p>
        <el-form-item label="模型列表" required>
          <el-select v-model="form.model_ids" multiple filterable allow-create default-first-option :reserve-keyword="false"
            collapse-tags collapse-tags-tooltip :max-collapse-tags="3" placeholder="选择模型，或输入模型 ID 后按回车添加" @change="handleModelsChange">
            <el-option v-for="model in availableModels" :key="model.id" :label="model.name === model.id ? model.id : `${model.name} (${model.id})`" :value="model.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="默认模型" required>
          <el-select v-model="form.default_model" :disabled="working || !form.model_ids.length" placeholder="选择测试和调用使用的模型">
            <el-option v-for="id in form.model_ids" :key="id" :label="id" :value="id" />
          </el-select>
        </el-form-item>

        <el-collapse v-model="advancedOpen" class="provider-advanced">
          <el-collapse-item title="高级连接配置" name="connection">
            <div class="headers-heading"><span>自定义请求头</span><el-button link type="primary" @click="headerRows.push({ key: '', value: '', savedKey: null })">添加请求头</el-button></div>
            <p v-if="headerRows.length" class="field-help">已保存的值不会回显；留空保留，移除该行即删除。</p>
            <div v-for="(row, index) in headerRows" :key="index" class="provider-header-row">
              <el-input v-model="row.key" placeholder="请求头名称" :aria-label="`请求头 ${index + 1} 名称`" />
              <el-input v-model="row.value" type="password" show-password autocomplete="new-password"
                :placeholder="row.savedKey === row.key ? '已保存，留空保留' : '请求头值'" :aria-label="`请求头 ${index + 1} 值`" />
              <el-button link type="danger" :aria-label="`移除请求头 ${index + 1}`" @click="headerRows.splice(index, 1)">移除</el-button>
            </div>
            <div class="provider-options">
              <el-form-item label="请求超时（秒）"><el-input-number v-model="form.timeout_seconds" :min="1" :max="180" :precision="0" :value-on-clear="60" /></el-form-item>
              <el-checkbox v-model="form.verify_tls">校验 HTTPS 证书</el-checkbox>
              <el-checkbox v-model="form.is_enabled">启用供应商</el-checkbox>
            </div>
          </el-collapse-item>
        </el-collapse>
      </el-form>
      <el-alert v-if="formError" :title="formError" type="error" show-icon :closable="false" class="provider-alert" />
      <el-alert v-if="testResult" :type="testResult.ok ? 'success' : 'error'" show-icon :closable="false" class="provider-alert">
        <template #title>{{ testResult.ok ? '模型调用成功' : '模型调用失败' }} · {{ testResult.model }} · {{ Math.round(testResult.latency_ms) }} ms</template>
        {{ testResult.message }}
      </el-alert>
      <template #footer>
        <div class="provider-dialog-footer">
          <div class="test-action"><el-button :loading="operation === 'test'" :disabled="working" @click="testConnection">测试模型</el-button><span>发送一条简短消息</span></div>
          <div><el-button :disabled="working" @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="operation === 'save'" :disabled="working" @click="saveProvider">保存</el-button></div>
        </div>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.provider-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin: 8px 0 20px; }
.provider-toolbar h3 { margin: 0 0 6px; font-size: 16px; font-weight: 600; }
.provider-toolbar p { margin: 0; font-size: 13px; color: var(--muted); }
.provider-list { min-height: 100px; border: 1px solid var(--border); border-radius: 8px; background: white; }
.provider-row { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 20px; }
.provider-row + .provider-row { border-top: 1px solid var(--border); }
.provider-identity { min-width: 0; }
.provider-title { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 4px; }
.provider-title h4 { font-size: 15px; margin: 0; overflow-wrap: anywhere; }
.provider-key, .provider-url { font-size: 12px; color: var(--muted); overflow-wrap: anywhere; }
.provider-key { font-family: Consolas, monospace; }
.provider-url { margin: 10px 0; }
.provider-model-summary { display: flex; gap: 8px 20px; flex-wrap: wrap; font-size: 12px; color: var(--muted); }
.provider-model-summary strong { color: var(--ink); font-weight: 500; overflow-wrap: anywhere; }
.provider-actions { flex: 0 0 auto; display: flex; flex-direction: column; align-items: flex-end; gap: 14px; }
.provider-alert { margin: 12px 0; }
.provider-alert :deep(.el-alert__content) { min-width: 0; overflow-wrap: anywhere; }
.provider-updated { color: var(--muted); font-size: 12px; }
.provider-form :deep(.el-select) { width: 100%; }
.provider-form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.provider-form :deep(.el-form-item) { margin-bottom: 18px; }
.field-help { width: 100%; margin: 6px 0 0; color: var(--muted); font-size: 12px; line-height: 1.7; }
.model-section-heading, .headers-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 8px 0 12px; }
.model-section-heading { padding-top: 16px; border-top: 1px solid var(--border); }
.model-section-heading h4 { margin: 0; font-size: 14px; }
.discovery-message { margin: -4px 0 12px; }
.provider-advanced { margin-top: 8px; }
.provider-header-row { display: grid; grid-template-columns: minmax(100px, 1fr) minmax(120px, 1.4fr) auto; gap: 10px; margin: 10px 0; align-items: center; }
.provider-options { display: flex; gap: 12px 24px; align-items: center; flex-wrap: wrap; margin-top: 20px; }
.provider-options :deep(.el-form-item) { margin-bottom: 0; }
.provider-dialog-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.test-action { display: flex; align-items: center; gap: 10px; }
.test-action span { color: var(--muted); font-size: 12px; }
@media (max-width: 600px) {
  .provider-toolbar { align-items: flex-start; }
  .provider-row { align-items: flex-start; flex-direction: column; gap: 12px; padding: 16px; }
  .provider-actions { flex-direction: row; align-items: center; justify-content: space-between; width: 100%; }
  .provider-form-grid { grid-template-columns: 1fr; gap: 0; }
  .provider-header-row { grid-template-columns: minmax(80px, 1fr) minmax(80px, 1fr) auto; gap: 6px; }
  .provider-dialog-footer { align-items: flex-start; }
  .test-action { flex-direction: column; align-items: flex-start; gap: 4px; }
  .provider-model-summary { flex-direction: column; gap: 6px; }
}
</style>
