import http from './index'

export type ReportType = 'daily' | 'weekly'

export const reportsApi = {
  snapshot(reportType: ReportType) {
    return http.get('/reports/snapshot', { params: { report_type: reportType } })
  },
  refresh(reportType: ReportType) {
    return http.post('/reports/refresh', { report_type: reportType }, { timeout: 0 })
  },
  weeklyReport() {
    return http.get('/reports/weekly', { timeout: 0 })
  },
  sendReport(data: { report_type: ReportType; recipients: string[]; report?: Record<string, any>; subject?: string }) {
    return http.post('/reports/send', data)
  },
}
