<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { managementApi } from '@/api/management'
import { useAuthStore } from '@/stores/auth'
import { displayDate, managementError } from '@/utils/management'
import type { Project, User } from '@/types/models'
import type { Dependency, ManagedTask, Milestone, PlanBaseline } from '@/types/management'

const props = defineProps<{ projectId: string; tasks: ManagedTask[]; users: User[]; projects: Project[]; canWrite: boolean }>()
const emit = defineEmits<{ changed: [] }>(); const auth = useAuthStore()
const milestones = ref<Milestone[]>([]); const dependencies = ref<Dependency[]>([]); const baselines = ref<PlanBaseline[]>([]); const allTasks = ref<ManagedTask[]>([])
const loading = ref(false); const working = ref(''); const error = ref(''); let generation = 0
const canPlan = computed(() => props.canWrite && auth.can('project.edit')); const canDepend = computed(() => props.canWrite && auth.can('task.edit'))
const milestoneVisible = ref(false); const editingMilestone = ref(''); const milestone = ref({ name: '', owner_id: '', due_date: '', task_ids: [] as string[] })
const dependencyVisible = ref(false); const dependency = ref({ predecessor_id: '', successor_id: '' })
const baselineLabel = ref(''); const selectedBaseline = ref('')
const baseline = computed(() => baselines.value.find(item => item.id === selectedBaseline.value))
const userName = (id: string) => props.users.find(user => user.id === id)?.full_name || '未指定'
const taskLabel = (task: ManagedTask) => `${props.projects.find(project => project.id === task.project_id)?.name || '项目'} / ${task.title}`
async function load() {
  const request = ++generation; loading.value = true; error.value = ''
  try {
    const [milestoneRows, dependencyRows, baselineRows, taskRows] = await Promise.all([managementApi.milestones(props.projectId), managementApi.dependencies(props.projectId), managementApi.baselines(props.projectId), managementApi.tasks()])
    if (request !== generation) return
    milestones.value = milestoneRows.data; dependencies.value = dependencyRows.data; baselines.value = baselineRows.data; allTasks.value = taskRows.data
    if (!baselines.value.some(item => item.id === selectedBaseline.value)) selectedBaseline.value = baselines.value[0]?.id || ''
  } catch (err) { if (request === generation) error.value = managementError(err, '交付计划加载失败，请重试。') }
  finally { if (request === generation) loading.value = false }
}
function editMilestone(item?: Milestone) {
  editingMilestone.value = item?.id || ''
  milestone.value = item ? { name: item.name, owner_id: item.owner_id, due_date: item.due_date, task_ids: [...item.task_ids] } : { name: '', owner_id: '', due_date: '', task_ids: [] }
  milestoneVisible.value = true
}
async function saveMilestone() {
  if (!milestone.value.name.trim() || !milestone.value.owner_id || !milestone.value.due_date) { error.value = '请填写里程碑名称、主责和日期'; return }
  if (working.value) return
  working.value = 'milestone'; error.value = ''
  try { await managementApi.saveMilestone({ ...milestone.value, project_id: props.projectId }, editingMilestone.value || undefined); milestoneVisible.value = false; await load(); ElMessage.success('里程碑已保存') }
  catch (err) { error.value = managementError(err) } finally { working.value = '' }
}
async function removeMilestone(id: string) {
  try { await ElMessageBox.confirm('删除此里程碑？关联任务会保留。', '删除里程碑', { type: 'warning' }) } catch { return }
  working.value = 'delete'; error.value = ''
  try { await managementApi.removeMilestone(id); await load() } catch (err) { error.value = managementError(err) } finally { working.value = '' }
}
async function saveDependency() {
  if (!dependency.value.predecessor_id || !dependency.value.successor_id) { error.value = '请选择前置任务和后续任务'; return }
  if (working.value) return
  working.value = 'dependency'; error.value = ''
  try { await managementApi.depend(dependency.value.predecessor_id, dependency.value.successor_id); dependencyVisible.value = false; await load(); ElMessage.success('任务依赖已保存') }
  catch (err) { error.value = managementError(err) } finally { working.value = '' }
}
async function removeDependency(id: string) {
  if (working.value) return
  working.value = 'dependency'; error.value = ''
  try { await managementApi.removeDependency(id); await load() } catch (err) { error.value = managementError(err) } finally { working.value = '' }
}
async function freeze() {
  if (!baselineLabel.value.trim()) { error.value = '请给本次计划基线命名'; return }
  if (working.value) return
  working.value = 'baseline'; error.value = ''
  try { const result = (await managementApi.freeze(props.projectId, baselineLabel.value.trim())).data; baselineLabel.value = ''; await load(); selectedBaseline.value = result.id; emit('changed'); ElMessage.success('原计划已冻结，后续调整可对照查看') }
  catch (err) { error.value = managementError(err) } finally { working.value = '' }
}
watch(() => props.projectId, () => { milestoneVisible.value = false; dependencyVisible.value = false; void load() }, { immediate: true })
</script>

