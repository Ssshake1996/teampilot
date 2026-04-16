import http from './index'
import type { Task, TaskProgress, PaginatedResponse } from '@/types/models'
import type { TaskStatus } from '@/types/enums'

export const tasksApi = {
  list(projectId: string, params?: { status?: TaskStatus; user_id?: string; page?: number; page_size?: number }) {
    return http.get<PaginatedResponse<Task>>(`/projects/${projectId}/tasks`, { params })
  },
  create(projectId: string, data: Partial<Task>) {
    return http.post<Task>(`/projects/${projectId}/tasks`, data)
  },
  get(taskId: string) {
    return http.get<Task>(`/tasks/${taskId}`)
  },
  update(taskId: string, data: Partial<Task>) {
    return http.patch<Task>(`/tasks/${taskId}`, data)
  },
  delete(taskId: string) {
    return http.delete(`/tasks/${taskId}`)
  },
  signoff(taskId: string) {
    return http.post<Task>(`/tasks/${taskId}/signoff`)
  },
  assign(taskId: string, assigneeIds: string[]) {
    return http.patch<Task>(`/tasks/${taskId}/assign`, {
      assignee_ids: assigneeIds,
    })
  },
  logProgress(taskId: string, data: { progress_pct: number; note?: string; hours_spent?: number }) {
    return http.post<TaskProgress>(`/tasks/${taskId}/progress`, data)
  },
  getProgress(taskId: string) {
    return http.get<TaskProgress[]>(`/tasks/${taskId}/progress`)
  },
  reorder(items: { task_id: string; status: TaskStatus; sort_order: number }[]) {
    return http.patch('/tasks/reorder', items)
  },
  getSubtasks(taskId: string) {
    return http.get<Task[]>(`/tasks/${taskId}/subtasks`)
  },
  createSubtask(taskId: string, data: Partial<Task>) {
    return http.post<Task>(`/tasks/${taskId}/subtasks`, data)
  },
  batchCreateSubtasks(taskId: string, subtasks: Partial<Task>[]) {
    return http.post<Task[]>(`/tasks/${taskId}/batch-subtasks`, subtasks)
  },
}
