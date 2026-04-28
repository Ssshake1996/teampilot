import { describe, expect, it, vi } from 'vitest'

vi.mock('../index', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

import http from '../index'
import { reportsApi } from '../reports'

describe('reportsApi', () => {
  it('disables frontend timeout for report refresh', () => {
    reportsApi.refresh('daily')

    expect(http.post).toHaveBeenCalledWith(
      '/reports/refresh',
      { report_type: 'daily' },
      { timeout: 0 },
    )
  })
})
