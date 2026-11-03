import http from './index'
import type {
  ModelConnectionResult,
  ModelProvider,
  ModelProviderCatalog,
  ModelProviderDraft,
  ModelProviderInput,
  ProviderModel,
} from '@/types/modelProviders'

const endpoint = '/model-providers'

function probeTimeout(data: ModelProviderDraft) {
  return { timeout: (data.timeout_seconds + 5) * 1000 }
}

export const modelProvidersApi = {
  catalog() {
    return http.get<ModelProviderCatalog>(`${endpoint}/catalog`)
  },
  list() {
    return http.get<ModelProvider[]>(endpoint)
  },
  create(data: ModelProviderInput) {
    return http.post<ModelProvider>(endpoint, data)
  },
  update(id: string, data: Partial<ModelProviderInput>) {
    return http.patch<ModelProvider>(`${endpoint}/${id}`, data)
  },
  remove(id: string) {
    return http.delete(`${endpoint}/${id}`)
  },
  models(data: ModelProviderDraft) {
    return http.post<{ models: ProviderModel[] }>(`${endpoint}/models`, data, probeTimeout(data))
  },
  test(data: ModelProviderDraft) {
    return http.post<ModelConnectionResult>(`${endpoint}/test`, data, probeTimeout(data))
  },
}
