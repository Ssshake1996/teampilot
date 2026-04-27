<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { dataSkillsApi } from '@/api/dataSkills'
import type { DataConnector, SkillRun, Task, TaskDataSkill, TaskProgress } from '@/types/models'

const props = defineProps<{
  task: Task
  canManageProgress: boolean
}>()

const emit = defineEmits<{
  (event: 'progress-adopted', payload: TaskProgress): void
}>()

const connectors = ref<DataConnector[]>([])
const skills = ref<TaskDataSkill[]>([])
const runs = ref<SkillRun[]>([])
const selectedSkillId = ref('')
const naturalLanguage = ref('')
const selectedConnectorId = ref('')
const paramsText = ref('')
const loading = ref(false)
const generating = ref(false)
const confirming = ref(false)
const running = ref(false)
const adopting = ref(false)

const selectedSkill = computed(() => skills.value.find((item) => item.id === selectedSkillId.value) || null)
const latestRun = computed(() => runs.value.find((item) => item.task_data_skill_id === selectedSkillId.value) || runs.value[0] || null)

function formatDateTime(value: string | null): string {
  if (!value) return '-'
  return value.replace('T', ' ').slice(0, 16)
}

function prettyJson(value: Record<string, any> | null | undefined): string {
  return JSON.stringify(value || {}, null, 2)
}

async function loadPanel() {
  if (!props.task?.id) return
  loading.value = true
  try {
    const [skillsRes, runsRes] = await Promise.all([
      dataSkillsApi.listTaskSkills(props.task.id),
      dataSkillsApi.listRuns(props.task.id),
    ])
    skills.value = skillsRes.data
    runs.value = runsRes.data
    selectedSkillId.value = skills.value[0]?.id || ''
  } catch {
    skills.value = []
    runs.value = []
  } finally {
    loading.value = false
  }

  try {
    const connectorRes = await dataSkillsApi.listConnectors()
    connectors.value = connectorRes.data.filter((item) => item.is_enabled)
  } catch {
    connectors.value = []
  }
}

async function generateSkill() {
  if (!naturalLanguage.value.trim()) {
    ElMessage.warning('请填写数据说明')
    return
  }
  generating.value = true
  try {
    const res = await dataSkillsApi.generateTaskSkill(props.task.id, {
      natural_language: naturalLanguage.value.trim(),
      connector_id: selectedConnectorId.value || undefined,
    })
    skills.value = [res.data, ...skills.value]
    selectedSkillId.value = res.data.id
    ElMessage.success('数据 Skill 已生成')
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '生成失败')
  } finally {
    generating.value = false
  }
}

async function confirmSkill() {
  if (!selectedSkill.value) return
  confirming.value = true
  try {
    const res = await dataSkillsApi.confirmTaskSkill(props.task.id, selectedSkill.value.id)
    skills.value = skills.value.map((item) => item.id === res.data.id ? res.data : item)
    ElMessage.success('数据 Skill 已确认')
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '确认失败')
  } finally {
    confirming.value = false
  }
}

function parseParams(): Record<string, any> {
  if (!paramsText.value.trim()) return {}
  return JSON.parse(paramsText.value)
}

async function runSkill() {
  if (!selectedSkill.value) return
  let params: Record<string, any>
  try {
    params = parseParams()
  } catch {
    ElMessage.error('参数 JSON 格式不正确')
    return
  }
  running.value = true
  try {
    const res = await dataSkillsApi.runTaskSkill(props.task.id, selectedSkill.value.id, {
      params,
      use_ai: true,
    })
    runs.value = [res.data, ...runs.value.filter((item) => item.id !== res.data.id)]
    if (res.data.status === 'success') {
      ElMessage.success('执行完成')
    } else {
      ElMessage.warning(res.data.error_message || '执行失败')
    }
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '执行失败')
  } finally {
    running.value = false
  }
}

async function adoptRun() {
  if (!latestRun.value || latestRun.value.status !== 'success') return
  adopting.value = true
  try {
    const res = await dataSkillsApi.adoptRun(props.task.id, latestRun.value.id, {
      progress_pct: latestRun.value.suggested_progress_pct ?? undefined,
      note: latestRun.value.suggested_note || undefined,
    })
    emit('progress-adopted', res.data)
    ElMessage.success('已采纳为任务进展')
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '采纳失败')
  } finally {
    adopting.value = false
  }
}

watch(() => props.task.id, () => {
  naturalLanguage.value = ''
  selectedConnectorId.value = ''
  paramsText.value = ''
  loadPanel()
}, { immediate: true })
</script>

