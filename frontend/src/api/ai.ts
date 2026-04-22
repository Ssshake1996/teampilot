import http from './index'
import { useAuthStore } from '@/stores/auth'

/**
 * Promise-based SSE call.
 * Streams status events to onStatus callback, resolves with final result.
 */
function sseCallAsync(
  url: string,
  body: Record<string, any>,
  onStatus?: (msg: string) => void,
): Promise<any> {
  return new Promise((resolve, reject) => {
    const auth = useAuthStore()
    const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1'

    fetch(`${baseUrl}${url}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${auth.token}`,
      },
      body: JSON.stringify(body),
    })
      .then(async (response) => {
        if (!response.ok) {
          const text = await response.text()
          reject(new Error(text || `HTTP ${response.status}`))
          return
        }

        const reader = response.body?.getReader()
        if (!reader) { reject(new Error('No stream')); return }

        const decoder = new TextDecoder()
        let buffer = ''
        let resolved = false

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          let eventType = ''
          for (const line of lines) {
            if (line.startsWith('event: ')) {
              eventType = line.slice(7).trim()
            } else if (line.startsWith('data: ')) {
              try {
                const parsed = JSON.parse(line.slice(6))
                if (eventType === 'status') {
                  onStatus?.(parsed.message)
                } else if (eventType === 'result') {
                  resolved = true
                  resolve(parsed)
                } else if (eventType === 'error') {
                  reject(new Error(parsed.message))
                }
              } catch { /* skip */ }
              eventType = ''
            }
          }
        }

        if (!resolved) reject(new Error('No result received'))
      })
      .catch((err) => reject(err))
  })
}


export const aiApi = {
  // SSE streaming AI calls — onStatus shows work progress, result arrives at end
  estimateTask(projectId: string, title: string, description: string, onStatus?: (msg: string) => void) {
    return sseCallAsync('/ai/estimate-task', { project_id: projectId, title, description }, onStatus)
  },
  recommendAssignee(taskId: string, onStatus?: (msg: string) => void) {
    return sseCallAsync('/ai/recommend-assignee', { task_id: taskId }, onStatus)
  },
  analyzeCapability(userId: string, onStatus?: (msg: string) => void) {
    return sseCallAsync('/ai/analyze-capability', { user_id: userId }, onStatus)
  },
  analyzeRisk(projectId: string, onStatus?: (msg: string) => void) {
    return sseCallAsync('/ai/analyze-risk', { project_id: projectId }, onStatus)
  },
  analyzePriority(projectId: string, onStatus?: (msg: string) => void) {
    return sseCallAsync('/ai/analyze-risk', { project_id: projectId }, onStatus)
  },
  decomposeTask(taskId: string, onStatus?: (msg: string) => void) {
    return sseCallAsync('/ai/decompose-task', { task_id: taskId }, onStatus)
  },
  previewProgressImport(text: string, onStatus?: (msg: string) => void, projectId?: string) {
    const body: Record<string, any> = { text }
    if (projectId) body.project_id = projectId
    return sseCallAsync('/ai/progress-import/preview', body, onStatus)
  },
  commitProgressImport(updates: any[]) {
    return http.post('/ai/progress-import/commit', { updates })
  },
  previewProjectPlan(prompt: string, onStatus?: (msg: string) => void) {
    return sseCallAsync('/ai/project-plan/preview', { prompt }, onStatus)
  },
  commitProjectPlan(plan: any) {
    return http.post('/ai/project-plan/commit', { plan })
  },
  dailyBrief(onStatus?: (msg: string) => void) {
    return sseCallAsync('/ai/daily-brief', {}, onStatus)
  },
  signoffAssist(taskId: string, onStatus?: (msg: string) => void) {
    return sseCallAsync('/ai/signoff-assist', { task_id: taskId }, onStatus)
  },
  projectRetrospective(projectId: string, onStatus?: (msg: string) => void) {
    return sseCallAsync('/ai/project-retrospective', { project_id: projectId }, onStatus)
  },

  // Non-streaming (config management)
  getConfig() {
    return http.get('/ai/config')
  },
  getPrompts() {
    return http.get('/ai/prompts')
  },
  updatePrompt(key: string, value: string) {
    return http.put('/ai/prompts', { key, value })
  },
  updateConfig(data: { api_base_url: string; api_key: string; model_name: string; max_tokens: number; temperature: number }) {
    return http.put('/ai/config', data)
  },
  testConnection() {
    return http.post('/ai/test-connection', {}, { timeout: 180000 })
  },
}
