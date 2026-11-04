<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { managementApi } from '@/api/management'
import { reportsApi } from '@/api/reports'
import { displayDate, managementError, reportHighlights } from '@/utils/management'
import type { ReportHistory } from '@/types/management'
const reportType = ref<'daily' | 'weekly'>('weekly'); const history = ref<ReportHistory[]>([]); const selected = ref('')
const report = ref<Record<string, unknown> | null>(null); const generatedAt = ref(''); const loading = ref(false); const refreshing = ref(false); const error = ref(''); let generation = 0
function strings(value: unknown): string[] { return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [] }
const sections = computed(() => {
  const value = report.value || {}
  const highlights = reportHighlights(value)
  return [
    { title: '本周承诺', items: strings(value.commitments) },
    { title: '本期已验收成果', items: highlights.delivered },
    { title: '需支持事项', items: highlights.supportNeeded },
    { title: '承诺偏差', items: strings(value.deviations) },
    { title: '下一步与负责人', items: strings(value.next_steps) },
    { title: '风险项目', items: strings(value.risky_projects) },
    { title: '逾期与持续阻塞', items: strings(value.overdue_blocked_tasks) },
    { title: '优先推进任务', items: strings(value.priority_tasks) },
    { title: '待验收事项', items: strings(value.signoff_pending) },
  ].filter(section => section.items.length)
})
const projectRows = computed(() => Array.isArray(report.value?.project_progress_table) ? report.value.project_progress_table.filter(item => item && typeof item === 'object') as Record<string, unknown>[] : [])
async function loadHistory() {
  const request = ++generation; loading.value = true; error.value = ''; report.value = null
  try {
    const response = await managementApi.reportHistory(reportType.value)
    if (request !== generation) return
    history.value = response.data
    selected.value = history.value[0]?.id || ''
    if (selected.value) await loadVersion()
  } catch (err) { if (request === generation) error.value = managementError(err, '历史报告加载失败，请重试。') }
  finally { if (request === generation) loading.value = false }
}
async function loadVersion() {
  if (!selected.value) { report.value = null; return }
  loading.value = true; error.value = ''
  report.value = null
  const selectedId = selected.value
  try { const response = await managementApi.reportVersion(selectedId); if (selectedId === selected.value) { report.value = response.data.report; generatedAt.value = response.data.generated_at } }
  catch (err) { if (selectedId === selected.value) error.value = managementError(err, '此版本报告加载失败，请重试。') }
  finally { if (selectedId === selected.value) loading.value = false }
}
async function refresh() {
  if (refreshing.value) return
  refreshing.value = true; error.value = ''
  try { await reportsApi.refresh(reportType.value); await loadHistory() }
  catch (err) { error.value = managementError(err) }
  finally { refreshing.value = false }
}
watch(reportType, loadHistory); onMounted(loadHistory)
</script>

<template>
  <section v-loading="loading" class="report-history-panel">
    <div class="report-tools"><el-radio-group v-model="reportType" :disabled="refreshing"><el-radio-button value="daily">日报</el-radio-button><el-radio-button value="weekly">周报</el-radio-button></el-radio-group><el-select v-model="selected" aria-label="选择历史报告版本" placeholder="选择历史版本" :disabled="refreshing" @change="loadVersion"><el-option v-for="item in history" :key="item.id" :label="`${displayDate(item.generated_at)} · ${item.summary.slice(0, 50)}`" :value="item.id" /></el-select><el-button type="primary" :loading="refreshing" :disabled="loading || refreshing" @click="refresh">生成新版本</el-button></div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon><el-button link @click="loadHistory">重试</el-button></el-alert>
    <p class="report-scope">报告覆盖你可见的项目；生成新版本会保留已有历史。</p>
    <el-empty v-if="!history.length && !loading" description="暂无历史报告，可生成第一个版本" />
    <article v-if="report" class="report-content"><header><h3>{{ reportType === 'weekly' ? '团队周报' : '团队日报' }}</h3><span>{{ displayDate(generatedAt) }}</span></header><p class="summary">{{ report.summary }}</p><div v-if="projectRows.length" class="project-report-rows"><article v-for="(item,index) in projectRows" :key="index"><strong>{{ item.project_name }}</strong><p>总进度 {{ item.progress_pct }}% · 已完成 {{ item.task_completion }} · 风险 {{ item.risk_level }}</p><p>{{ item.weekly_progress }}</p><p>下一步：{{ item.next_action }}</p></article></div><section v-for="section in sections" :key="section.title" class="report-section"><h4>{{ section.title }}</h4><ul><li v-for="(item,index) in section.items" :key="index">{{ item }}</li></ul></section></article>
  </section>
</template>

<style scoped>
.report-tools { display:flex; gap:14px; flex-wrap:wrap; align-items:center; margin:12px 0; }.report-tools .el-select { flex:1; min-width:220px; }.report-scope { color:var(--muted); font-size:12px; margin:14px 0; }.report-content { border:1px solid var(--border); background:white; padding:24px; border-radius:8px; }.report-content header { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }.report-content h3 { margin:0; font-size:17px; }.report-content header span { color:var(--muted); font-size:12px; }.summary { line-height:1.9; font-size:14px; }.report-section h4 { margin:24px 0 10px; font-size:14px; }.report-section ul { margin:0; padding-left:20px; }.report-section li { line-height:1.9; font-size:13px; margin:8px 0; overflow-wrap:anywhere; }.project-report-rows article { border:1px solid var(--border); padding:14px; margin:10px 0; font-size:13px; }.project-report-rows p { line-height:1.7; color:var(--muted); margin:7px 0; }
@media(max-width:600px) { .report-content { padding:16px; }.report-tools .el-select { flex:1 0 100%; }.report-tools { gap:10px; } }
</style>