<template>
  <div v-loading="loading" class="data-skill-panel">
    <div v-if="canManageProgress && !task.is_deleted" class="data-skill-create">
      <el-input
        v-model="naturalLanguage"
        type="textarea"
        :rows="3"
        placeholder="这个任务的数据从测试平台获取。接口是 GET /api/test/feature/{feature_id}/summary。"
      />
      <div class="data-skill-actions">
        <el-select
          v-model="selectedConnectorId"
          clearable
          filterable
          placeholder="连接器"
          class="connector-select"
        >
          <el-option
            v-for="connector in connectors"
            :key="connector.id"
            :label="connector.name"
            :value="connector.id"
          />
        </el-select>
        <el-button type="primary" :loading="generating" @click="generateSkill">AI 生成 Skill</el-button>
      </div>
    </div>

    <div v-if="skills.length" class="data-skill-runtime">
      <div class="data-skill-selector">
        <el-select v-model="selectedSkillId" placeholder="选择 Skill" style="width: 100%">
          <el-option
            v-for="skill in skills"
            :key="skill.id"
            :label="skill.natural_language.slice(0, 36)"
            :value="skill.id"
          />
        </el-select>
        <el-tag v-if="selectedSkill" :type="selectedSkill.status === 'confirmed' ? 'success' : 'warning'" effect="plain">
          {{ selectedSkill.status === 'confirmed' ? '已确认' : '草稿' }}
        </el-tag>
      </div>

      <template v-if="selectedSkill">
        <div class="skill-meta">
          <span>{{ selectedSkill.connector_name || '未绑定连接器' }}</span>
          <span>{{ formatDateTime(selectedSkill.updated_at) }}</span>
        </div>
        <el-input
          v-model="paramsText"
          type="textarea"
          :rows="2"
          placeholder='可选参数 JSON，例如 {"feature_id":"FEAT-1024"}'
        />
        <div class="data-skill-actions">
          <el-button :loading="confirming" @click="confirmSkill">确认 Skill</el-button>
          <el-button type="warning" :loading="running" @click="runSkill">执行采集</el-button>
          <el-button
            type="success"
            :loading="adopting"
            :disabled="!latestRun || latestRun.status !== 'success' || latestRun.suggested_progress_pct == null"
            @click="adoptRun"
          >
            采纳进展
          </el-button>
        </div>

        <div v-if="latestRun" class="run-result" :class="{ failed: latestRun.status === 'failed' }">
          <div class="run-result-head">
            <el-tag :type="latestRun.status === 'success' ? 'success' : 'danger'" size="small">
              {{ latestRun.status === 'success' ? '成功' : '失败' }}
            </el-tag>
            <span>{{ formatDateTime(latestRun.created_at) }}</span>
            <strong v-if="latestRun.suggested_progress_pct != null">{{ latestRun.suggested_progress_pct }}%</strong>
          </div>
          <p v-if="latestRun.suggested_note">{{ latestRun.suggested_note }}</p>
          <p v-if="latestRun.error_message">{{ latestRun.error_message }}</p>
          <el-collapse class="run-json">
            <el-collapse-item title="Skill JSON" name="skill">
              <pre>{{ prettyJson(selectedSkill.skill_json) }}</pre>
            </el-collapse-item>
            <el-collapse-item title="指标与返回" name="metrics">
              <pre>{{ prettyJson({ metrics: latestRun.metrics_json, response: latestRun.response_json }) }}</pre>
            </el-collapse-item>
          </el-collapse>
        </div>
      </template>
    </div>

    <el-empty v-else description="暂无数据 Skill" :image-size="48" />
  </div>
</template>

<style scoped>
.data-skill-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.data-skill-create,
.data-skill-runtime {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.data-skill-actions,
.data-skill-selector,
.skill-meta,
.run-result-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.connector-select {
  flex: 1 1 180px;
  min-width: 160px;
}

.skill-meta {
  justify-content: space-between;
  font-size: 12px;
  color: #909399;
}

.run-result {
  border: 1px solid #e1f3d8;
  background: #f0f9eb;
  border-radius: 6px;
  padding: 10px;
}

.run-result.failed {
  border-color: #fde2e2;
  background: #fef0f0;
}

.run-result-head {
  justify-content: space-between;
  font-size: 12px;
  color: #606266;
}

.run-result p {
  margin: 8px 0 0;
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
}

.run-json {
  margin-top: 8px;
}

.run-json pre {
  max-height: 220px;
  overflow: auto;
  margin: 0;
  padding: 8px;
  border-radius: 4px;
  background: #1f2937;
  color: #e5e7eb;
  font-size: 12px;
  line-height: 1.5;
}
</style>
