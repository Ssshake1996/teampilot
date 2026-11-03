export type ModelProtocol = 'openai-completions' | 'openai-responses' | 'anthropic-messages'

export interface ModelProviderInput {
  key: string
  name: string
  protocol: ModelProtocol
  base_url: string
  api_key?: string
  clear_api_key?: boolean
  headers: Record<string, string>
  model_ids: string[]
  default_model: string
  is_enabled: boolean
  timeout_seconds: number
  verify_tls: boolean
}

export interface ModelProvider extends Omit<ModelProviderInput, 'api_key' | 'clear_api_key'> {
  id: string
  has_api_key: boolean
}

export interface ModelProviderPreset {
  key: string
  name: string
  protocol: ModelProtocol
  base_url: string
  model_ids: string[]
  default_model: string
}

export interface ModelProviderCatalog {
  protocols: { id: ModelProtocol; label: string }[]
  presets: ModelProviderPreset[]
}

export interface ModelProviderDraft extends ModelProviderInput {
  id?: string
}

export interface ProviderModel {
  id: string
  name: string
}

export interface ModelConnectionResult {
  ok: boolean
  model: string
  protocol: ModelProtocol
  message: string
  latency_ms: number
}
