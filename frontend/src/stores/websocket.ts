import { defineStore } from 'pinia'
import { ref, shallowRef } from 'vue'
import { useAuthStore } from './auth'
import { authApi } from '@/api/auth'

export const useWebSocketStore = defineStore('websocket', () => {
  const ws = shallowRef<WebSocket | null>(null)
  const connected = ref(false)
  const listeners = new Map<string, Set<(data: any) => void>>()
  let stopped = true
  let reconnect: ReturnType<typeof setTimeout> | undefined
  let retryDelay = 1000

  function dispatch(type: string, data: any) {
    listeners.get(type)?.forEach(fn => fn(data))
  }

  function connect() {
    stopped = false
    const auth = useAuthStore()
    if (!auth.token || ws.value) return
    const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`)
    ws.value = socket
    socket.onopen = () => socket.send(JSON.stringify({ token: auth.token }))
    socket.onmessage = event => {
      try {
        const msg = JSON.parse(event.data)
        dispatch(msg.type, msg.data)
      } catch { /* Ignore malformed events. */ }
    }
    socket.onclose = async event => {
      if (ws.value !== socket) return
      ws.value = null
      connected.value = false
      if (stopped || !auth.token || event.code === 4003) return
      if (event.code === 4001) {
        try {
          if (!auth.refreshToken) return
          const response = await authApi.refresh({ refresh_token: auth.refreshToken })
          if (stopped) return
          auth.setTokens(response.data.access_token, response.data.refresh_token)
        } catch { return }
      }
      reconnect = setTimeout(connect, retryDelay)
      retryDelay = Math.min(retryDelay * 2, 30000)
    }
  }

  function on(type: string, handler: (data: any) => void) {
    if (!listeners.has(type)) listeners.set(type, new Set())
    listeners.get(type)!.add(handler)
  }

  function off(type: string, handler: (data: any) => void) {
    listeners.get(type)?.delete(handler)
  }

  function disconnect() {
    stopped = true
    clearTimeout(reconnect)
    const socket = ws.value
    ws.value = null
    connected.value = false
    socket?.close()
  }

  on('connection.ready', () => {
    connected.value = true
    retryDelay = 1000
    dispatch('project.changed', {})
  })
  return { connected, connect, on, off, disconnect }
})
