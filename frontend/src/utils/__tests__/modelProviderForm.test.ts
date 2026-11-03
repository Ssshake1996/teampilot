import { describe, expect, it } from 'vitest'
import {
  editProviderHeaders,
  KEEP_PROVIDER_SECRET,
  normalizeProviderModels,
  providerRequestError,
  serializeProviderHeaders,
} from '../modelProviderForm'

describe('provider header editing', () => {
  it('keeps existing secrets without putting their sentinel into the visible value', () => {
    const rows = editProviderHeaders({ 'X-Private-Key': KEEP_PROVIDER_SECRET })
    expect(rows).toEqual([{ key: 'X-Private-Key', value: '', savedKey: 'X-Private-Key' }])
    expect(serializeProviderHeaders(rows)).toEqual({ 'X-Private-Key': KEEP_PROVIDER_SECRET })
    expect(serializeProviderHeaders([])).toEqual({})
  })

  it('requires a new value when renaming a saved secret and accepts explicit replacement', () => {
    const rows = editProviderHeaders({ 'X-Private-Key': KEEP_PROVIDER_SECRET })
    rows[0]!.key = 'X-New-Key'
    expect(() => serializeProviderHeaders(rows)).toThrow('请填写请求头 X-New-Key 的值')
    rows[0]!.value = 'replacement'
    expect(serializeProviderHeaders(rows)).toEqual({ 'X-New-Key': 'replacement' })
  })

  it('rejects duplicate names regardless of case, reserved sentinels and line breaks', () => {
    expect(() => serializeProviderHeaders([
      { key: 'X-App', value: 'one', savedKey: null },
      { key: 'x-app', value: 'two', savedKey: null },
    ])).toThrow('重复')
    expect(() => serializeProviderHeaders([{ key: 'X-App', value: KEEP_PROVIDER_SECRET, savedKey: null }])).toThrow('无效')
    expect(() => serializeProviderHeaders([{ key: 'X-App', value: 'one\r\nX-Other: two', savedKey: null }])).toThrow('无效')
  })
})

describe('provider form feedback', () => {
  it('normalizes pasted model identifiers and keeps their order', () => {
    expect(normalizeProviderModels([' model-a ', '', 'model-b', 'model-a'])).toEqual(['model-a', 'model-b'])
  })

  it('shows validation messages without rendering submitted credential values', () => {
    expect(providerRequestError({ response: { data: { detail: [{ msg: 'Invalid URL', input: 'private-value' }] } } }, '失败')).toBe('配置格式有误：Invalid URL')
    expect(providerRequestError({ response: { data: { detail: [{ loc: ['body', 'headers'], msg: 'Value error, 请求头名称不正确', input: 'private-value' }] } } }, '失败')).toBe('自定义请求头：请求头名称不正确')
    expect(providerRequestError(new Error('private-value'), '连接失败，请重试')).toBe('连接失败，请重试')
  })
})
