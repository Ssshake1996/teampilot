<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { managementApi } from '@/api/management'
import { useAuthStore } from '@/stores/auth'
import { displayDate, managementError } from '@/utils/management'
import type { User } from '@/types/models'
import type { Commitment, ManagedTask, Retrospective } from '@/types/management'

const props = defineProps<{ projectId: string; week: string; tasks: ManagedTask[]; users: User[]; canWrite: boolean }>()
const emit = defineEmits<{ changed: [] }>(); const auth = useAuthStore()
const commitments = ref<Commitment[]>([]); const retrospectives = ref<Retrospective[]>([])
const outcomeNotes = ref<Record<string, string>>({}); const loading = ref(false); const working = ref(''); const error = ref(''); let generation = 0
const canCommit = computed(() => props.canWrite && auth.can('task.assign')); const canRetrospect = computed(() => props.canWrite && auth.can('task.create'))
const commitmentVisible = ref(false); const commitment = ref({ task_id: '', owner_id: '', expected_outcome: '' })
const retroVisible = ref(false); const retro = ref({ summary: '', decisions: '', actions: [] as { title: string; owner_id: string; deadline: string; acceptance_criteria: string }[] })
const statusLabels: Record<string, string> = { committed: '已承诺 · 待交付', delivered: '本周已验收', missed: '未按周交付' }
const userName = (id: string) => props.users.find(user => user.id === id)?.full_name || '未指定'
async function load() {
  const request = ++generation; loading.value = true; error.value = ''
  try {
    const [commitmentRows, retroRows] = await Promise.all([managementApi.commitments(props.projectId, props.week), managementApi.retrospectives(props.projectId, props.week)])
    if (request !== generation) return
    commitments.value = commitmentRows.data; retrospectives.value = retroRows.data
    outcomeNotes.value = Object.fromEntries(commitments.value.map(item => [item.id, item.outcome_note || '']))
  } catch (err) { if (request === generation) error.value = managementError(err, '周承诺与复盘加载失败，请重试。') }
  finally { if (request === generation) loading.value = false }
}
async function saveCommitment() {
  if (!commitment.value.task_id || !commitment.value.owner_id || !commitment.value.expected_outcome.trim()) { error.value = '请明确任务、承诺人和本周可验收成果'; return }
  if (working.value) return
  working.value = 'commitment'; error.value = ''
  try { await managementApi.commit({ ...commitment.value, week_start: props.week }); commitmentVisible.value = false; await load(); ElMessage.success('本周交付承诺已记录') }
  catch (err) { error.value = managementError(err) } finally { working.value = '' }
}
async function saveOutcome(item: Commitment) {
  if (working.value) return
  working.value = item.id; error.value = ''
  try { await managementApi.updateCommitment(item.id, { outcome_note: outcomeNotes.value[item.id] || '' }); await load(); ElMessage.success('交付结果与偏差说明已保存') }
  catch (err) { error.value = managementError(err) } finally { working.value = '' }
}
async function saveRetro() {
  if (!retro.value.summary.trim()) { error.value = '请填写本周实际交付和主要偏差'; return }
  if (retro.value.actions.some(action => !action.title.trim() || !action.owner_id || !action.deadline)) { error.value = '每项改进行动都需要名称、主责和截止日期'; return }
  if (working.value) return
  working.value = 'retro'; error.value = ''
  try { await managementApi.retrospect({ ...retro.value, project_id: props.projectId, week_start: props.week }); retroVisible.value = false; await load(); emit('changed'); ElMessage.success('复盘已保存，改进行动已生成任务') }
  catch (err) { error.value = managementError(err) } finally { working.value = '' }
}
watch(() => commitment.value.task_id, id => { const task = props.tasks.find(item => item.id === id); if (task?.owner_id) commitment.value.owner_id = task.owner_id })
watch(() => [props.projectId, props.week], () => { commitmentVisible.value = false; retroVisible.value = false; void load() }, { immediate: true })
</script>

