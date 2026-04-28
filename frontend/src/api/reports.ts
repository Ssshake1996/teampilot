import http from './index'

export type ReportType = 'daily' | 'weekly'

export const reportsApi = {
  weeklyReport() {
    return http.get('/reports/weekly')
  },
  sendReport(data: { report_type: ReportType; recipients: string[]; report?: Record<string, any>; subject?: string }) {
    return http.post('/reports/send', data)
  },
}
