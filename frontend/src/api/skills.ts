import http from './index'
import type { Skill } from '@/types/models'

export const skillsApi = {
  list(category?: string) {
    return http.get<Skill[]>('/skills', { params: category ? { category } : {} })
  },
  create(data: { name: string; category?: string; description?: string }) {
    return http.post<Skill>('/skills', data)
  },
  update(id: string, data: { name: string; category?: string; description?: string }) {
    return http.patch<Skill>(`/skills/${id}`, data)
  },
  delete(id: string) {
    return http.delete(`/skills/${id}`)
  },
}
