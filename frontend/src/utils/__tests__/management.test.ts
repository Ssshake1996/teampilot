import { describe, expect, it } from 'vitest'
import { calendarMonday, managementError, reportHighlights, safeEvidenceUrl } from '../management'

describe('management calendar week', () => {
  it('groups a Sunday with the previous Monday across a year boundary', () => {
    expect(calendarMonday(new Date(2026, 0, 4, 23, 30))).toBe('2025-12-29')
  })
  it('keeps a Monday date even late in the local day', () => {
    expect(calendarMonday(new Date(2026, 10, 2, 23, 59))).toBe('2026-11-02')
  })
})

describe('delivery evidence links', () => {
  it('allows external HTTP documents and preserves gateway paths', () => {
    expect(safeEvidenceUrl('https://docs.example.test/team/result?id=4')).toBe('https://docs.example.test/team/result?id=4')
  })
  it.each(['javascript:alert(1)', 'data:text/html,test', '/relative-document', 'not-a-url'])('rejects non-web evidence %s', value => {
    expect(safeEvidenceUrl(value)).toBeUndefined()
  })
})

describe('management errors', () => {
  it('displays server validation messages without including request input', () => {
    expect(managementError({ response: { data: { detail: [{ msg: '任务不能依赖自身', input: 'do-not-display' }] } } })).toBe('任务不能依赖自身')
  })
})

describe('report highlights', () => {
  it('shows accepted work even when no weekly commitment was delivered', () => {
    expect(reportHighlights({ delivered: [], completed_tasks: ['已验收任务 A'], progress_fast_top3: ['其他成果'] }).delivered).toEqual(['已验收任务 A'])
  })
  it('prefers accepted task facts over the commitment delivery summary', () => {
    expect(reportHighlights({ completed_tasks: ['实际已验收成果'], delivered: ['周承诺兑现'] }).delivered).toEqual(['实际已验收成果'])
  })
  it('falls back through empty fact lists before using delivered commitments', () => {
    expect(reportHighlights({ completed_tasks: [], progress_fast_top3: ['兼容验收清单'], delivered: [] }).delivered).toEqual(['兼容验收清单'])
    expect(reportHighlights({ completed_tasks: [], progress_fast_top3: [], delivered: ['周承诺兑现'] }).delivered).toEqual(['周承诺兑现'])
  })
  it('uses historical support items when the current list has no usable entries', () => {
    expect(reportHighlights({ support_needed: [], progress_slow_top3: ['需要协助'] }).supportNeeded).toEqual(['需要协助'])
    expect(reportHighlights({ support_needed: [null, ' '], progress_slow_top3: ['需要协助'] }).supportNeeded).toEqual(['需要协助'])
    expect(reportHighlights({})).toEqual({ delivered: [], supportNeeded: [] })
  })
})
