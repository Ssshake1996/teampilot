import { onUnmounted } from 'vue'
import { useDebounceFn, useEventListener } from '@vueuse/core'
import { useWebSocketStore } from '@/stores/websocket'

export function useProjectUpdates(refresh: (projectId?: string) => unknown) {
  const socket = useWebSocketStore()
  let disposed = false
  let running = false
  const pending = new Set<string>()
  let all = false
  const flush = useDebounceFn(async () => {
    if (disposed || running) return
    running = true
    try {
      do {
        const ids = [...pending]
        const refreshAll = all
        pending.clear()
        all = false
        if (refreshAll) await refresh()
        else for (const id of ids) await refresh(id)
      } while (!disposed && (all || pending.size))
    } finally { running = false }
  }, 400)
  const handler = (data: { project_id?: string } = {}) => {
    if (data.project_id) pending.add(data.project_id)
    else all = true
    void flush()
  }
  socket.on('project.changed', handler)
  useEventListener(window, 'focus', () => handler())
  onUnmounted(() => {
    disposed = true
    socket.off('project.changed', handler)
  })
}
