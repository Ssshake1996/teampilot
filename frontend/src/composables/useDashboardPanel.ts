import { getCurrentScope, onScopeDispose, ref, shallowRef } from 'vue'

/** Keep successful data visible during refreshes without disguising failures as empty data. */
export function useDashboardPanel<T>(request: () => Promise<{ data: T }>) {
  const data = shallowRef<T | null>(null)
  const loading = ref(false)
  const error = ref('')
  const updatedAt = ref<number | null>(null)
  let revision = 0

  async function load() {
    const current = ++revision
    loading.value = true
    error.value = ''
    try {
      const response = await request()
      if (current !== revision) return
      data.value = response.data
      updatedAt.value = Date.now()
    } catch (reason: any) {
      if (current !== revision) return
      const detail = reason?.response?.data?.detail
      error.value = typeof detail === 'string' ? detail : '读取失败，请重试'
    } finally {
      if (current === revision) loading.value = false
    }
  }

  if (getCurrentScope()) onScopeDispose(() => { revision++ })
  return { data, loading, error, updatedAt, load }
}
