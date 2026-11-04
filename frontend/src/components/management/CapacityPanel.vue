<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { managementApi } from '@/api/management'
import { useAuthStore } from '@/stores/auth'
import { managementError } from '@/utils/management'
import type { User } from '@/types/models'
import type { CapacityPlan, CapacityUser, ManagedTask } from '@/types/management'

const props = defineProps<{ week: string; tasks: ManagedTask[]; users: User[]; canWrite: boolean }>()
const auth = useAuthStore(); const plan = ref<CapacityPlan | null>(null)
const loading = ref(false); const working = ref(false); const error = ref(''); let generation = 0
const canEdit = computed(() => props.canWrite && auth.can('task.assign'))
const capacityVisible = ref(false); const capacityForm = ref({ user_id: '', available_hours: 0, note: '' })
const allocationVisible = ref(false); const allocationForm = ref({ task_id: '', user_id: '', hours: 1 })
const parentIds = computed(() => new Set(props.tasks.map(task => task.parent_task_id).filter(Boolean)))
const leafTasks = computed(() => props.tasks.filter(task => !parentIds.value.has(task.id) && task.status !== 'done'))
const allocationUsers = computed(() => {
  const selectedTask = props.tasks.find(task => task.id === allocationForm.value.task_id)
  return props.users.filter(user => selectedTask?.assignee_ids.includes(user.id))
})
const userName = (id: string) => props.users.find(user => user.id === id)?.full_name || '成员'
async function load() {
  const request = ++generation; loading.value = true; error.value = ''
  try { const response = await managementApi.capacity(props.week); if (request === generation) plan.value = response.data }
  catch (err) { if (request === generation) error.value = managementError(err, '本周容量加载失败，请重试。') }
  finally { if (request === generation) loading.value = false }
}
function editCapacity(person?: CapacityUser) {
  capacityForm.value = { user_id: person?.user_id || '', available_hours: person?.available_hours ?? 0, note: person?.note || '' }
  capacityVisible.value = true
}
async function saveCapacity() {
  if (!capacityForm.value.user_id) { error.value = '请选择成员'; return }
  if (working.value) return
  working.value = true; error.value = ''
  try { plan.value = (await managementApi.saveCapacity(props.week, capacityForm.value)).data; capacityVisible.value = false; ElMessage.success('本周可用工时已保存') }
  catch (err) { error.value = managementError(err) }
  finally { working.value = false }
}
async function saveAllocation() {
  if (!allocationForm.value.task_id || !allocationForm.value.user_id) { error.value = '请选择任务和成员'; return }
  if (working.value) return
  working.value = true; error.value = ''
  try { await managementApi.allocate({ ...allocationForm.value, week_start: props.week }); allocationVisible.value = false; await load(); ElMessage.success('本周任务工时已分配') }
  catch (err) { error.value = managementError(err) }
  finally { working.value = false }
}
async function remove(id: string) {
  if (working.value) return
  working.value = true; error.value = ''
  try { await managementApi.removeAllocation(id); await load() }
  catch (err) { error.value = managementError(err) }
  finally { working.value = false }
}
watch(() => allocationForm.value.task_id, () => { if (!allocationUsers.value.some(user => user.id === allocationForm.value.user_id)) allocationForm.value.user_id = '' })
watch(() => props.week, () => { capacityVisible.value = false; allocationVisible.value = false; void load() }, { immediate: true })
</script>

