import http from './index'

export const aiApi = {
  recommendAssignee(taskId: string) {
    return http.post('/ai/recommend-assignee', { task_id: taskId })
  },
  analyzeCapability(userId: string) {
    return http.post('/ai/analyze-capability', { user_id: userId })
  },
  getConfig() {
    return http.get('/ai/config')
  },
  updateConfig(data: {
    api_base_url: string
    api_key: string
    model_name: string
    max_tokens: number
    temperature: number
  }) {
    return http.put('/ai/config', data)
  },
  testConnection() {
    return http.post('/ai/test-connection')
  },
  analyzeRisk(projectId: string) {
    return http.post('/ai/analyze-risk', { project_id: projectId })
  },
  decomposeTask(taskId: string) {
    return http.post('/ai/decompose-task', { task_id: taskId })
  },
}
