import http from './index'
import type { Project, ProjectMember, PaginatedResponse } from '@/types/models'

export const projectsApi = {
  list(page = 1, pageSize = 20, includeArchived = false) {
    return http.get<PaginatedResponse<Project>>('/projects', { params: { page, page_size: pageSize, include_archived: includeArchived } })
  },
  create(data: { name: string; goal?: string; description?: string; start_date?: string; end_date?: string }) {
    return http.post<Project>('/projects', data)
  },
  get(id: string) {
    return http.get<Project>(`/projects/${id}`)
  },
  update(id: string, data: Partial<Project>) {
    return http.patch<Project>(`/projects/${id}`, data)
  },
  delete(id: string) {
    return http.delete(`/projects/${id}`)
  },
  getMembers(id: string) {
    return http.get<ProjectMember[]>(`/projects/${id}/members`)
  },
  addMember(id: string, userId: string, role = 'member') {
    return http.post(`/projects/${id}/members`, { user_id: userId, role_in_project: role })
  },
  removeMember(id: string, userId: string) {
    return http.delete(`/projects/${id}/members/${userId}`)
  },
  getTaskTree(id: string) {
    return http.get(`/projects/${id}/task-tree`)
  },
}
