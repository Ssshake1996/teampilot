<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { managementApi } from '@/api/management'
import { tasksApi } from '@/api/tasks'
import { useAuthStore } from '@/stores/auth'
import { displayDate, managementError, reviewLabels, safeEvidenceUrl } from '@/utils/management'
import type { User } from '@/types/models'
import type { ManagedTask, TaskIssue, TaskManagementDetail } from '@/types/management'

const props = defineProps<{ projectId: string; tasks: ManagedTask[]; users: User[]; canWrite: boolean }>()
const emit = defineEmits<{ changed: [] }>()
const route = useRoute(); const router = useRouter(); const auth = useAuthStore()
const selected = ref(typeof route.query.task_id === 'string' ? route.query.task_id : '')
const filter = ref('all'); const search = ref(''); const detail = ref<TaskManagementDetail | null>(null)
const loading = ref(false); const working = ref(''); const error = ref(''); let generation = 0
const responsibility = ref({ owner_id: '', collaborator_ids: [] as string[], reviewer_id: '', acceptance_criteria: '', change_reason: '' })
const delivery = ref({ deliverable_url: '', deliverable_note: '' }); const reviewNote = ref('')
const plan = ref({ deadline: null as string | null, estimated_hours: null as number | null, change_reason: '' })
const issueVisible = ref(false); const editingIssue = ref<TaskIssue | null>(null)
const issueForm = ref({ title: '', reason: '', owner_id: '', next_action: '', due_at: '', state: 'open', resolution: '' })
const visibleTasks = computed(() => props.tasks.filter(task => {
  const matches = !search.value || `${task.title} ${task.owner_name || ''}`.toLowerCase().includes(search.value.toLowerCase())
  return matches && (filter.value === 'all' || filter.value === 'owner' && task.needs_owner || filter.value === 'blocked' && task.open_issue_count > 0 || filter.value === 'review' && task.review_status === 'submitted')
}))
const userName = (id: string) => id ? props.users.find(user => user.id === id)?.full_name || '成员信息不可用' : '未指定'
const changeLabels: Record<string, string> = {
  deadline: '截止日期', start_date: '开始日期', estimated_hours: '预估工时', actual_hours: '实际工时',
  assignee_ids: '执行成员', collaborator_ids: '协作者', owner_id: '负责人', reviewer_id: '验收人',
  acceptance_criteria: '验收标准', handover_accepted: '主责接收', deliverable_url: '成果链接',
  deliverable_note: '成果说明', review_status: '验收状态', review_note: '验收意见',
  issue_title: '阻塞事项', issue_owner_id: '阻塞处理人', title: '事项名称', reason: '原因',
  next_action: '下一步', due_at: '处理期限', state: '处理状态', resolution: '解除说明',
  resolved_at: '解除时间', completed_at: '完成时间', status: '任务状态', priority: '优先级', weight: '权重',
}
const personFields = new Set(['owner_id', 'reviewer_id', 'issue_owner_id', 'assignee_ids', 'collaborator_ids'])
const dateFields = new Set(['deadline', 'start_date', 'due_at', 'resolved_at', 'completed_at'])
function changeValue(field: string, value: unknown): string {
  if (value == null || value === '') return '未设置'
  if (personFields.has(field)) return Array.isArray(value) ? value.map(item => userName(String(item))).join('、') || '无' : userName(String(value))
  if (dateFields.has(field)) return typeof value === 'string' ? displayDate(value) : '未设置'
  if (field === 'review_status') return reviewLabels[String(value)] || '状态已更新'
  if (field === 'state') return ({ open: '处理中', resolved: '已解除' } as Record<string, string>)[String(value)] || '状态已更新'
  if (field === 'status') return ({ not_started: '待开始', in_progress: '进行中', done: '已完成' } as Record<string, string>)[String(value)] || '状态已更新'
  if (field === 'priority') return ({ low: '低', medium: '普通', high: '高', urgent: '紧急' } as Record<string, string>)[String(value)] || '已调整'
  if (field === 'handover_accepted') return value ? '已接收' : '待接收'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (field === 'estimated_hours' || field === 'actual_hours') return `${value} h`
  return Array.isArray(value) ? value.map(String).join('、') || '无' : typeof value === 'object' ? '内容已更新' : String(value)
}
function applyDetail(value: TaskManagementDetail) {
  detail.value = { ...value, can_manage: value.can_manage && props.canWrite, can_deliver: value.can_deliver && props.canWrite, can_review: value.can_review && props.canWrite, can_accept_handover: value.can_accept_handover && props.canWrite }
  const governance = value.governance
  responsibility.value = { owner_id: governance?.owner_id || '', collaborator_ids: (value.task.assignee_ids || []).filter(id => id !== governance?.owner_id), reviewer_id: governance?.reviewer_id || '', acceptance_criteria: governance?.acceptance_criteria || '', change_reason: '' }
  delivery.value = { deliverable_url: governance?.deliverable_url || '', deliverable_note: governance?.deliverable_note || '' }
  reviewNote.value = ''; plan.value = { deadline: value.task.deadline, estimated_hours: value.task.estimated_hours, change_reason: '' }
}
async function load() {
  const request = ++generation; detail.value = null; error.value = ''
  if (!selected.value) return
  loading.value = true
  try { const response = await managementApi.task(selected.value); if (request === generation) applyDetail(response.data) }
  catch (err) { if (request === generation) error.value = managementError(err, '任务协作信息加载失败，请重试。') }
  finally { if (request === generation) loading.value = false }
}
async function mutate(action: string, request: () => Promise<{ data: TaskManagementDetail }>) {
  if (working.value) return
  working.value = action; error.value = ''
  try { applyDetail((await request()).data); emit('changed'); ElMessage.success('已保存'); return true }
  catch (err) { error.value = managementError(err); return false }
  finally { working.value = '' }
}
async function saveResponsibility() {
  if (!responsibility.value.owner_id || !responsibility.value.reviewer_id || !responsibility.value.acceptance_criteria.trim()) { error.value = '请明确主责、验收人和验收标准'; return }
  await mutate('responsibility', () => managementApi.responsibility(selected.value, { ...responsibility.value, collaborator_ids: responsibility.value.collaborator_ids.filter(id => id !== responsibility.value.owner_id) }))
}
async function submitDelivery() { await mutate('delivery', () => managementApi.delivery(selected.value, delivery.value)) }
async function review(decision: 'accept' | 'return') {
  if (decision === 'return' && !reviewNote.value.trim()) { error.value = '退回时请说明需要补齐的内容'; return }
  await mutate('review', () => managementApi.review(selected.value, decision, reviewNote.value))
}
function openIssue(issue?: TaskIssue) {
  editingIssue.value = issue || null
  issueForm.value = issue ? { title: issue.title, reason: issue.reason, owner_id: issue.owner_id, next_action: issue.next_action, due_at: issue.due_at, state: issue.state, resolution: issue.resolution || '' }
    : { title: '', reason: '', owner_id: detail.value?.governance?.owner_id || auth.user?.id || '', next_action: '', due_at: '', state: 'open', resolution: '' }
  issueVisible.value = true
}
async function saveIssue() {
  if (!issueForm.value.title.trim() || !issueForm.value.owner_id || !issueForm.value.due_at || !issueForm.value.next_action.trim()) { error.value = '请填写阻塞事项、处理人、下一步和处理期限'; return }
  const { state, resolution, ...payload } = issueForm.value
  const success = await mutate('issue', () => editingIssue.value
    ? managementApi.updateIssue(selected.value, editingIssue.value.id, { ...payload, state, resolution })
    : managementApi.issue(selected.value, payload))
  if (success) issueVisible.value = false
}
async function savePlan() {
  if (!plan.value.change_reason.trim()) { error.value = '请说明调整计划的原因'; return }
  if (working.value) return
  working.value = 'plan'; error.value = ''
  try {
    await tasksApi.update(selected.value, { change_reason: plan.value.change_reason,
      ...(auth.can('task.set_deadline') ? { deadline: plan.value.deadline } : {}),
      ...(auth.can('task.set_hours') ? { estimated_hours: plan.value.estimated_hours } : {}),
    }); await load(); emit('changed'); ElMessage.success('计划已调整并保留记录')
  }
  catch (err) { error.value = managementError(err) }
  finally { working.value = '' }
}
watch(() => props.tasks, tasks => { if (!tasks.some(task => task.id === selected.value)) selected.value = tasks[0]?.id || '' }, { immediate: true })
watch(selected, () => { void router.replace({ query: { ...route.query, task_id: selected.value || undefined } }); void load() }, { immediate: true })
watch(() => route.query.task_id, id => { if (!working.value && typeof id === 'string' && props.tasks.some(task => task.id === id)) selected.value = id })
watch(() => props.projectId, () => { detail.value = null; issueVisible.value = false })
</script>

