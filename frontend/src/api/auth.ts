import http from './index'
import type { User } from '@/types/models'

export const authApi = {
  register(data: { username: string; email: string; password: string; full_name: string }) {
    return http.post<User>('/auth/register', data)
  },
  login(data: { username: string; password: string }) {
    return http.post<{ access_token: string; token_type: string }>('/auth/login', data)
  },
  me() {
    return http.get<User>('/auth/me')
  },
}
