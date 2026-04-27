import http from './index'
import type { DataConnector, SkillRun, TaskDataSkill, TaskProgress } from '@/types/models'

export const dataSkillsApi = {
  listConnectors() {
    return http.get<DataConnector[]>('/data-connectors')
  },
  createConnector(data: Partial<DataConnector>) {
    return http.post<DataConnector>('/data-connectors', data)
  },
  updateConnector(connectorId: string, data: Partial<DataConnector>) {
    return http.patch<DataConnector>(`/data-connectors/${connectorId}`, data)
  },
  deleteConnector(connectorId: string) {
    return http.delete(`/data-connectors/${connectorId}`)
  },
  listTaskSkills(taskId: string) {
    return http.get<TaskDataSkill[]>(`/tasks/${taskId}/data-skills`)
  },
  generateTaskSkill(taskId: string, data: { natural_language: string; connector_id?: string }) {
    return http.post<TaskDataSkill>(`/tasks/${taskId}/data-skills/generate`, data, { timeout: 180000 })
  },
  updateTaskSkill(taskId: string, skillId: string, data: Partial<TaskDataSkill>) {
    return http.patch<TaskDataSkill>(`/tasks/${taskId}/data-skills/${skillId}`, data)
  },
  confirmTaskSkill(taskId: string, skillId: string) {
    return http.post<TaskDataSkill>(`/tasks/${taskId}/data-skills/${skillId}/confirm`)
  },
  runTaskSkill(taskId: string, skillId: string, data: { params?: Record<string, any>; use_ai?: boolean }) {
    return http.post<SkillRun>(`/tasks/${taskId}/data-skills/${skillId}/run`, data, { timeout: 180000 })
  },
  listRuns(taskId: string) {
    return http.get<SkillRun[]>(`/tasks/${taskId}/data-skills/runs`)
  },
  adoptRun(taskId: string, runId: string, data: { progress_pct?: number; note?: string; hours_spent?: number }) {
    return http.post<TaskProgress>(`/tasks/${taskId}/data-skills/runs/${runId}/adopt`, data)
  },
}
