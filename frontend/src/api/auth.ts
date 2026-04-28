import http from './index'
import type { User } from '@/types/models'

export const authApi = {
  register(data: { username: string; password: string; full_name: string }) {
    return http.post<User>('/auth/register', data)
  },
  login(data: { username: string; password: string }) {
    return http.post<{ access_token: string; refresh_token: string; token_type: string }>('/auth/login', data)
  },
  refresh(data: { refresh_token: string }) {
    return http.post<{ access_token: string; refresh_token: string; token_type: string }>('/auth/refresh', data)
  },
  me() {
    return http.get<User>('/auth/me')
  },
  permissions() {
    return http.get<{ role: string; permissions: string[] }>('/permissions/me')
  },
}
