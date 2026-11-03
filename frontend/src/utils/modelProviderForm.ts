export const KEEP_PROVIDER_SECRET = '__KEEP_SECRET__'

export interface ProviderHeaderRow {
  key: string
  value: string
  savedKey: string | null
}

export function editProviderHeaders(headers: Record<string, string>): ProviderHeaderRow[] {
  return Object.entries(headers).map(([key, value]) => ({
    key,
    value: value === KEEP_PROVIDER_SECRET ? '' : value,
    savedKey: value === KEEP_PROVIDER_SECRET ? key : null,
  }))
}

export function serializeProviderHeaders(rows: ProviderHeaderRow[]): Record<string, string> {
  const headers: Record<string, string> = Object.create(null)
  const usedNames = new Set<string>()
  for (const row of rows) {
    const key = row.key.trim()
    if (!key && !row.value && !row.savedKey) continue
    if (!key || !/^[!#$%&'*+.^_`|~0-9A-Za-z-]+$/.test(key)) {
      throw new Error('请填写有效的请求头名称')
    }
    if (usedNames.has(key.toLowerCase())) throw new Error(`请求头 ${key} 重复`)
    usedNames.add(key.toLowerCase())
    if (!row.value && row.savedKey === key) {
      headers[key] = KEEP_PROVIDER_SECRET
    } else {
      if (!row.value) throw new Error(`请填写请求头 ${key} 的值，或移除该行`)
      if (row.value === KEEP_PROVIDER_SECRET || /[\r\n]/.test(row.value)) {
        throw new Error(`请求头 ${key} 的值无效`)
      }
      headers[key] = row.value
    }
  }
  return headers
}

export function normalizeProviderModels(values: string[]): string[] {
  return [...new Set(values.map(value => value.trim()).filter(Boolean))]
}

export function providerRequestError(error: unknown, fallback: string): string {
  const response = (error as { response?: { data?: { detail?: unknown } } })?.response
  const detail = response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const first = detail.find(item => item && typeof item.msg === 'string')
    if (first) {
      const labels: Record<string, string> = {
        key: '供应商标识', name: '供应商名称', protocol: '接入协议', base_url: 'API 地址',
        api_key: 'API Key', headers: '自定义请求头', model_ids: '模型列表',
        default_model: '默认模型', timeout_seconds: '请求超时',
      }
      const field = Array.isArray(first.loc) ? labels[first.loc[1]] : undefined
      const message = first.msg.replace(/^Value error, /, '')
      return `${field || '配置格式有误'}：${message}`
    }
  }
  return fallback
}
