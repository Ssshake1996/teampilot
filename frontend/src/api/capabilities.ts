import http from './index'
import type { CapabilityProfile } from '@/types/models'

export const capabilitiesApi = {
  get(userId: string) {
    return http.get<CapabilityProfile>(`/capabilities/${userId}`)
  },
}
