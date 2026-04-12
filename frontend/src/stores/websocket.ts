import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useAuthStore } from './auth'

export const useWebSocketStore = defineStore('websocket', () => {
  const ws = ref<WebSocket | null>(null)
  const connected = ref(false)
  const listeners = ref<Map<string, Set<(data: any) => void>>>(new Map())

  function connect() {
    const auth = useAuthStore()
    if (!auth.token || ws.value) return

    const wsUrl = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/${auth.token}`
    ws.value = new WebSocket(wsUrl)

    ws.value.onopen = () => {
      connected.value = true
    }

    ws.value.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        const handlers = listeners.value.get(msg.type)
        if (handlers) {
          handlers.forEach((fn) => fn(msg.data))
        }
      } catch { /* ignore parse errors */ }
    }

    ws.value.onclose = () => {
      connected.value = false
      ws.value = null
      // Reconnect after 3 seconds
      setTimeout(() => connect(), 3000)
    }
  }

  function on(eventType: string, handler: (data: any) => void) {
    if (!listeners.value.has(eventType)) {
      listeners.value.set(eventType, new Set())
    }
    listeners.value.get(eventType)!.add(handler)
  }

  function off(eventType: string, handler: (data: any) => void) {
    listeners.value.get(eventType)?.delete(handler)
  }

  function disconnect() {
    ws.value?.close()
    ws.value = null
    connected.value = false
  }

  return { connected, connect, on, off, disconnect }
})
