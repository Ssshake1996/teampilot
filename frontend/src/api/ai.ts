import http from './index'

const AI_TIMEOUT = 180000 // 3 minutes for AI calls

export const aiApi = {
  recommendAssignee(taskId: string) {
    return http.post('/ai/recommend-assignee', { task_id: taskId }, { timeout: AI_TIMEOUT })
  },
  analyzeCapability(userId: string) {
    return http.post('/ai/analyze-capability', { user_id: userId }, { timeout: AI_TIMEOUT })
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
    return http.post('/ai/test-connection', {}, { timeout: AI_TIMEOUT })
  },
  analyzeRisk(projectId: string) {
    return http.post('/ai/analyze-risk', { project_id: projectId }, { timeout: AI_TIMEOUT })
  },
  decomposeTask(taskId: string) {
    return http.post('/ai/decompose-task', { task_id: taskId }, { timeout: AI_TIMEOUT })
  },
  estimateTask(projectId: string, title: string, description: string = '') {
    return http.post('/ai/estimate-task', { project_id: projectId, title, description }, { timeout: AI_TIMEOUT })
  },
}
