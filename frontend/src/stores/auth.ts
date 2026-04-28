import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api/auth'
import type { User } from '@/types/models'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('token'))
  const refreshToken = ref<string | null>(localStorage.getItem('refresh_token'))
  const user = ref<User | null>(null)
  const permissions = ref<string[]>([])

  const isAuthenticated = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === 'admin')
  const isManager = computed(() => user.value?.role === 'admin' || user.value?.role === 'manager')
  const permissionSet = computed(() => new Set(permissions.value))

  async function login(username: string, password: string) {
    const res = await authApi.login({ username, password })
    setTokens(res.data.access_token, res.data.refresh_token)
    await fetchUser()
  }

  function setTokens(accessToken: string, nextRefreshToken?: string | null) {
    token.value = accessToken
    localStorage.setItem('token', accessToken)
    if (nextRefreshToken) {
      refreshToken.value = nextRefreshToken
      localStorage.setItem('refresh_token', nextRefreshToken)
    }
  }

  async function fetchUser() {
    if (!token.value) return
    try {
      const res = await authApi.me()
      user.value = res.data
      await fetchPermissions()
    } catch {
      logout()
    }
  }

  async function fetchPermissions() {
    if (!token.value) return
    try {
      const permRes = await authApi.permissions()
      permissions.value = permRes.data.permissions || []
    } catch {
      logout()
    }
  }

  function can(permission: string) {
    return user.value?.role === 'admin' || permissionSet.value.has(permission)
  }

  function logout() {
    token.value = null
    refreshToken.value = null
    user.value = null
    permissions.value = []
    localStorage.removeItem('token')
    localStorage.removeItem('refresh_token')
  }

  return {
    token,
    refreshToken,
    user,
    permissions,
    isAuthenticated,
    isAdmin,
    isManager,
    can,
    login,
    setTokens,
    fetchUser,
    fetchPermissions,
    logout,
  }
})
