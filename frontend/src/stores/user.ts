import { defineStore } from 'pinia'
import { ref } from 'vue'
import { usersApi } from '@/api/users'
import type { User } from '@/types/models'

const CACHE_TTL = 5 * 60 * 1000

export const useUserStore = defineStore('user', () => {
  const users = ref<User[]>([])
  const total = ref(0)
  const loading = ref(false)
  const overviewCache = ref<Record<string, { ts: number; data: any }>>({})
  const detailCache = ref<Record<string, { ts: number; data: any }>>({})
  const departmentsCache = ref<{ ts: number; data: string[] } | null>(null)

  function fresh(entry?: { ts: number; data: any } | null) {
    return Boolean(entry && Date.now() - entry.ts < CACHE_TTL)
  }

  async function fetchUsers(page = 1, pageSize = 20) {
    loading.value = true
    try {
      const res = await usersApi.list(page, pageSize)
      users.value = res.data.items
      total.value = res.data.total
    } finally {
      loading.value = false
    }
  }

  async function fetchOverview(params: { page?: number; page_size?: number; search?: string; department?: string } = {}, force = false) {
    const normalized = {
      page: params.page || 1,
      page_size: params.page_size || 100,
      search: params.search || '',
      department: params.department || '',
    }
    const key = JSON.stringify(normalized)
    const cached = overviewCache.value[key]
    if (!force && cached && fresh(cached)) return cached.data

    loading.value = true
    try {
      const res = await usersApi.overview(normalized)
      overviewCache.value[key] = { ts: Date.now(), data: res.data }
      users.value = res.data.items.map((item: any) => item.user)
      total.value = res.data.total
      if (res.data.departments) {
        departmentsCache.value = { ts: Date.now(), data: res.data.departments }
      }
      return res.data
    } catch (err) {
      const res = await usersApi.list(normalized.page, normalized.page_size)
      const filteredItems = res.data.items.filter((user) => {
        const matchesSearch = !normalized.search ||
          user.full_name.includes(normalized.search) ||
          user.username.includes(normalized.search)
        const matchesDepartment = !normalized.department || user.department === normalized.department
        return matchesSearch && matchesDepartment
      })
      const fallback = {
        items: filteredItems.map((user) => ({
          user,
          skills: [],
          workload: { assigned_tasks: 0, in_progress_tasks: 0 },
        })),
        total: normalized.search || normalized.department ? filteredItems.length : res.data.total,
        page: normalized.page,
        page_size: normalized.page_size,
        departments: departmentsCache.value?.data || [],
      }
      overviewCache.value[key] = { ts: Date.now(), data: fallback }
      users.value = filteredItems
      total.value = fallback.total
      return fallback
    } finally {
      loading.value = false
    }
  }

  async function fetchDepartments(force = false) {
    if (!force && fresh(departmentsCache.value)) return departmentsCache.value!.data
    let departments: string[] = []
    try {
      const res = await usersApi.overview({ page: 1, page_size: 1 })
      departments = res.data.departments || []
    } catch {
      const res = await usersApi.departments()
      departments = res.data || []
    }
    departmentsCache.value = { ts: Date.now(), data: departments }
    return departments
  }

  async function fetchDetailBundle(userId: string, force = false) {
    const cached = detailCache.value[userId]
    if (!force && cached && fresh(cached)) return cached.data
    const res = await usersApi.detailBundle(userId)
    detailCache.value[userId] = { ts: Date.now(), data: res.data }
    return res.data
  }

  function invalidate(userId?: string) {
    overviewCache.value = {}
    departmentsCache.value = null
    if (userId) delete detailCache.value[userId]
    else detailCache.value = {}
  }

  return { users, total, loading, fetchUsers, fetchOverview, fetchDepartments, fetchDetailBundle, invalidate }
})
