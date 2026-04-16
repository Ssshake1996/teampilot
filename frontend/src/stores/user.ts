import { defineStore } from 'pinia'
import { ref } from 'vue'

import { usersApi } from '@/api/users'

const CACHE_TTL = 5 * 60 * 1000

export const useUserStore = defineStore('user', () => {
  const detailCache = ref<Record<string, { ts: number; data: any }>>({})

  function fresh(entry?: { ts: number; data: any } | null) {
    return Boolean(entry && Date.now() - entry.ts < CACHE_TTL)
  }

  async function fetchDetailBundle(userId: string, force = false) {
    const cached = detailCache.value[userId]
    if (!force && cached && fresh(cached)) return cached.data
    const res = await usersApi.detailBundle(userId)
    detailCache.value[userId] = { ts: Date.now(), data: res.data }
    return res.data
  }

  function invalidate(userId?: string) {
    if (userId) delete detailCache.value[userId]
    else detailCache.value = {}
  }

  return { fetchDetailBundle, invalidate }
})
