import { defineStore } from 'pinia'
import { ref } from 'vue'
import { usersApi } from '@/api/users'
import type { User } from '@/types/models'

export const useUserStore = defineStore('user', () => {
  const users = ref<User[]>([])
  const total = ref(0)
  const loading = ref(false)

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

  return { users, total, loading, fetchUsers }
})
