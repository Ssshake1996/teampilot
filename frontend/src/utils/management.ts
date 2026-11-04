export function calendarMonday(value = new Date()): string {
  const date = new Date(value.getFullYear(), value.getMonth(), value.getDate())
  date.setDate(date.getDate() - (date.getDay() + 6) % 7)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

export function managementError(error: unknown, fallback = '操作失败，输入已保留，请重试。'): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map(item => typeof item?.msg === 'string' ? item.msg : '').filter(Boolean).join('；') || fallback
  return fallback
}

export function displayDate(value?: string | null): string {
  return value ? value.replace('T', ' ').slice(0, value.length > 10 ? 16 : 10) : '未设置'
}

export function safeEvidenceUrl(value?: string | null): string | undefined {
  if (!value) return undefined
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : undefined }
  catch { return undefined }
}

export function reportHighlights(report: Record<string, unknown>): { delivered: string[]; supportNeeded: string[] } {
  const firstNonEmpty = (...values: unknown[]): string[] => {
    for (const value of values) {
      const items = Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string' && !!item.trim()) : []
      if (items.length) return items
    }
    return []
  }
  return {
    delivered: firstNonEmpty(report.completed_tasks, report.progress_fast_top3, report.delivered),
    supportNeeded: firstNonEmpty(report.support_needed, report.progress_slow_top3),
  }
}

export const reviewLabels: Record<string, string> = {
  not_submitted: '待提交成果', submitted: '待验收', accepted: '已验收', changes_requested: '已退回',
}
