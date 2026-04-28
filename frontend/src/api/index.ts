import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import router from '@/router'
import type { InternalAxiosRequestConfig } from 'axios'

type RetriableRequestConfig = InternalAxiosRequestConfig & { _retry?: boolean }
type TokenResponse = { access_token: string; refresh_token?: string | null; token_type: string }

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000,
})

let refreshRequest: Promise<string | null> | null = null

function isAuthEndpoint(url?: string) {
  return !!url && (url.includes('/auth/login') || url.includes('/auth/refresh'))
}

async function requestNewAccessToken(refreshToken: string) {
  const res = await axios.post<TokenResponse>(
    `${http.defaults.baseURL}/auth/refresh`,
    { refresh_token: refreshToken },
    { timeout: 30000 },
  )
  const auth = useAuthStore()
  auth.setTokens(res.data.access_token, res.data.refresh_token)
  return res.data.access_token
}

http.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
})

http.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config as RetriableRequestConfig | undefined
    if (
      error.response?.status === 401 &&
      original &&
      !original._retry &&
      !isAuthEndpoint(original.url)
    ) {
      const auth = useAuthStore()
      if (auth.refreshToken) {
        original._retry = true
        try {
          refreshRequest = refreshRequest || requestNewAccessToken(auth.refreshToken)
          const nextToken = await refreshRequest
          if (nextToken) {
            original.headers.Authorization = `Bearer ${nextToken}`
            return http(original)
          }
        } catch {
          auth.logout()
          router.push('/login')
        } finally {
          refreshRequest = null
        }
      }
    }

    if (error.response?.status === 401) {
      const auth = useAuthStore()
      auth.logout()
      router.push('/login')
    }
    return Promise.reject(error)
  },
)

export default http