<template>
  <section v-loading="loading" class="capacity-panel">
    <div class="panel-heading"><div><h3>本周容量与分配</h3><p>{{ week }} 起始周 · 分配范围为你有权查看的项目，不代表全公司总负荷。</p></div><div v-if="canEdit" class="actions"><el-button :disabled="working" @click="editCapacity()">设置可用工时</el-button><el-button type="primary" :disabled="working" @click="allocationForm = { task_id: '', user_id: '', hours: 1 }; allocationVisible = true">分配本周工时</el-button></div></div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon><el-button link @click="load">重试</el-button></el-alert>
    <div v-if="plan" class="capacity-summary"><div><span>已知可用工时</span><strong>{{ plan.totals.available_hours }} h</strong></div><div><span>可见项目已分配</span><strong>{{ plan.totals.allocated_hours }} h</strong></div><div :class="{ danger: plan.totals.over_capacity_hours > 0 }"><span>超容量缺口</span><strong>{{ plan.totals.over_capacity_hours }} h</strong></div></div>
    <div class="people-grid"><article v-for="person in plan?.users || []" :key="person.user_id" class="person-capacity" :class="{ overloaded: (person.gap_hours || 0) > 0 }"><header><strong>{{ person.full_name }}</strong><el-tag :type="person.available_hours == null ? 'info' : person.gap_hours ? 'danger' : 'success'" size="small">{{ person.available_hours == null ? '容量未设置' : person.gap_hours ? `缺口 ${person.gap_hours} h` : '容量内' }}</el-tag></header><p>已分配 <strong>{{ person.allocated_hours }} h</strong> / 可用 {{ person.available_hours == null ? '待确认' : `${person.available_hours} h` }}</p><p v-if="person.note" class="muted">{{ person.note }}</p><el-button v-if="canEdit" link type="primary" @click="editCapacity(person)">调整容量</el-button></article></div>
    <h4>本周任务工时明细</h4><p class="muted">按每人、每个末级任务明确分配；修改同一人同一任务的工时会更新原分配。</p>
    <el-empty v-if="!plan?.allocations.length && !loading" description="本周还没有任务工时分配" />
    <article v-for="row in plan?.allocations || []" :key="row.id" class="allocation-row"><div><strong>{{ row.task_title }}</strong><p>{{ userName(row.user_id) }} · {{ row.hours }} h</p><el-tag v-if="row.excluded_from_total" type="warning" size="small">父任务分配已排除，请重新安排到末级任务</el-tag></div><el-button v-if="canEdit" link type="danger" :disabled="working" @click="remove(row.id)">取消分配</el-button></article>
    <el-dialog v-model="capacityVisible" title="设置本周可用工时" width="min(480px, calc(100vw - 24px))" :close-on-click-modal="false" :show-close="!working" :close-on-press-escape="!working"><el-form label-position="top" :disabled="working"><el-form-item label="成员" required><el-select v-model="capacityForm.user_id" filterable><el-option v-for="user in users" :key="user.id" :label="user.full_name" :value="user.id" /></el-select></el-form-item><el-form-item label="本周可用工时" required><el-input-number v-model="capacityForm.available_hours" :min="0" :max="168" :precision="1" /></el-form-item><el-form-item label="容量说明"><el-input v-model="capacityForm.note" type="textarea" :rows="2" placeholder="例如：已扣除会议和其他支持工作" /></el-form-item></el-form><el-alert v-if="error" type="error" :title="error" :closable="false" /><template #footer><el-button :disabled="working" @click="capacityVisible = false">取消</el-button><el-button type="primary" :loading="working" :disabled="working" @click="saveCapacity">保存容量</el-button></template></el-dialog>
    <el-dialog v-model="allocationVisible" title="分配本周任务工时" width="min(520px, calc(100vw - 24px))" :close-on-click-modal="false" :show-close="!working" :close-on-press-escape="!working"><el-form label-position="top" :disabled="working"><el-form-item label="当前项目末级任务" required><el-select v-model="allocationForm.task_id" filterable><el-option v-for="task in leafTasks" :key="task.id" :label="task.title" :value="task.id" /></el-select></el-form-item><el-form-item label="执行成员" required><el-select v-model="allocationForm.user_id" filterable><el-option v-for="user in allocationUsers" :key="user.id" :label="user.full_name" :value="user.id" /></el-select><p v-if="allocationForm.task_id && !allocationUsers.length" class="muted">此任务尚无执行成员，请先在责任与交付中分工。</p></el-form-item><el-form-item label="分配给该成员的本周工时" required><el-input-number v-model="allocationForm.hours" :min="0.1" :max="168" :precision="1" /></el-form-item></el-form><el-alert v-if="error" type="error" :title="error" :closable="false" /><template #footer><el-button :disabled="working" @click="allocationVisible = false">取消</el-button><el-button type="primary" :loading="working" :disabled="working" @click="saveAllocation">保存分配</el-button></template></el-dialog>
  </section>
</template>

<style scoped>
.panel-heading { display:flex; justify-content:space-between; align-items:center; gap:16px; flex-wrap:wrap; margin:8px 0 20px; }.panel-heading h3 { margin:0 0 8px; font-size:16px; }.panel-heading p,.muted { color:var(--muted); font-size:12px; line-height:1.7; margin:6px 0; }.actions { display:flex; gap:8px; flex-wrap:wrap; }.capacity-summary { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; margin:20px 0; }.capacity-summary>div { border:1px solid var(--border); background:white; padding:18px; border-radius:8px; display:flex; flex-direction:column; gap:10px; }.capacity-summary span { font-size:12px; color:var(--muted); }.capacity-summary strong { font-size:24px; }.capacity-summary .danger strong { color:#b34b42; }.people-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:14px; }.person-capacity { background:white; border:1px solid var(--border); border-radius:8px; padding:16px; font-size:13px; }.person-capacity.overloaded { border-color:#dda59b; }.person-capacity header { display:flex; align-items:center; justify-content:space-between; gap:10px; }.allocation-row { display:flex; align-items:center; justify-content:space-between; gap:16px; background:white; padding:16px; border-bottom:1px solid var(--border); font-size:13px; }.allocation-row p { margin:8px 0 0; color:var(--muted); }.allocation-row strong { overflow-wrap:anywhere; }.el-select { width:100%; }h4 { margin:28px 0 12px; font-size:14px; }
@media(max-width:600px) { .capacity-summary { gap:8px; }.capacity-summary>div { padding:12px; }.capacity-summary strong { font-size:20px; }.people-grid { grid-template-columns:1fr; } }
</style>