<template>
  <section v-loading="loading" class="weekly-review-panel">
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon><el-button link @click="load">重试</el-button></el-alert>
    <div class="section-heading"><div><h3>本周承诺与实际交付</h3><p>{{ week }} 起始周 · 交付状态根据会签验收事实判断。</p></div><el-button v-if="canCommit" type="primary" :disabled="!!working" @click="commitment = { task_id: '', owner_id: '', expected_outcome: '' }; commitmentVisible = true">新增交付承诺</el-button></div>
    <el-empty v-if="!commitments.length && !loading" description="此周暂无交付承诺" :image-size="60" />
    <article v-for="item in commitments" :key="item.id" class="commitment-card"><header><strong>{{ item.task_title }}</strong><el-tag :type="item.status === 'delivered' ? 'success' : item.status === 'missed' ? 'danger' : 'info'" size="small">{{ statusLabels[item.status] || item.status }}</el-tag></header><p class="muted">承诺人 {{ userName(item.owner_id) }}<span v-if="item.signed_off_at"> · 验收时间 {{ displayDate(item.signed_off_at) }}</span></p><p><strong>承诺成果：</strong>{{ item.expected_outcome }}</p><el-input v-if="canCommit" v-model="outcomeNotes[item.id]" type="textarea" :rows="2" placeholder="实际交付、未完成原因与下一步" :disabled="!!working" /><p v-else>结果与偏差：{{ item.outcome_note || '尚未补充' }}</p><el-button v-if="canCommit" link type="primary" :loading="working === item.id" :disabled="!!working" @click="saveOutcome(item)">保存结果说明</el-button></article>
    <div class="section-heading"><div><h3>周复盘与改进行动</h3><p>保留结论，并把后续行动落实为有主责和期限的任务。</p></div><el-button v-if="canRetrospect" :disabled="!!working" @click="retro = { summary: '', decisions: '', actions: [] }; retroVisible = true">记录复盘</el-button></div>
    <el-empty v-if="!retrospectives.length && !loading" description="此周暂无复盘记录" :image-size="60" />
    <article v-for="item in retrospectives" :key="item.id" class="retro-card"><h4>承诺与结果</h4><p class="preserve-lines">{{ item.summary }}</p><h4>决定与调整</h4><p class="preserve-lines">{{ item.decisions || '未补充' }}</p><h4>改进行动</h4><p v-if="!item.action_tasks.length" class="muted">本次复盘没有新增行动任务。</p><div v-for="action in item.action_tasks" :key="action.task_id" class="action-task"><RouterLink :to="{ path: '/management', query: { project_id: projectId, task_id: action.task_id, tab: 'tasks' } }">{{ action.title }}</RouterLink><span>{{ userName(action.owner_id) }} · {{ displayDate(action.deadline) }} · {{ action.status === 'done' ? '已完成' : '待跟进' }}</span></div></article>
    <el-dialog v-model="commitmentVisible" title="记录本周交付承诺" width="min(580px, calc(100vw - 24px))" :close-on-click-modal="false" :show-close="!working" :close-on-press-escape="!working"><el-form label-position="top" :disabled="!!working"><el-form-item label="交付任务" required><el-select v-model="commitment.task_id" filterable><el-option v-for="task in tasks" :key="task.id" :label="task.title" :value="task.id" /></el-select></el-form-item><el-form-item label="承诺人" required><el-select v-model="commitment.owner_id" filterable><el-option v-for="user in users" :key="user.id" :label="user.full_name" :value="user.id" /></el-select></el-form-item><el-form-item label="本周可验收成果" required><el-input v-model="commitment.expected_outcome" type="textarea" :rows="3" placeholder="说明本周要交付什么，以及判断交付的标准" /></el-form-item></el-form><el-alert v-if="error" type="error" :title="error" :closable="false" /><template #footer><el-button :disabled="!!working" @click="commitmentVisible = false">取消</el-button><el-button type="primary" :loading="working === 'commitment'" :disabled="!!working" @click="saveCommitment">保存承诺</el-button></template></el-dialog>
    <el-dialog v-model="retroVisible" title="记录复盘与改进行动" width="min(740px, calc(100vw - 24px))" top="5vh" :close-on-click-modal="false" :show-close="!working" :close-on-press-escape="!working"><el-form label-position="top" :disabled="!!working"><el-form-item label="实际交付与主要偏差" required><el-input v-model="retro.summary" type="textarea" :rows="4" placeholder="本周承诺兑现了什么？哪些事项未完成，原因是什么？" /></el-form-item><el-form-item label="决定与调整"><el-input v-model="retro.decisions" type="textarea" :rows="3" placeholder="下一周的范围、顺序、资源或工作方式如何调整？" /></el-form-item><p class="muted">行动将直接创建任务，所选主责需要确认接手，复盘创建人负责验收。</p><div class="section-heading"><h4>改进行动</h4><el-button @click="retro.actions.push({ title: '', owner_id: '', deadline: '', acceptance_criteria: '' })">添加行动</el-button></div><article v-for="(action, index) in retro.actions" :key="index" class="retro-action-form"><el-form-item :label="`行动 ${index + 1}`" required><el-input v-model="action.title" placeholder="行动任务名称" /></el-form-item><el-form-item label="验收标准"><el-input v-model="action.acceptance_criteria" placeholder="可留空，默认使用行动任务名称" /></el-form-item><div class="form-grid"><el-form-item label="主责" required><el-select v-model="action.owner_id" filterable><el-option v-for="user in users" :key="user.id" :label="user.full_name" :value="user.id" /></el-select></el-form-item><el-form-item label="截止日期" required><el-date-picker v-model="action.deadline" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" /></el-form-item></div><el-button link type="danger" @click="retro.actions.splice(index, 1)">移除此行动</el-button></article></el-form><el-alert v-if="error" type="error" :title="error" :closable="false" /><template #footer><el-button :disabled="!!working" @click="retroVisible = false">取消</el-button><el-button type="primary" :loading="working === 'retro'" :disabled="!!working" @click="saveRetro">保存复盘并创建行动任务</el-button></template></el-dialog>
  </section>
</template>

<style scoped>
.section-heading { display:flex; justify-content:space-between; align-items:center; gap:16px; flex-wrap:wrap; margin:20px 0 16px; }.section-heading h3 { margin:0 0 8px; font-size:16px; }.section-heading p,.muted { font-size:12px; color:var(--muted); line-height:1.7; }.commitment-card,.retro-card { padding:20px; border:1px solid var(--border); border-radius:8px; background:white; margin-bottom:14px; font-size:13px; line-height:1.8; }.commitment-card header { display:flex; align-items:center; gap:12px; flex-wrap:wrap; }.commitment-card p { overflow-wrap:anywhere; }.commitment-card .el-button { margin-top:8px; }.retro-card h4 { margin:16px 0 8px; font-size:13px; }.retro-card h4:first-child { margin-top:0; }.preserve-lines { white-space:pre-wrap; overflow-wrap:anywhere; }.action-task { border-top:1px solid var(--border); padding:10px 0; display:flex; justify-content:space-between; gap:14px; flex-wrap:wrap; }.action-task a { color:var(--brand); }.action-task span { font-size:12px; color:var(--muted); }.retro-action-form { border:1px solid var(--border); padding:14px; margin:12px 0; border-radius:6px; }.form-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; }.el-select { width:100%; }.form-grid :deep(.el-date-editor) { width:100%; }
@media(max-width:600px) { .commitment-card,.retro-card { padding:16px; }.form-grid { grid-template-columns:1fr; gap:0; } }
</style>
