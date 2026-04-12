import http from './index'
import type { User, UserSkill, PaginatedResponse } from '@/types/models'

export const usersApi = {
  list(page = 1, pageSize = 20) {
    return http.get<PaginatedResponse<User>>('/users', { params: { page, page_size: pageSize } })
  },
  get(userId: string) {
    return http.get<User>(`/users/${userId}`)
  },
  update(userId: string, data: Partial<User>) {
    return http.patch<User>(`/users/${userId}`, data)
  },
  getWorkload(userId: string) {
    return http.get(`/users/${userId}/workload`)
  },
  getSkills(userId: string) {
    return http.get<UserSkill[]>(`/users/${userId}/skills`)
  },
  updateSkills(userId: string, skills: { skill_id: string; proficiency: number }[]) {
    return http.put(`/users/${userId}/skills`, skills)
  },
}