<template>
  <section v-loading="loading" class="project-plan-panel">
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon><el-button link @click="load">重试</el-button></el-alert>
    <div class="section-heading"><div><h3>关键交付里程碑</h3><p>用验收完成的任务追踪关键交付节点。</p></div><el-button v-if="canPlan" type="primary" :disabled="!!working" @click="editMilestone()">新增里程碑</el-button></div>
    <el-empty v-if="!milestones.length && !loading" description="暂无里程碑" :image-size="60" />
    <div class="milestone-grid"><article v-for="item in milestones" :key="item.id" class="plan-card"><div class="card-heading"><strong>{{ item.name }}</strong><el-tag :type="item.is_overdue ? 'danger' : item.total_tasks && item.completed_tasks === item.total_tasks ? 'success' : 'info'" size="small">{{ item.is_overdue ? '交付延期' : item.total_tasks && item.completed_tasks === item.total_tasks ? '已交付' : '推进中' }}</el-tag></div><p>{{ userName(item.owner_id) }} · {{ displayDate(item.due_date) }}</p><p>已验收任务 {{ item.completed_tasks }} / {{ item.total_tasks }}</p><el-progress :percentage="item.total_tasks ? Math.round(item.completed_tasks / item.total_tasks * 100) : 0" /><div v-if="canPlan" class="actions"><el-button link type="primary" @click="editMilestone(item)">编辑</el-button><el-button link type="danger" :disabled="!!working" @click="removeMilestone(item.id)">删除</el-button></div></article></div>
    <div class="section-heading"><div><h3>任务前后依赖</h3><p>前置任务完成后，后续任务才能按计划交付。</p></div><el-button v-if="canDepend" :disabled="!!working" @click="dependency = { predecessor_id: '', successor_id: '' }; dependencyVisible = true">新增依赖</el-button></div>
    <el-empty v-if="!dependencies.length && !loading" description="暂无任务依赖" :image-size="60" />
    <article v-for="item in dependencies" :key="item.id" class="dependency-row"><div><strong>{{ item.predecessor_title }} → {{ item.successor_title }}</strong><p><el-tag :type="item.is_upstream_late ? 'danger' : item.is_blocked ? 'warning' : 'success'" size="small">{{ item.is_upstream_late ? '前置任务逾期，后续交付受影响' : item.is_blocked ? '等待前置任务完成' : '前置任务已完成' }}</el-tag></p></div><el-button v-if="canDepend" link type="danger" :disabled="!!working" @click="removeDependency(item.id)">解除依赖</el-button></article>
    <div class="section-heading"><div><h3>原计划与当前计划</h3><p>基线保留冻结时的承诺，后续改期不会覆盖原计划。</p></div></div>
    <div v-if="canPlan" class="baseline-tools"><el-input v-model="baselineLabel" placeholder="基线名称，例如：需求确认后的交付计划" maxlength="200" :disabled="!!working" /><el-button :loading="working === 'baseline'" :disabled="!!working" @click="freeze">冻结当前计划</el-button></div>
    <el-select v-if="baselines.length" v-model="selectedBaseline" aria-label="查看计划基线" class="baseline-select"><el-option v-for="item in baselines" :key="item.id" :label="`${item.label} · ${displayDate(item.created_at)}`" :value="item.id" /></el-select>
    <el-empty v-else-if="!loading" description="暂无冻结计划" :image-size="60" />
    <div v-if="baseline" class="baseline-rows"><article v-for="item in baseline.tasks" :key="item.task_id" :class="{ changed: item.changed }"><div><strong>{{ item.title }}</strong><el-tag v-if="item.changed" type="warning" size="small">计划有调整</el-tag></div><p>截止：{{ displayDate(item.baseline_deadline) }} → {{ displayDate(item.current_deadline) }}</p><p>预估：{{ item.baseline_hours ?? '未设置' }} h → {{ item.current_hours ?? '未设置' }} h</p></article></div>
    <el-dialog v-model="milestoneVisible" :title="editingMilestone ? '编辑里程碑' : '新增里程碑'" width="min(580px, calc(100vw - 24px))" :close-on-click-modal="false" :show-close="!working" :close-on-press-escape="!working"><el-form label-position="top" :disabled="!!working"><el-form-item label="关键交付名称" required><el-input v-model="milestone.name" /></el-form-item><div class="form-grid"><el-form-item label="主责" required><el-select v-model="milestone.owner_id" filterable><el-option v-for="user in users" :key="user.id" :label="user.full_name" :value="user.id" /></el-select></el-form-item><el-form-item label="交付日期" required><el-date-picker v-model="milestone.due_date" type="date" value-format="YYYY-MM-DD" /></el-form-item></div><el-form-item label="关联交付任务"><el-select v-model="milestone.task_ids" multiple filterable collapse-tags><el-option v-for="task in tasks" :key="task.id" :label="task.title" :value="task.id" /></el-select></el-form-item></el-form><el-alert v-if="error" :title="error" type="error" :closable="false" /><template #footer><el-button :disabled="!!working" @click="milestoneVisible = false">取消</el-button><el-button type="primary" :loading="working === 'milestone'" :disabled="!!working" @click="saveMilestone">保存里程碑</el-button></template></el-dialog>
    <el-dialog v-model="dependencyVisible" title="设置任务依赖" width="min(580px, calc(100vw - 24px))" :close-on-click-modal="false" :show-close="!working" :close-on-press-escape="!working"><el-form label-position="top" :disabled="!!working"><el-form-item label="先完成的任务" required><el-select v-model="dependency.predecessor_id" filterable><el-option v-for="task in allTasks" :key="task.id" :label="taskLabel(task)" :value="task.id" /></el-select></el-form-item><el-form-item label="依赖它的后续任务" required><el-select v-model="dependency.successor_id" filterable><el-option v-for="task in allTasks.filter(item => item.id !== dependency.predecessor_id)" :key="task.id" :label="taskLabel(task)" :value="task.id" /></el-select></el-form-item></el-form><el-alert v-if="error" :title="error" type="error" :closable="false" /><template #footer><el-button :disabled="!!working" @click="dependencyVisible = false">取消</el-button><el-button type="primary" :loading="working === 'dependency'" :disabled="!!working" @click="saveDependency">保存依赖</el-button></template></el-dialog>
  </section>
