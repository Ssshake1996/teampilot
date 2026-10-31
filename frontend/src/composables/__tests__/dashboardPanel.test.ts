import { describe, expect, it, vi } from 'vitest'
import { useDashboardPanel } from '../useDashboardPanel'

describe('dashboard panel reads', () => {
  it('keeps an initial failure distinct from a successful empty result', async () => {
    const request = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ data: [] })
    const panel = useDashboardPanel(request)
    await panel.load()
    expect(panel.data.value).toBeNull()
    expect(panel.error.value).toBeTruthy()
    expect(panel.updatedAt.value).toBeNull()
    await panel.load()
    expect(panel.data.value).toEqual([])
    expect(panel.error.value).toBe('')
    expect(panel.updatedAt.value).toBeTypeOf('number')
  })

  it('preserves successful data and its timestamp when a refresh fails', async () => {
    const request = vi.fn().mockResolvedValueOnce({ data: { count: 7 } }).mockRejectedValueOnce(new Error('offline'))
    const panel = useDashboardPanel(request)
    await panel.load()
    const updatedAt = panel.updatedAt.value
    await panel.load()
    expect(panel.data.value).toEqual({ count: 7 })
    expect(panel.updatedAt.value).toBe(updatedAt)
    expect(panel.error.value).toBeTruthy()
    expect(panel.loading.value).toBe(false)
  })

  it('discards a late response from an older refresh', async () => {
    let resolveOlder!: (value: { data: number }) => void
    const request = vi.fn().mockImplementationOnce(() => new Promise(resolve => { resolveOlder = resolve })).mockResolvedValueOnce({ data: 12 })
    const panel = useDashboardPanel<number>(request)
    const older = panel.load()
    await panel.load()
    resolveOlder({ data: 3 })
    await older
    expect(panel.data.value).toBe(12)
    expect(panel.loading.value).toBe(false)
  })
})
