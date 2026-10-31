import type { LoginRequest } from '../shared/types.js'

export function validateBaseUrl(value: string): string {
  const url = new URL(value)
  if (url.username || url.password || url.search || url.hash || url.pathname !== '/') throw new Error('Use an origin without credentials or a path')
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname))) {
    throw new Error('Remote TeamPilot requires HTTPS')
  }
  return url.origin
}

function authTokens(value: unknown): { access_token: string; refresh_token?: string | null } {
  const tokens = value as { access_token?: unknown; refresh_token?: unknown } | null
  const valid = (token: unknown): token is string => typeof token === 'string' && token.length > 0 && token.length <= 16384 && !/[^!-~]/.test(token)
  if (!tokens || !valid(tokens.access_token) || (tokens.refresh_token !== undefined && tokens.refresh_token !== null && !valid(tokens.refresh_token))) {
    throw new Error('Invalid TeamPilot authentication response')
  }
  return tokens as { access_token: string; refresh_token?: string | null }
}

export class TeamPilotApi {
  readonly baseUrl: string
  private access = ''
  private refresh = ''
  private generation = 0
  username = ''
  constructor(baseUrl: string) { this.baseUrl = validateBaseUrl(baseUrl) }
  get connected(): boolean { return Boolean(this.access) }
  logout(): void { this.generation++; this.access = ''; this.refresh = ''; this.username = '' }

  async login(data: LoginRequest, signal: AbortSignal): Promise<void> {
    this.logout()
    const generation = this.generation
    const response = authTokens(await this.send('/auth/login', 'POST', data, signal, ''))
    if (generation !== this.generation) throw new Error('Account changed during login')
    this.access = response.access_token
    this.refresh = response.refresh_token ?? ''
    this.username = data.username
  }

  async request(path: string, signal: AbortSignal, method = 'GET', body?: unknown): Promise<unknown> {
    if (!this.access) throw new Error('Log in to TeamPilot in its native DSH panel first')
    const generation = this.generation
    let result: unknown
    try { result = await this.send(path, method, body, signal, this.access) }
    catch (error) {
      if (generation !== this.generation) throw new Error('Account changed during request')
      if (!(error instanceof ApiError) || error.status !== 401) throw error
      if (!this.refresh) { this.logout(); throw error }
      try {
        const tokens = authTokens(await this.send('/auth/refresh', 'POST', { refresh_token: this.refresh }, signal, ''))
        if (generation !== this.generation) throw new Error('Account changed during request')
        this.access = tokens.access_token
        this.refresh = tokens.refresh_token ?? this.refresh
        result = await this.send(path, method, body, signal, this.access)
      } catch (refreshError) {
        if (generation !== this.generation) throw new Error('Account changed during request')
        if (refreshError instanceof ApiError && refreshError.status === 401) this.logout()
        throw refreshError
      }
    }
    if (generation !== this.generation) throw new Error('Account changed during request')
    return result
  }

  private async send(path: string, method: string, body: unknown, signal: AbortSignal, token: string): Promise<unknown> {
    const pathname = path.split('?', 1)[0]
    if (!/^\/[a-z][a-z0-9_/-]*$/i.test(pathname) || pathname.includes('//')) throw new Error('Invalid API path')
    const response = await fetch(this.baseUrl + '/api/v1' + path, {
      method, redirect: 'error', signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]),
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    // Never interpolate server error bodies: authentication errors can contain private input.
    if (!response.ok) throw new ApiError(response.status)
    const reader = response.body?.getReader()
    if (!reader) throw new Error('Empty API response')
    const chunks: Uint8Array[] = []
    let length = 0
    while (true) {
      const item = await reader.read()
      if (item.done) break
      length += item.value.byteLength
      if (length > 2 * 1024 * 1024) { await reader.cancel(); throw new Error('Response exceeds context limit') }
      chunks.push(item.value)
    }
    // SyntaxError messages can include server content, including credentials.
    try { return JSON.parse(Buffer.concat(chunks).toString('utf8')) }
    catch { throw new Error('Invalid TeamPilot JSON response') }
  }
}

export class ApiError extends Error {
  constructor(readonly status: number) {
    super(`TeamPilot HTTP ${status}: ${status === 409 ? 'draft expired or project changed; create a new draft' : status === 403 ? 'permission or explicit approval required' : 'request failed'}`)
  }
}
