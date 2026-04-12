import http from './index'
import type { OverviewStats, TeamWorkload, RecentActivity } from '@/types/models'

export const dashboardApi = {
  overview() {
    return http.get<OverviewStats>('/dashboard/overview')
  },
  teamWorkload() {
    return http.get<TeamWorkload[]>('/dashboard/team-workload')
  },
  recentActivity(limit = 20) {
    return http.get<RecentActivity[]>('/dashboard/recent-activity', { params: { limit } })
  },
}