<template>
  <div class="task-management-layout">
    <aside class="managed-task-list">
      <el-input v-model="search" placeholder="搜索任务或主责" aria-label="搜索协作任务" clearable />
      <el-select v-model="filter" aria-label="任务协作筛选"><el-option label="全部任务" value="all" /><el-option label="待明确主责" value="owner" /><el-option label="存在未解除阻塞" value="blocked" /><el-option label="待验收" value="review" /></el-select>
      <el-empty v-if="!visibleTasks.length" description="没有符合条件的任务" :image-size="60" />
      <button v-for="task in visibleTasks" :key="task.id" class="managed-task" :class="{ selected: task.id === selected }" :disabled="!!working" @click="selected = task.id">
        <strong>{{ task.title }}</strong><span>{{ task.owner_name || '待明确主责' }} · {{ task.progress_pct }}%</span>
        <span class="task-tags"><el-tag v-if="task.open_issue_count" type="danger" size="small">{{ task.open_issue_count }} 项阻塞</el-tag><el-tag v-if="task.handover_pending" type="warning" size="small">待接收</el-tag><el-tag v-if="task.review_status === 'submitted'" type="warning" size="small">待验收</el-tag></span>
      </button>
    </aside>
    <section v-loading="loading" class="managed-task-detail">
      <el-alert v-if="error" type="error" :title="error" show-icon :closable="false"><el-button v-if="!detail" link @click="load">重试</el-button></el-alert>
      <el-empty v-if="!selected" description="选择一个任务，明确责任与交付要求" />
      <template v-if="detail">
        <div class="detail-heading"><h3>{{ detail.task.title }}</h3><el-tag>{{ detail.task.progress_pct }}% · {{ reviewLabels[detail.governance?.review_status || 'not_submitted'] }}</el-tag></div>
        <el-alert v-if="detail.needs_owner" title="此任务尚未明确单一主责，请在下方完成责任分工。" type="warning" :closable="false" />
        <div class="management-card">
          <h4>责任与验收标准</h4>
          <el-form label-position="top" :disabled="!!working || !detail.can_manage">
            <div class="form-grid"><el-form-item label="交付主责" required><el-select v-model="responsibility.owner_id" filterable placeholder="选择一名主责"><el-option v-for="user in users" :key="user.id" :label="user.full_name" :value="user.id" /></el-select></el-form-item>
              <el-form-item label="指定验收人" required><el-select v-model="responsibility.reviewer_id" filterable placeholder="选择验收人"><el-option v-for="user in users" :key="user.id" :label="user.full_name" :value="user.id" /></el-select></el-form-item></div>
            <el-form-item label="协作者"><el-select v-model="responsibility.collaborator_ids" multiple filterable collapse-tags><el-option v-for="user in users.filter(item => item.id !== responsibility.owner_id)" :key="user.id" :label="user.full_name" :value="user.id" /></el-select></el-form-item>
            <el-form-item label="验收标准" required><el-input v-model="responsibility.acceptance_criteria" type="textarea" :rows="3" placeholder="写清交付内容与通过条件" /></el-form-item>
            <el-form-item v-if="detail.can_manage" label="分工 / 标准变更原因"><el-input v-model="responsibility.change_reason" placeholder="说明调整原因和交接事项" /></el-form-item>
          </el-form>
          <div class="card-actions"><el-button v-if="detail.can_manage" type="primary" :loading="working === 'responsibility'" :disabled="!!working" @click="saveResponsibility">保存分工</el-button>
            <el-button v-if="detail.can_accept_handover && !detail.governance?.handover_accepted_at" :loading="working === 'handover'" :disabled="!!working" @click="mutate('handover', () => managementApi.handover(selected, '已确认交付要求并接受主责'))">我已确认并接受主责</el-button>
            <span class="muted">{{ detail.governance?.handover_accepted_at ? `主责已接收 · ${displayDate(detail.governance.handover_accepted_at)}` : '主责尚未接收' }}</span></div>
        </div>
        <div class="management-card">
          <div class="section-heading"><h4>持续阻塞与协助事项</h4><el-button v-if="canWrite && auth.can('progress.submit')" :disabled="!!working" @click="openIssue()">新增阻塞</el-button></div>
          <p v-if="!detail.issues.length" class="muted">暂无阻塞事项。</p>
          <article v-for="issue in detail.issues" :key="issue.id" class="issue-row">
            <div><strong>{{ issue.title }}</strong> <el-tag :type="issue.state === 'resolved' ? 'success' : issue.is_overdue ? 'danger' : 'warning'" size="small">{{ issue.state === 'resolved' ? '已解除' : issue.is_overdue ? '超期 · 需升级处理' : '处理中' }}</el-tag></div>
            <p>{{ issue.reason }}</p><p>处理人 {{ issue.owner_name }} · 期限 {{ displayDate(issue.due_at) }}</p><p v-if="issue.is_overdue && issue.state === 'open' && issue.escalation_owner_id">升级对象：{{ userName(issue.escalation_owner_id) }}</p><p>下一步：{{ issue.next_action }}</p>
            <p v-if="issue.resolution">解除记录：{{ issue.resolution }}</p><el-button v-if="canWrite && (auth.can('task.assign') || [issue.owner_id, issue.reporter_id].includes(auth.user?.id || ''))" link type="primary" @click="openIssue(issue)">更新处理 / 解除</el-button>
          </article>
        </div>
        <div class="management-card">
          <h4>提交成果与验收</h4>
          <el-form label-position="top" :disabled="!!working || !detail.can_deliver">
            <el-form-item label="成果链接"><el-input v-model="delivery.deliverable_url" placeholder="https://…" /></el-form-item>
            <el-form-item label="成果说明"><el-input v-model="delivery.deliverable_note" type="textarea" :rows="3" placeholder="说明交付内容、验证结果及对应验收标准" /></el-form-item>
          </el-form>
          <p v-if="safeEvidenceUrl(detail.governance?.deliverable_url)"><a :href="safeEvidenceUrl(detail.governance?.deliverable_url)" target="_blank" rel="noopener noreferrer">打开已提交的成果</a></p>
          <el-button v-if="detail.can_deliver" type="primary" :disabled="!!working" :loading="working === 'delivery'" @click="submitDelivery">提交成果待验收</el-button>
          <el-alert v-if="detail.governance?.review_note" :title="`验收意见：${detail.governance.review_note}`" :type="detail.governance.review_status === 'changes_requested' ? 'warning' : 'success'" :closable="false" />
          <div v-if="detail.can_review" class="review-actions"><el-input v-model="reviewNote" type="textarea" :rows="2" placeholder="验收意见；退回时说明需要补齐的内容" :disabled="!!working" /><div class="card-actions"><el-button type="success" :disabled="!!working || detail.task.progress_pct < 100 || detail.governance?.review_status !== 'submitted'" :loading="working === 'review'" @click="review('accept')">通过验收并完成</el-button><el-button type="warning" :disabled="!!working || detail.governance?.review_status !== 'submitted'" @click="review('return')">退回补充</el-button><span class="muted">通过验收需进度达到 100%。</span></div></div>
        </div>
        <div v-if="detail.can_manage && (auth.can('task.set_deadline') || auth.can('task.set_hours'))" class="management-card">
          <h4>调整计划</h4><el-form label-position="top" :disabled="!!working"><div class="form-grid"><el-form-item v-if="auth.can('task.set_deadline')" label="当前截止日期"><el-date-picker v-model="plan.deadline" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" /></el-form-item><el-form-item v-if="auth.can('task.set_hours')" label="预估工时"><el-input-number v-model="plan.estimated_hours" :min="0" :precision="1" /></el-form-item></div><el-form-item label="变更原因" required><el-input v-model="plan.change_reason" placeholder="说明范围、资源或计划发生了什么变化" /></el-form-item><el-button :loading="working === 'plan'" :disabled="!!working" @click="savePlan">保存计划变更</el-button></el-form>
        </div>
        <div class="management-card"><h4>关键变更记录</h4><p v-if="!detail.changes.length" class="muted">暂无关键变更记录。</p><article v-for="change in detail.changes" :key="change.id" class="change-row"><strong>{{ change.actor_name }} · {{ displayDate(change.created_at) }}</strong><p>{{ change.reason || '未填写原因' }}</p><p v-for="(value, field) in change.after_json" :key="field">{{ changeLabels[field] || '其他调整' }}：{{ changeValue(field, change.before_json[field]) }} → {{ changeValue(field, value) }}</p></article></div>
      </template>
    </section>
    <el-dialog v-model="issueVisible" :title="editingIssue ? '更新阻塞处理' : '新增阻塞事项'" width="min(600px, calc(100vw - 24px))" :close-on-click-modal="false" :close-on-press-escape="!working" :show-close="!working">
      <el-form label-position="top" :disabled="!!working"><el-form-item label="事项" required><el-input v-model="issueForm.title" /></el-form-item><el-form-item label="原因"><el-input v-model="issueForm.reason" type="textarea" :rows="2" /></el-form-item><div class="form-grid"><el-form-item label="处理人" required><el-select v-model="issueForm.owner_id" filterable><el-option v-for="user in users" :key="user.id" :label="user.full_name" :value="user.id" /></el-select></el-form-item><el-form-item label="处理期限" required><el-date-picker v-model="issueForm.due_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" /></el-form-item></div><el-form-item label="下一步" required><el-input v-model="issueForm.next_action" type="textarea" :rows="2" /></el-form-item><template v-if="editingIssue"><el-form-item label="状态"><el-radio-group v-model="issueForm.state"><el-radio value="open">继续处理</el-radio><el-radio value="resolved">已解除</el-radio></el-radio-group></el-form-item><el-form-item v-if="issueForm.state === 'resolved'" label="解除说明" required><el-input v-model="issueForm.resolution" type="textarea" :rows="2" /></el-form-item></template></el-form>
      <el-alert v-if="error" type="error" :title="error" :closable="false" /><template #footer><el-button :disabled="!!working" @click="issueVisible = false">取消</el-button><el-button type="primary" :loading="working === 'issue'" :disabled="!!working" @click="saveIssue">保存处理记录</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.task-management-layout { display:grid; grid-template-columns:260px minmax(0,1fr); gap:20px; align-items:start; }.managed-task-list { display:flex; flex-direction:column; gap:10px; max-height:75vh; overflow:auto; }.managed-task { display:flex; flex-direction:column; gap:8px; background:white; border:1px solid var(--border); border-radius:7px; padding:14px; text-align:left; cursor:pointer; color:var(--ink); }.managed-task.selected { border-color:var(--brand); background:#f0f8f6; }.managed-task strong { font-size:13px; line-height:1.6; overflow-wrap:anywhere; }.managed-task>span { font-size:12px; color:var(--muted); }.task-tags { display:flex; gap:6px; flex-wrap:wrap; }.managed-task-detail { min-width:0; }.detail-heading,.section-heading { display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; }.detail-heading h3 { font-size:17px; margin:0 0 12px; }.management-card { background:white; border:1px solid var(--border); border-radius:8px; padding:20px; margin:14px 0; }.management-card h4 { margin:0 0 16px; font-size:14px; }.form-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; }.el-select { width:100%; }.form-grid :deep(.el-date-editor) { width:100%; }.card-actions { display:flex; flex-wrap:wrap; align-items:center; gap:10px; }.muted { color:var(--muted); font-size:12px; line-height:1.7; }.issue-row,.change-row { padding:14px 0; border-top:1px solid var(--border); font-size:13px; overflow-wrap:anywhere; }.issue-row p,.change-row p { margin:8px 0; line-height:1.7; }.review-actions { margin-top:16px; }.review-actions .card-actions { margin-top:12px; }a { color:var(--brand); }
@media(max-width:900px) { .task-management-layout { grid-template-columns:1fr; }.managed-task-list { max-height:260px; }.form-grid { grid-template-columns:1fr; gap:0; }.management-card { padding:16px; } }
</style>
