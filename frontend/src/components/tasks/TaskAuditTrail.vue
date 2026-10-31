<script setup lang="ts">
import { ref, watch } from 'vue'
import http from '@/api/index'

const props = defineProps<{ taskId: string; revision?: string | null }>()
type Entry = { id: string; event_type: string; user_name: string; created_at: string }
const entries = ref<Entry[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const error = ref(false)
let generation = 0
async function load(append = false) {
  const request = ++generation
  loading.value = true
  error.value = false
  try {
    const response = await http.get(`/tasks/${props.taskId}/audit`, { params: { page: append ? page.value + 1 : 1 } })
    if (request !== generation) return
    entries.value = append ? [...entries.value, ...response.data.items] : response.data.items
    total.value = response.data.total
    page.value = response.data.page
  } catch { if (request === generation) error.value = true }
  finally { if (request === generation) loading.value = false }
}
watch(() => [props.taskId, props.revision], () => { entries.value = []; void load() }, { immediate: true })
</script>

<template>
  <section class="task-audit" v-loading="loading">
    <h4>会签历史</h4>
    <div v-if="error">加载失败 <el-button link type="primary" @click="load()">重试</el-button></div>
    <p v-else-if="!entries.length && !loading" class="audit-empty">暂无会签记录</p>
    <div v-for="entry in entries" :key="entry.id" class="audit-row">
      <el-tag :type="entry.event_type === 'signoff' ? 'success' : 'warning'" size="small">{{ entry.event_type === 'signoff' ? '会签完成' : '重新打开' }}</el-tag>
      <span>{{ entry.user_name }}</span><time>{{ entry.created_at.replace('T', ' ').slice(0, 16) }}</time>
    </div>
    <el-button v-if="entries.length < total" link type="primary" @click="load(true)">加载更多</el-button>
  </section>
</template>

<style scoped>
.task-audit { margin: 20px 0; }
.task-audit h4 { font-size: 14px; margin-bottom: 10px; }
.audit-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 8px 0; font-size: 13px; border-bottom: 1px solid var(--border); }
.audit-row time { margin-left: auto; font-size: 12px; color: var(--muted); }
.audit-empty { color: var(--muted); font-size: 13px; }
</style>