</template>

<style scoped>
.section-heading { display:flex; align-items:center; justify-content:space-between; gap:16px; margin:20px 0 16px; flex-wrap:wrap; }.section-heading h3 { margin:0 0 7px; font-size:16px; }.section-heading p,p { font-size:12px; color:var(--muted); line-height:1.7; }.milestone-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:16px; }.plan-card { padding:18px; background:white; border:1px solid var(--border); border-radius:8px; }.card-heading,.actions { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }.card-heading { justify-content:space-between; }.card-heading strong { overflow-wrap:anywhere; font-size:14px; }.actions { margin-top:14px; }.dependency-row { display:flex; align-items:center; justify-content:space-between; gap:12px; background:white; padding:16px; border-bottom:1px solid var(--border); }.dependency-row strong { font-size:13px; overflow-wrap:anywhere; }.baseline-tools { display:flex; gap:12px; margin-bottom:14px; }.baseline-select { width:100%; max-width:550px; }.baseline-rows { margin-top:14px; }.baseline-rows article { background:white; padding:16px; border-left:3px solid var(--border); margin:8px 0; font-size:13px; }.baseline-rows article.changed { border-left-color:#c98730; }.baseline-rows article>div { display:flex; gap:10px; flex-wrap:wrap; }.form-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; }.el-select { width:100%; }.form-grid :deep(.el-date-editor) { width:100%; }
@media(max-width:600px) { .milestone-grid,.form-grid { grid-template-columns:1fr; }.form-grid { gap:0; }.baseline-tools { flex-direction:column; }.dependency-row { align-items:flex-start; }.dependency-row>div { min-width:0; } }
</style>
